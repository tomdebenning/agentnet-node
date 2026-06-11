"""Ollama tool definitions for the slim agent."""

from __future__ import annotations

from shared.schemas import ToolDefinition

ALL_TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        type="function",
        function={
            "name": "read_file",
            "description": "Read a text file from the agent workspace.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    ),
    ToolDefinition(
        type="function",
        function={
            "name": "write_file",
            "description": "Write a text file in the agent workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    ),
    ToolDefinition(
        type="function",
        function={
            "name": "list_files",
            "description": "List files in a workspace directory.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "default": "."}},
                "required": [],
            },
        },
    ),
    ToolDefinition(
        type="function",
        function={
            "name": "list_databases",
            "description": "List SQLite databases.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    ),
    ToolDefinition(
        type="function",
        function={
            "name": "sqlite_query",
            "description": "Run a read-only SQL query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "db_name": {"type": "string"},
                    "sql": {"type": "string"},
                    "params": {"type": "array", "items": {}},
                },
                "required": ["db_name", "sql"],
            },
        },
    ),
    ToolDefinition(
        type="function",
        function={
            "name": "sqlite_execute",
            "description": "Run a write SQL statement.",
            "parameters": {
                "type": "object",
                "properties": {
                    "db_name": {"type": "string"},
                    "sql": {"type": "string"},
                    "params": {"type": "array", "items": {}},
                },
                "required": ["db_name", "sql"],
            },
        },
    ),
    ToolDefinition(
        type="function",
        function={
            "name": "sqlite_schema",
            "description": "Show schema for a SQLite database.",
            "parameters": {
                "type": "object",
                "properties": {"db_name": {"type": "string"}},
                "required": ["db_name"],
            },
        },
    ),
    ToolDefinition(
        type="function",
        function={
            "name": "web_search",
            "description": "Search the public web using Brave Search.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "count": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
    ),
    ToolDefinition(
        type="function",
        function={
            "name": "fetch_url",
            "description": "Fetch readable text content from a URL.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    ),
    ToolDefinition(
        type="function",
        function={
            "name": "read_memory",
            "description": "Read persistent memory markdown body.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    ),
    ToolDefinition(
        type="function",
        function={
            "name": "write_memory",
            "description": "Replace persistent memory markdown body.",
            "parameters": {
                "type": "object",
                "properties": {"content": {"type": "string"}},
                "required": ["content"],
            },
        },
    ),
]

RUN_TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        type="function",
        function={
            "name": "set_plan",
            "description": "Define plan steps for the current run goal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "title": {"type": "string"},
                            },
                            "required": ["title"],
                        },
                    }
                },
                "required": ["steps"],
            },
        },
    ),
    ToolDefinition(
        type="function",
        function={
            "name": "advance_step",
            "description": "Mark a plan step complete and move to the next step.",
            "parameters": {
                "type": "object",
                "properties": {"step_id": {"type": "string"}},
                "required": ["step_id"],
            },
        },
    ),
    ToolDefinition(
        type="function",
        function={
            "name": "mark_goal_done",
            "description": "Mark the run goal complete and designate product artifact id(s).",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_artifact_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    }
                },
                "required": ["product_artifact_ids"],
            },
        },
    ),
    ToolDefinition(
        type="function",
        function={
            "name": "send_artifact_to_agent",
            "description": "Send an artifact to another control-plane agent as a task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_agent_id": {"type": "string"},
                    "artifact_id": {"type": "string"},
                    "prompt": {"type": "string"},
                },
                "required": ["target_agent_id", "artifact_id", "prompt"],
            },
        },
    ),
]

ALL_TOOLS = ALL_TOOLS + RUN_TOOLS

_MEMORY_TOOL_NAMES = frozenset({"read_memory", "write_memory"})


def tools_for_agent(*, uses_memory: bool = True) -> list[ToolDefinition]:
    if uses_memory:
        return ALL_TOOLS
    return [tool for tool in ALL_TOOLS if tool.function.get("name") not in _MEMORY_TOOL_NAMES]
