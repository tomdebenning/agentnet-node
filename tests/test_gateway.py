"""Tests for agentnet-node."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.agent_store import AgentFileKind, AgentStore
from gateway.app import create_app
from gateway.config import GatewayConfig, NodeSection, ControlPlaneSection, ServerSection
from gateway.markdown_io import parse_markdown_document, render_markdown_document


@pytest.fixture
def tmp_agents_root(tmp_path: Path) -> Path:
    root = tmp_path / "agents"
    root.mkdir()
    return root


@pytest.fixture
def gateway_config(tmp_agents_root: Path) -> GatewayConfig:
    return GatewayConfig(
        node=NodeSection(id="test-node"),
        server=ServerSection(host="127.0.0.1", port=8080),
        agents_root=str(tmp_agents_root),
        control_plane=ControlPlaneSection(url="http://127.0.0.1:8000"),
    )


def test_markdown_roundtrip() -> None:
    rendered = render_markdown_document({"agent_id": "a1"}, "# Hello\n")
    meta, body = parse_markdown_document(rendered)
    assert meta["agent_id"] == "a1"
    assert body.startswith("# Hello")


def test_agent_store_crud(tmp_agents_root: Path) -> None:
    store = AgentStore(tmp_agents_root)
    store.create_agent("alpha", target_puller="puller-01", model="llama3.1:8b")
    agents = store.list_agents()
    assert len(agents) == 1
    assert agents[0].agent_id == "alpha"
    content = store.read_file("alpha", AgentFileKind.PERSONA)
    assert "alpha" in content
    store.delete_agent("alpha")
    assert store.list_agents() == []


@pytest.mark.asyncio
async def test_admin_api_list_and_create(gateway_config: GatewayConfig) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            empty = await client.get("/api/agents")
            assert empty.status_code == 200
            assert empty.json()["agents"] == []

            created = await client.post(
                "/api/agents",
                json={"agent_id": "demo", "target_puller": "puller-01", "model": "llama3.1:8b"},
            )
            assert created.status_code == 201
            assert created.json()["agent_id"] == "demo"

            listing = await client.get("/api/agents")
            assert len(listing.json()["agents"]) == 1


@pytest.mark.asyncio
async def test_status_reports_control_plane(gateway_config: GatewayConfig) -> None:
    import respx
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    with respx.mock:
        respx.get("http://127.0.0.1:8000/health").respond(200, json={"status": "ok"})
        respx.post("http://127.0.0.1:8000/heartbeat/node").respond(
            200, json={"acknowledged": True}
        )
        async with LifespanManager(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/status")
                assert response.status_code == 200
                body = response.json()
                assert body["control_plane_url"] == "http://127.0.0.1:8000"
                assert body["control_plane_connected"] is True
                assert body["gateway_url"] == "http://127.0.0.1:8080"
