"""Tool execution registry."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from shared.markdown_io import parse_markdown_document, render_markdown_document
from shared.run_store import RunStore
from shared.schemas import Message, ToolCall
from node_agent.gateway_client import GatewayClient
from node_agent.markdown_config import AgentSettings
from node_agent.run_tools import RunToolContext
from shared.sandbox import SandboxViolation
from node_agent.tools import files, sqlite_tools

ToolHandler = Callable[..., Awaitable[str]]


class ToolRegistry:
    def __init__(
        self,
        settings: AgentSettings,
        gateway: GatewayClient,
        *,
        conversation_id: str | None = None,
    ) -> None:
        self._settings = settings
        self._gateway = gateway
        self._conversation_id = conversation_id
        self._run_store = RunStore(settings.paths.root) if conversation_id else None
        self._run_tools = (
            RunToolContext(
                settings=settings,
                gateway=gateway,
                conversation_id=conversation_id,
            )
            if conversation_id
            else None
        )
        self._handlers: dict[str, ToolHandler] = {
            "read_file": self._read_file,
            "write_file": self._write_file,
            "list_files": self._list_files,
            "list_databases": self._list_databases,
            "sqlite_query": self._sqlite_query,
            "sqlite_execute": self._sqlite_execute,
            "sqlite_schema": self._sqlite_schema,
            "web_search": self._web_search,
            "fetch_url": self._fetch_url,
            "read_memory": self._read_memory,
            "write_memory": self._write_memory,
            "set_plan": self._set_plan,
            "advance_step": self._advance_step,
            "mark_goal_done": self._mark_goal_done,
            "send_artifact_to_agent": self._send_artifact_to_agent,
        }

    async def _read_file(self, **kwargs: Any) -> str:
        return await files.read_file(self._settings.paths.workspace_root, kwargs["path"])

    async def _write_file(self, **kwargs: Any) -> str:
        path = kwargs["path"]
        result = await files.write_file(
            self._settings.paths.workspace_root,
            path,
            kwargs["content"],
        )
        if self._run_store is not None and self._conversation_id is not None:
            artifact = self._run_store.record_artifact(
                self._conversation_id,
                artifact_type="file",
                summary=f"Wrote {path}",
                ref={"path": path},
            )
            return f"{result} (artifact_id={artifact.artifact_id})"
        return result

    async def _list_files(self, **kwargs: Any) -> str:
        return await files.list_files(
            self._settings.paths.workspace_root,
            kwargs.get("path", "."),
        )

    async def _list_databases(self, **kwargs: Any) -> str:
        return await sqlite_tools.list_databases(self._settings.paths.sqlite_root)

    async def _sqlite_query(self, **kwargs: Any) -> str:
        return await sqlite_tools.sqlite_query(
            self._settings.paths.sqlite_root,
            kwargs["db_name"],
            kwargs["sql"],
            kwargs.get("params"),
        )

    async def _sqlite_execute(self, **kwargs: Any) -> str:
        db_name = kwargs["db_name"]
        sql = kwargs["sql"]
        result = await sqlite_tools.sqlite_execute(
            self._settings.paths.sqlite_root,
            db_name,
            sql,
            kwargs.get("params"),
        )
        if self._run_store is not None and self._conversation_id is not None:
            artifact = self._run_store.record_artifact(
                self._conversation_id,
                artifact_type="db",
                summary=f"Executed SQL on {db_name}",
                ref={"db_name": db_name, "sql": sql},
            )
            result = f"{result} (artifact_id={artifact.artifact_id})"
        return result

    async def _sqlite_schema(self, **kwargs: Any) -> str:
        return await sqlite_tools.sqlite_schema(
            self._settings.paths.sqlite_root,
            kwargs["db_name"],
        )

    async def _web_search(self, **kwargs: Any) -> str:
        return await self._gateway.web_search(kwargs["query"], int(kwargs.get("count") or 5))

    async def _fetch_url(self, **kwargs: Any) -> str:
        return await self._gateway.fetch_url(kwargs["url"])

    async def _read_memory(self, **kwargs: Any) -> str:
        return self._settings.paths.memory_file.read_text(encoding="utf-8")

    async def _write_memory(self, **kwargs: Any) -> str:
        meta, _ = parse_markdown_document(
            self._settings.paths.memory_file.read_text(encoding="utf-8")
        )
        rendered = render_markdown_document(meta, kwargs["content"])
        self._settings.paths.memory_file.write_text(rendered, encoding="utf-8")
        self._settings.memory_body = kwargs["content"]
        return "memory updated"

    async def _set_plan(self, **kwargs: Any) -> str:
        if self._run_tools is None:
            return "Error: no active run"
        return await self._run_tools.set_plan(kwargs["steps"])

    async def _advance_step(self, **kwargs: Any) -> str:
        if self._run_tools is None:
            return "Error: no active run"
        return await self._run_tools.advance_step(kwargs["step_id"])

    async def _mark_goal_done(self, **kwargs: Any) -> str:
        if self._run_tools is None:
            return "Error: no active run"
        return await self._run_tools.mark_goal_done(kwargs["product_artifact_ids"])

    async def _send_artifact_to_agent(self, **kwargs: Any) -> str:
        if self._run_tools is None:
            return "Error: no active run"
        return await self._run_tools.send_artifact_to_agent(
            kwargs["target_agent_id"],
            kwargs["artifact_id"],
            kwargs["prompt"],
        )

    def _parse_arguments(self, tool_call: ToolCall) -> dict[str, Any]:
        raw = (tool_call.function or {}).get("arguments")
        if not raw:
            return {}
        if isinstance(raw, dict):
            return raw
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("Tool arguments must be a JSON object")
        return parsed

    async def execute(self, tool_call: ToolCall) -> Message:
        tool_name = (tool_call.function or {}).get("name") or ""
        handler = self._handlers.get(tool_name)
        if handler is None:
            return Message(
                role="tool",
                tool_call_id=tool_call.id,
                name=tool_name,
                content=f"Error: unknown tool: {tool_name}",
            )
        try:
            args = self._parse_arguments(tool_call)
            result = await handler(**args)
            return Message(
                role="tool",
                tool_call_id=tool_call.id,
                name=tool_name,
                content=result,
            )
        except SandboxViolation as exc:
            return Message(
                role="tool",
                tool_call_id=tool_call.id,
                name=tool_name,
                content=f"Error: {exc}",
            )
        except Exception as exc:
            return Message(
                role="tool",
                tool_call_id=tool_call.id,
                name=tool_name,
                content=f"Error: {exc}",
            )
