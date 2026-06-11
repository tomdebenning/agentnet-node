"""Tests for run store and run API."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.app import create_app
from gateway.config import ControlPlaneSection, GatewayConfig, NodeSection, ServerSection
from shared.markdown_io import default_skills_markdown
from conftest import reviewed_definition, spawn_payload
from shared.run_store import RunStatus, RunStore


@pytest.fixture
def roots(tmp_path: Path) -> tuple[Path, Path]:
    agents = tmp_path / "agents"
    templates = tmp_path / "definitions"
    agents.mkdir()
    templates.mkdir()
    return agents, templates


@pytest.fixture
def gateway_config(roots: tuple[Path, Path], tmp_path: Path) -> GatewayConfig:
    agents, templates = roots
    return GatewayConfig(
        node=NodeSection(id="test-node"),
        server=ServerSection(host="127.0.0.1", port=8080),
        agents_root=str(agents),
        definitions_root=str(templates),
        database=str(tmp_path / "gateway.db"),
        control_plane=ControlPlaneSection(url="http://127.0.0.1:8000"),
    )


def test_run_store_create_and_artifact(tmp_path: Path) -> None:
    instance_dir = tmp_path / "bot"
    instance_dir.mkdir()
    store = RunStore(instance_dir)
    store.create_run("run-1", goal="Write a blog post")
    store.set_plan_steps("run-1", [{"id": "research", "title": "Research topic"}])
    artifact = store.record_artifact(
        "run-1",
        artifact_type="file",
        summary="outline",
        ref={"path": "outline.md"},
    )
    store.mark_goal_done("run-1", [artifact.artifact_id])
    run = store.get_run("run-1")
    assert run.goal == "Write a blog post"
    assert run.status == RunStatus.DONE
    products = store.get_products("run-1")
    assert products.product_artifact_ids == [artifact.artifact_id]


@pytest.mark.asyncio
async def test_spawn_creates_run_with_goal(gateway_config: GatewayConfig) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/api/definitions",
                json=reviewed_definition("writer", skills_content=default_skills_markdown()),
            )
            assert created.status_code == 201

            spawned = await client.post(
                "/api/definitions/writer/spawn",
                json=spawn_payload(
                    mode="autonomous",
                    base_name="writer-01",
                    goal="Draft a short blog post about testing.",
                    auto_start=False,
                ),
            )
            assert spawned.status_code == 201
            body = spawned.json()
            instance_id = body["instance_id"]
            assert body["current_run"] is not None
            assert body["current_run"]["run"]["goal"] == "Draft a short blog post about testing."

            current = await client.get(f"/api/fleet/instances/{instance_id}/runs/current")
            assert current.status_code == 200
            assert current.json()["run"]["status"] == "pending"

            runs = await client.get(f"/api/fleet/instances/{instance_id}/runs")
            assert runs.status_code == 200
            assert len(runs.json()["runs"]) == 1


@pytest.mark.asyncio
async def test_spawn_task_body_fallback_as_goal(gateway_config: GatewayConfig) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/definitions",
                json=reviewed_definition("worker"),
            )
            spawned = await client.post(
                "/api/definitions/worker/spawn",
                json=spawn_payload(
                    mode="interactive",
                    base_name="worker-01",
                    task_body="Plan a release checklist.",
                ),
            )
            assert spawned.status_code == 201
            assert spawned.json()["current_run"]["run"]["goal"] == "Plan a release checklist."
