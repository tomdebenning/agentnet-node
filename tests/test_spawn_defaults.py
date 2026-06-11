"""Tests for spawn defaults and run options."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.app import create_app
from gateway.config import ControlPlaneSection, GatewayConfig, NodeSection, ServerSection, SpawnDefaultsSection
from conftest import reviewed_definition, spawn_payload


@pytest.fixture
def roots(tmp_path: Path) -> tuple[Path, Path]:
    agents = tmp_path / "agents"
    definitions = tmp_path / "definitions"
    agents.mkdir()
    definitions.mkdir()
    return agents, definitions


@pytest.fixture
def gateway_config(roots: tuple[Path, Path], tmp_path: Path) -> GatewayConfig:
    agents, definitions = roots
    return GatewayConfig(
        node=NodeSection(id="test-node"),
        server=ServerSection(host="127.0.0.1", port=8080),
        agents_root=str(agents),
        definitions_root=str(definitions),
        database=str(tmp_path / "gateway.db"),
        spawn_defaults=SpawnDefaultsSection(
            model="custom-model",
            target_puller="puller-99",
            temperature=0.3,
            num_ctx=4096,
        ),
        control_plane=ControlPlaneSection(url="http://127.0.0.1:8000"),
    )


@pytest.mark.asyncio
async def test_spawn_defaults_api(gateway_config: GatewayConfig) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/spawn-defaults")
            assert response.status_code == 200
            body = response.json()
            assert body["model"] == "custom-model"
            assert body["target_puller"] == "puller-99"
            assert body["temperature"] == 0.3
            assert body["num_ctx"] == 4096


@pytest.mark.asyncio
async def test_spawn_uses_config_defaults(gateway_config: GatewayConfig) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/definitions", json=reviewed_definition("worker"))
            spawned = await client.post(
                "/api/definitions/worker/spawn",
                json={
                    "mode": "autonomous",
                    "base_name": "worker",
                    "auto_start": False,
                },
            )
            assert spawned.status_code == 201
            body = spawned.json()
            assert body["config"]["default_model"] == "custom-model"
            assert body["config"]["default_target_puller"] == "puller-99"
            assert body["config"]["temperature"] == 0.3
            assert body["current_run"]["run"]["options"]["temperature"] == 0.3


@pytest.mark.asyncio
async def test_start_run_accepts_temperature(gateway_config: GatewayConfig) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/definitions", json=reviewed_definition("writer"))
            spawned = await client.post(
                "/api/definitions/writer/spawn",
                json=spawn_payload(mode="interactive", base_name="writer", auto_start=False),
            )
            instance_id = spawned.json()["instance_id"]
            new_run = await client.post(
                f"/api/fleet/instances/{instance_id}/runs",
                json={"goal": "Draft outline", "temperature": 0.9},
            )
            assert new_run.status_code == 201
            assert new_run.json()["run"]["options"]["temperature"] == 0.9
