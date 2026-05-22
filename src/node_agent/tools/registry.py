"""Tool execution registry."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from gateway.markdown_io import parse_markdown_document, render_markdown_document
from gateway.schemas import Message, ToolCall
from node_agent.gateway_client import GatewayClient
from node_agent.markdown_config import AgentSettings
from node_agent.sandbox import SandboxViolation
from node_agent.tools import files, sqlite_tools

ToolHandler = Callable[..., Awaitable[str]]


class ToolRegistry:
    def __init__(self, settings: AgentSettings, gateway: GatewayClient) -> None:
        self._settings = settings
        self._gateway = gateway
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
        }

    async def _read_file(self, **kwargs: Any) -> str:
        return await files.read_file(self._settings.paths.workspace_root, kwargs["path"])

    async def _write_file(self, **kwargs: Any) -> str:
        return await files.write_file(
            self._settings.paths.workspace_root,
            kwargs["path"],
            kwargs["content"],
        )

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
        return await sqlite_tools.sqlite_execute(
            self._settings.paths.sqlite_root,
            kwargs["db_name"],
            kwargs["sql"],
            kwargs.get("params"),
        )

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
