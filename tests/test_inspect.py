"""Tests for agent inspection APIs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from gateway.agent_inspect import (
    format_messages_for_display,
    get_conversation_messages,
    list_conversations,
    list_databases,
    list_workspace,
    read_workspace_file,
)
from gateway.agent_store import AgentStore
from gateway.app import create_app
from gateway.config import ControlPlaneSection, GatewayConfig, NodeSection, ServerSection


@pytest.fixture
def agent_dir(tmp_path: Path) -> Path:
    store = AgentStore(tmp_path / "agents")
    path = store.create_agent("bot")
    ws = path / "workspace" / "notes.txt"
    ws.write_text("hello artifact", encoding="utf-8")
    db = path / "databases" / "main.sqlite"
    import sqlite3

    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE items (id INTEGER, label TEXT)")
    conn.execute("INSERT INTO items VALUES (1, 'alpha')")
    conn.commit()
    conn.close()

    state = path / "agent_state.db"
    import sqlite3 as sq

    c = sq.connect(state)
    c.execute(
        "CREATE TABLE messages (id INTEGER PRIMARY KEY, conversation_id TEXT, round INT, payload TEXT)"
    )
    c.execute(
        "CREATE TABLE conversations (conversation_id TEXT PRIMARY KEY, status TEXT)"
    )
    payload = json.dumps({"role": "user", "content": "hi"})
    c.execute("INSERT INTO messages VALUES (1, 'task', 1, ?)", (payload,))
    c.execute("INSERT INTO conversations VALUES ('task', 'active')")
    c.commit()
    c.close()
    return path


def test_list_and_read_conversations(agent_dir: Path) -> None:
    convs = list_conversations(agent_dir)
    assert convs[0]["conversation_id"] == "task"
    messages = get_conversation_messages(agent_dir, "task")
    assert messages[0]["content"] == "hi"
    assert "role=user" in format_messages_for_display(messages)


def test_workspace_and_database(agent_dir: Path) -> None:
    entries = list_workspace(agent_dir, ".")
    assert any(e["name"] == "notes.txt" for e in entries)
    content = read_workspace_file(agent_dir, "notes.txt")
    assert content["content"] == "hello artifact"
    assert "main" in list_databases(agent_dir)


@pytest.mark.asyncio
async def test_inspect_api_routes(agent_dir: Path, tmp_path: Path) -> None:
    config = GatewayConfig(
        node=NodeSection(id="n"),
        server=ServerSection(host="127.0.0.1", port=8080),
        agents_root=str(agent_dir.parent),
        control_plane=ControlPlaneSection(url="http://127.0.0.1:8000"),
    )
    app = create_app(config)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            convs = await client.get("/api/fleet/instances/bot/conversations")
            assert convs.status_code == 200
            detail = await client.get("/api/fleet/instances/bot/conversations/task")
            assert "hi" in detail.json()["formatted"]
            ws = await client.get("/api/fleet/instances/bot/workspace")
            assert ws.status_code == 200
            dbs = await client.get("/api/fleet/instances/bot/databases")
            assert "main" in dbs.json()["databases"]
