"""Tests for empty startup and resilient instance loading."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.app import create_app
from gateway.config import ControlPlaneSection, GatewayConfig, NodeSection, ServerSection


@pytest.fixture
def empty_roots(tmp_path: Path) -> tuple[Path, Path]:
    agents = tmp_path / "agents"
    definitions = tmp_path / "definitions"
    agents.mkdir()
    definitions.mkdir()
    return agents, definitions


@pytest.fixture
def empty_config(empty_roots: tuple[Path, Path]) -> GatewayConfig:
    agents, definitions = empty_roots
    return GatewayConfig(
        node=NodeSection(id="test-node"),
        server=ServerSection(host="127.0.0.1", port=8080),
        agents_root=str(agents),
        definitions_root=str(definitions),
        control_plane=ControlPlaneSection(url="http://127.0.0.1:8000"),
    )


@pytest.mark.asyncio
async def test_empty_startup_lists_zero_instances(empty_config: GatewayConfig) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(empty_config)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            status = await client.get("/api/status")
            assert status.status_code == 200
            body = status.json()
            assert body["instance_count"] == 0
            assert body["definition_count"] == 0

            instances = await client.get("/api/fleet/instances")
            assert instances.status_code == 200
            assert instances.json()["instances"] == []


@pytest.mark.asyncio
async def test_create_definition_on_empty_startup(empty_config: GatewayConfig) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(empty_config)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/api/definitions",
                json={
                    "definition_id": "helper",
                    "persona_reviewed": True,
                    "skills_reviewed": True,
                },
            )
            assert created.status_code == 201

            status = await client.get("/api/status")
            assert status.json()["definition_count"] == 1
            assert status.json()["instance_count"] == 0
