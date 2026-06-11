"""Tests for agent definitions and instances."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.app import create_app
from gateway.config import ControlPlaneSection, GatewayConfig, NodeSection, ServerSection
from gateway.agent_store import AgentFileKind
from gateway.definition_store import DefinitionStore
from gateway.instance_store import InstanceStore
from shared.markdown_io import default_memory_markdown, default_skills_markdown, parse_markdown_document
from conftest import reviewed_definition, spawn_payload


@pytest.fixture
def roots(tmp_path: Path) -> tuple[Path, Path, Path]:
    agents = tmp_path / "agents"
    definitions = tmp_path / "definitions"
    database = tmp_path / "gateway.db"
    agents.mkdir()
    definitions.mkdir()
    return agents, definitions, database


@pytest.fixture
def gateway_config(roots: tuple[Path, Path, Path]) -> GatewayConfig:
    agents, definitions, database = roots
    return GatewayConfig(
        node=NodeSection(id="test-node"),
        server=ServerSection(host="127.0.0.1", port=8080),
        agents_root=str(agents),
        definitions_root=str(definitions),
        database=str(database),
        control_plane=ControlPlaneSection(url="http://127.0.0.1:8000"),
    )


@pytest.mark.asyncio
async def test_definition_spawn_autonomous(gateway_config: GatewayConfig) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/api/definitions",
                json=reviewed_definition("researcher"),
            )
            assert created.status_code == 201

            spawned = await client.post(
                "/api/definitions/researcher/spawn",
                json=spawn_payload(
                    mode="autonomous",
                    base_name="researcher-04",
                    goal="Summarize test topic.",
                    auto_start=False,
                ),
            )
            assert spawned.status_code == 201
            body = spawned.json()
            assert body["definition_id"] == "researcher"
            assert body["mode"] == "autonomous"
            assert body["instance_id"].startswith("researcher-04-")
            assert body["config"]["default_model"] == "llama3.1:8b"

            fleet = await client.get("/api/fleet/instances")
            assert fleet.status_code == 200
            assert len(fleet.json()["instances"]) == 1


@pytest.mark.asyncio
async def test_spawn_requires_base_name(gateway_config: GatewayConfig) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/definitions", json=reviewed_definition("worker"))
            blocked = await client.post(
                "/api/definitions/worker/spawn",
                json={"mode": "autonomous", "base_name": "", "auto_start": False},
            )
            assert blocked.status_code == 422


@pytest.mark.asyncio
async def test_definition_has_no_spawn_config(gateway_config: GatewayConfig) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/definitions", json=reviewed_definition("writer"))
            detail = await client.get("/api/definitions/writer")
            meta = detail.json()["meta"]
            assert meta["definition_id"] == "writer"
            assert "default_model" not in meta
            assert "default_target_puller" not in meta
            assert "base_name" not in meta


@pytest.mark.asyncio
async def test_definition_spawn_interactive(gateway_config: GatewayConfig) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/definitions", json=reviewed_definition("helper"))
            spawned = await client.post(
                "/api/definitions/helper/spawn",
                json=spawn_payload(mode="interactive", base_name="helper", auto_start=True),
            )
            assert spawned.status_code == 201
            assert spawned.json()["mode"] == "interactive"
            assert spawned.json()["instance_status"] == "interactive_idle"

            poll = await client.get(
                f"/api/fleet/instances/{spawned.json()['instance_id']}/interactive"
            )
            assert poll.status_code == 200
            assert poll.json()["state"] == "interactive_idle"


@pytest.mark.asyncio
async def test_definition_persona_write_and_read(gateway_config: GatewayConfig) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/definitions",
                json=reviewed_definition(
                    "writer",
                    persona_content="---\nname: Writer\n---\n# Custom persona\n",
                ),
            )
            detail = await client.get("/api/definitions/writer")
            assert detail.status_code == 200
            assert "Custom persona" in detail.json()["persona_raw"]

            updated = await client.put(
                "/api/definitions/writer/files/persona",
                json={"content": "---\nname: Writer\n---\n# Updated persona\n"},
            )
            assert updated.status_code == 200
            assert "Updated persona" in updated.json()["persona"]["raw"]


@pytest.mark.asyncio
async def test_spawn_with_instance_persona_override(gateway_config: GatewayConfig) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/definitions",
                json=reviewed_definition(
                    "base",
                    persona_content="---\nname: Base\n---\n# Definition persona\n",
                ),
            )
            spawned = await client.post(
                "/api/definitions/base/spawn",
                json=spawn_payload(
                    mode="autonomous",
                    base_name="base",
                    goal="Do work",
                    auto_start=False,
                    persona_content="---\nname: Base\n---\n# Instance persona\n",
                ),
            )
            assert spawned.status_code == 201
            instance_id = spawned.json()["instance_id"]
            store = InstanceStore(gateway_config.agents_root_path)
            persona = store.read_file(instance_id, AgentFileKind.PERSONA)
            assert "Instance persona" in persona
            definition_persona = gateway_config.definitions_root_path / "base" / "persona.md"
            assert "Definition persona" in definition_persona.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_spawn_copies_memory_from_definition(gateway_config: GatewayConfig) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    memory = default_memory_markdown().replace(
        "(No memories yet.)", "Remember to cite sources."
    )
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/definitions",
                json=reviewed_definition("mem-bot", memory_content=memory),
            )
            spawned = await client.post(
                "/api/definitions/mem-bot/spawn",
                json=spawn_payload(mode="autonomous", base_name="mem-bot", auto_start=False),
            )
            assert spawned.status_code == 201
            store = InstanceStore(gateway_config.agents_root_path)
            instance_memory = store.read_file(spawned.json()["instance_id"], AgentFileKind.MEMORY)
            assert "Remember to cite sources." in instance_memory


@pytest.mark.asyncio
async def test_create_definition_without_memory(gateway_config: GatewayConfig) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/api/definitions",
                json={**reviewed_definition("stateless"), "uses_memory": False},
            )
            assert created.status_code == 201
            assert created.json()["uses_memory"] is False

            detail = await client.get("/api/definitions/stateless")
            assert detail.json()["uses_memory"] is False
            assert detail.json()["memory_raw"] == ""

            memory_path = gateway_config.definitions_root_path / "stateless" / "memory.md"
            assert not memory_path.exists()


@pytest.mark.asyncio
async def test_spawn_without_memory_when_disabled(gateway_config: GatewayConfig) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/definitions",
                json={**reviewed_definition("no-mem"), "uses_memory": False},
            )
            spawned = await client.post(
                "/api/definitions/no-mem/spawn",
                json=spawn_payload(mode="autonomous", base_name="no-mem", auto_start=False),
            )
            assert spawned.status_code == 201
            instance_id = spawned.json()["instance_id"]
            instance_path = gateway_config.agents_root_path / instance_id
            assert not (instance_path / "memory.md").exists()
            config_meta, _ = parse_markdown_document(
                (instance_path / "config.md").read_text(encoding="utf-8")
            )
            assert config_meta.get("uses_memory") is False


@pytest.mark.asyncio
async def test_toggle_definition_uses_memory(gateway_config: GatewayConfig) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/definitions", json=reviewed_definition("toggle"))
            disabled = await client.put(
                "/api/definitions/toggle/uses-memory",
                json={"uses_memory": False},
            )
            assert disabled.status_code == 200
            assert disabled.json()["uses_memory"] is False
            assert not (gateway_config.definitions_root_path / "toggle" / "memory.md").exists()

            enabled = await client.put(
                "/api/definitions/toggle/uses-memory",
                json={"uses_memory": True},
            )
            assert enabled.status_code == 200
            assert enabled.json()["uses_memory"] is True
            assert (gateway_config.definitions_root_path / "toggle" / "memory.md").exists()


@pytest.mark.asyncio
async def test_spawn_with_instance_skills_override(gateway_config: GatewayConfig) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/definitions",
                json=reviewed_definition("skilled", skills_content=default_skills_markdown()),
            )
            spawned = await client.post(
                "/api/definitions/skilled/spawn",
                json=spawn_payload(
                    mode="autonomous",
                    base_name="skilled",
                    auto_start=False,
                    skills_content="---\nversion: 1\n---\n# Skills\n\nInstance-only skill.\n",
                ),
            )
            assert spawned.status_code == 201
            store = InstanceStore(gateway_config.agents_root_path)
            skills = store.read_file(spawned.json()["instance_id"], AgentFileKind.SKILLS)
            assert "Instance-only skill." in skills


@pytest.mark.asyncio
async def test_completions_feed_empty(gateway_config: GatewayConfig) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/fleet/completions/recent")
            assert response.status_code == 200
            assert response.json()["completions"] == []


@pytest.mark.asyncio
async def test_create_definition_requires_review(gateway_config: GatewayConfig) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            blocked = await client.post(
                "/api/definitions", json={"definition_id": "unreviewed"}
            )
            assert blocked.status_code == 422

            created = await client.post(
                "/api/definitions", json=reviewed_definition("reviewed")
            )
            assert created.status_code == 201
            assert created.json()["spawnable"] is True


@pytest.mark.asyncio
async def test_spawn_blocked_until_reviewed(gateway_config: GatewayConfig) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        store = DefinitionStore(gateway_config.definitions_root_path)
        store.create_definition("legacy")
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            blocked = await client.post(
                "/api/definitions/legacy/spawn",
                json=spawn_payload(mode="autonomous", base_name="legacy", auto_start=False),
            )
            assert blocked.status_code == 422

            await client.put(
                "/api/definitions/legacy/files/persona",
                json={"content": store.read_persona_raw("legacy"), "mark_reviewed": True},
            )
            await client.put(
                "/api/definitions/legacy/files/skills",
                json={"content": store.read_skills_raw("legacy"), "mark_reviewed": True},
            )
            spawned = await client.post(
                "/api/definitions/legacy/spawn",
                json=spawn_payload(mode="autonomous", base_name="legacy", auto_start=False),
            )
            assert spawned.status_code == 201


@pytest.mark.asyncio
async def test_definition_registry_lists_from_database(gateway_config: GatewayConfig) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post("/api/definitions", json=reviewed_definition("catalog-bot"))
            assert created.status_code == 201
            listing = await client.get("/api/definitions")
            assert listing.status_code == 200
            items = listing.json()["definitions"]
            assert len(items) == 1
            assert items[0]["definition_id"] == "catalog-bot"
            assert items[0]["spawnable"] is True
            assert items[0]["persona_name"] == "catalog-bot"
            assert gateway_config.database_path.exists()
