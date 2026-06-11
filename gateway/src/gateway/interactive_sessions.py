"""In-process interactive REPL sessions (HTTP polling from web/TUI)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from gateway.instance_store import InstanceStatus
from node_agent.conversation import run_conversation_turn
from node_agent.conversation_store import ConversationStore
from node_agent.gateway_client import GatewayClient
from node_agent.markdown_config import load_agent_settings
from node_agent.tools.registry import ToolRegistry
from shared.run_store import RunStatus, RunStore

if TYPE_CHECKING:
    from gateway.instance_lifecycle import InstanceLifecycle

logger = structlog.get_logger(__name__)


class SessionState(str, Enum):
    IDLE = "interactive_idle"
    BUSY = "interactive_busy"
    ERROR = "error"
    STOPPED = "stopped"


def _timestamp_suffix() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


@dataclass
class InteractiveSession:
    instance_id: str
    directory: Path
    gateway_url: str
    state: SessionState = SessionState.IDLE
    last_reply: str | None = None
    last_error: str | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _store: ConversationStore | None = field(default=None, repr=False)
    _gateway: GatewayClient | None = field(default=None, repr=False)
    _settings: object | None = field(default=None, repr=False)

    async def _ensure_ready(self) -> tuple[object, GatewayClient, ConversationStore, ToolRegistry]:
        if self._store is None:
            settings = load_agent_settings(self.directory)
            gateway = GatewayClient(self.gateway_url)
            store = ConversationStore(settings.paths.conversation_db)
            await store.connect()
            self._settings = settings
            self._gateway = gateway
            self._store = store
        assert self._settings is not None
        assert self._gateway is not None
        assert self._store is not None
        conversation_id = self._current_conversation_id(self._settings)
        tools = ToolRegistry(self._settings, self._gateway, conversation_id=conversation_id)
        return self._settings, self._gateway, self._store, tools

    def _current_conversation_id(self, settings) -> str:
        from shared.markdown_io import parse_markdown_document

        meta, _ = parse_markdown_document(settings.paths.config_file.read_text(encoding="utf-8"))
        return str(meta.get("current_conversation_id") or "interactive")

    def _prepare_run_for_message(
        self,
        lifecycle: InstanceLifecycle,
        message: str,
    ) -> tuple[str, str, bool]:
        from shared.markdown_io import parse_markdown_document, render_markdown_document

        settings = load_agent_settings(self.directory)
        meta, body = parse_markdown_document(settings.paths.config_file.read_text(encoding="utf-8"))
        run_store = RunStore(self.directory)
        conv_id = str(meta.get("current_conversation_id") or "")
        needs_new_run = False
        if conv_id and (self.directory / "conversations" / conv_id / "run.json").exists():
            run = run_store.get_run(conv_id)
            if run.status == RunStatus.DONE:
                needs_new_run = True
        else:
            needs_new_run = True

        if needs_new_run:
            conv_id = f"run-{_timestamp_suffix()}"
            run_store.create_run(conv_id, goal=message.strip())
            meta["current_conversation_id"] = conv_id
            settings.paths.config_file.write_text(
                render_markdown_document(meta, body),
                encoding="utf-8",
            )
            return conv_id, message.strip(), True

        run = run_store.get_run(conv_id)
        if not run.goal.strip():
            run_store.set_goal(conv_id, message.strip())
            run_store.update_run_status(conv_id, RunStatus.EXECUTING)
            return conv_id, message.strip(), True

        if run.status == RunStatus.PAUSED:
            run_store.update_run_status(conv_id, RunStatus.EXECUTING)
        return conv_id, message.strip(), False

    async def send_message(
        self,
        message: str,
        *,
        status_callback,
        lifecycle: InstanceLifecycle,
    ) -> None:
        async with self._lock:
            self.state = SessionState.BUSY
            self.last_error = None
            self.last_reply = None
            await status_callback(InstanceStatus.INTERACTIVE_BUSY)
            try:
                settings, gateway, store, tools = await self._ensure_ready()
                conversation_id, user_input, is_goal = self._prepare_run_for_message(
                    lifecycle, message
                )
                tools = ToolRegistry(settings, gateway, conversation_id=conversation_id)
                run = RunStore(self.directory).get_run(conversation_id)
                if is_goal:
                    await store.clear_conversation(conversation_id)
                reply = await run_conversation_turn(
                    settings=settings,
                    gateway=gateway,
                    store=store,
                    tools=tools,
                    conversation_id=conversation_id,
                    user_input=user_input,
                    run_options=run.options,
                )
                run = RunStore(self.directory).get_run(conversation_id)
                if run.status == RunStatus.DONE:
                    await status_callback(InstanceStatus.COMPLETED)
                else:
                    await status_callback(InstanceStatus.INTERACTIVE_IDLE)
                self.last_reply = reply
                self.state = SessionState.IDLE
            except Exception as exc:
                self.last_error = str(exc)
                self.state = SessionState.ERROR
                await status_callback(InstanceStatus.ERROR)
                logger.warning("interactive_error", instance_id=self.instance_id, error=str(exc))

    async def close(self) -> None:
        if self._gateway is not None:
            await self._gateway.aclose()


class InteractiveSessionManager:
    def __init__(self, *, gateway_url: str) -> None:
        self.gateway_url = gateway_url.rstrip("/")
        self._sessions: dict[str, InteractiveSession] = {}

    def register(self, instance_id: str, directory: Path) -> InteractiveSession:
        session = InteractiveSession(
            instance_id=instance_id,
            directory=directory,
            gateway_url=self.gateway_url,
        )
        self._sessions[instance_id] = session
        return session

    def get(self, instance_id: str) -> InteractiveSession | None:
        return self._sessions.get(instance_id)

    def list_sessions(self) -> list[InteractiveSession]:
        return sorted(self._sessions.values(), key=lambda s: s.instance_id)

    async def unregister(self, instance_id: str) -> None:
        session = self._sessions.pop(instance_id, None)
        if session is not None:
            await session.close()

    async def stop_all(self) -> None:
        for instance_id in list(self._sessions):
            await self.unregister(instance_id)
