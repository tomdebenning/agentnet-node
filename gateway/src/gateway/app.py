"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from gateway.agent_manager import AgentManager
from gateway.completion_log import CompletionLog
from gateway.config import GatewayConfig, load_config
from gateway.control_plane_client import ControlPlaneClient
from gateway.heartbeat_loop import node_heartbeat_loop
from gateway.instance_lifecycle import InstanceLifecycle
from gateway.instance_store import InstanceStore
from gateway.interactive_sessions import InteractiveSessionManager
from gateway.definition_store import DefinitionStore
from gateway.definition_registry import DefinitionRegistry
from gateway.routes import admin, definitions, fleet, proxy
from gateway.urls import static_dir

logger = structlog.get_logger(__name__)


def _static_dir() -> Path | None:
    return static_dir()


def create_app(config: GatewayConfig | None = None) -> FastAPI:
    settings = config or load_config()
    gateway_url = f"http://{settings.server.host}:{settings.server.port}"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.config = settings
        app.state.agent_store = InstanceStore(settings.agents_root_path)
        app.state.definition_registry = DefinitionRegistry(settings.database_path)
        app.state.definition_store = DefinitionStore(
            settings.definitions_root_path,
            registry=app.state.definition_registry,
        )
        app.state.definition_registry.reconcile(app.state.definition_store)
        app.state.agent_manager = AgentManager(gateway_url=gateway_url)
        app.state.interactive_manager = InteractiveSessionManager(gateway_url=gateway_url)
        app.state.completion_log = CompletionLog()
        app.state.instance_lifecycle = InstanceLifecycle(
            instance_store=app.state.agent_store,
            definition_store=app.state.definition_store,
            agent_manager=app.state.agent_manager,
            interactive_manager=app.state.interactive_manager,
            completion_log=app.state.completion_log,
        )
        app.state.control_plane_client = ControlPlaneClient(settings.control_plane)

        for summary in app.state.agent_store.list_agents():
            try:
                meta = app.state.agent_store.read_instance_meta(summary.agent_id)
            except Exception as exc:
                logger.warning(
                    "agent_register_skipped",
                    agent_id=summary.agent_id,
                    error=str(exc),
                )
                continue
            if meta.get("mode") == "interactive":
                app.state.interactive_manager.register(summary.agent_id, summary.path)
            else:
                app.state.agent_manager.register(summary.agent_id, summary.path)

        stop_event = asyncio.Event()
        app.state.stop_event = stop_event
        heartbeat_task = asyncio.create_task(
            node_heartbeat_loop(
                settings,
                app.state.control_plane_client,
                app.state.agent_manager,
                stop_event,
            )
        )
        logger.info(
            "gateway_started",
            node_id=settings.node.id,
            url=gateway_url,
            agents_root=str(settings.agents_root_path),
            definitions_root=str(settings.definitions_root_path),
            database_path=str(settings.database_path),
        )
        try:
            yield
        finally:
            stop_event.set()
            heartbeat_task.cancel()
            await app.state.agent_manager.stop_all()
            await app.state.interactive_manager.stop_all()
            await app.state.control_plane_client.aclose()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task

    app = FastAPI(title="Agentnet Node Gateway", lifespan=lifespan)
    app.include_router(admin.router)
    app.include_router(fleet.router)
    app.include_router(definitions.router)
    app.include_router(proxy.router)

    static_root = _static_dir()
    if static_root is not None:
        assets_dir = static_root / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/")
        async def spa_index() -> FileResponse:
            return FileResponse(
                static_root / "index.html",
                headers={"Cache-Control": "no-cache"},
            )

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str) -> FileResponse:
            if full_path.startswith("api/") or full_path.startswith("proxy/"):
                from fastapi import HTTPException

                raise HTTPException(status_code=404)
            candidate = static_root / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(
                static_root / "index.html",
                headers={"Cache-Control": "no-cache"},
            )

    return app
