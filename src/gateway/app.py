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
from gateway.agent_store import AgentStore
from gateway.config import GatewayConfig, load_config
from gateway.control_plane_client import ControlPlaneClient
from gateway.heartbeat_loop import node_heartbeat_loop
from gateway.routes import admin, proxy

logger = structlog.get_logger(__name__)


def _static_dir() -> Path | None:
    candidates = [
        Path(__file__).resolve().parents[2] / "frontend" / "dist",
        Path.cwd() / "frontend" / "dist",
    ]
    for candidate in candidates:
        if (candidate / "index.html").exists():
            return candidate
    return None


def create_app(config: GatewayConfig | None = None) -> FastAPI:
    settings = config or load_config()
    gateway_url = f"http://{settings.server.host}:{settings.server.port}"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.config = settings
        app.state.agent_store = AgentStore(settings.agents_root_path)
        app.state.agent_manager = AgentManager(gateway_url=gateway_url)
        app.state.control_plane_client = ControlPlaneClient(settings.control_plane)

        for summary in app.state.agent_store.list_agents():
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
        )
        try:
            yield
        finally:
            stop_event.set()
            heartbeat_task.cancel()
            await app.state.agent_manager.stop_all()
            await app.state.control_plane_client.aclose()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task

    app = FastAPI(title="Agentnet Node Gateway", lifespan=lifespan)
    app.include_router(admin.router)
    app.include_router(proxy.router)

    static_root = _static_dir()
    if static_root is not None:
        assets_dir = static_root / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/")
        async def spa_index() -> FileResponse:
            return FileResponse(static_root / "index.html")

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str) -> FileResponse:
            if full_path.startswith("api/") or full_path.startswith("proxy/"):
                from fastapi import HTTPException

                raise HTTPException(status_code=404)
            candidate = static_root / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(static_root / "index.html")

    return app
