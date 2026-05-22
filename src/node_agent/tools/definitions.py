"""Ollama tool definitions for the slim agent."""

from __future__ import annotations

from gateway.schemas import ToolDefinition

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
