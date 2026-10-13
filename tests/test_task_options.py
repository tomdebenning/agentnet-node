"""Tests for chat defaults and the opt-in grading profile."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.agent_store import AgentStore
from gateway.app import create_app
from gateway.config import ControlPlaneSection, GatewayConfig, NodeSection, ServerSection
from node_agent.conversation import run_conversation_turn
from node_agent.conversation_store import ConversationStore
from node_agent.markdown_config import llm_options, llm_options_for_run, load_agent_settings
from node_agent.run_tools import RunToolContext
from node_agent.task_options import (
    GRADING_SEED,
    UnknownTaskProfile,
    grading_task_options,
    resolve_task_options,
)
from node_agent.tools.registry import ToolRegistry
from shared.run_store import RunStore
from shared.schemas import Message, Response
from conftest import reviewed_definition, spawn_payload


def _settings(tmp_path: Path, *, temperature: float = 0.7):
    store = AgentStore(tmp_path / "agents")
    store.create_agent("worker", temperature=temperature, num_ctx=8192)
    return load_agent_settings(store.agent_dir("worker"))


def test_chat_default_temperature_is_unchanged(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    assert settings.temperature == 0.7
    options = llm_options(settings)
    assert options == {"temperature": 0.7, "num_ctx": 8192}
    resolved = llm_options_for_run(settings, {})
    assert resolved == {"temperature": 0.7, "num_ctx": 8192}
    assert "seed" not in resolved
    assert "think" not in resolved
    assert "profile" not in resolved


def test_task_can_override_temperature_without_profile(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    resolved = llm_options_for_run(settings, {"temperature": 0.2, "num_ctx": 2048})
    assert resolved == {"temperature": 0.2, "num_ctx": 2048}
    zero = llm_options_for_run(settings, {"temperature": 0})
    assert zero["temperature"] == 0
    assert "seed" not in zero
    assert "think" not in zero


@pytest.mark.parametrize("profile", ["grading", "deterministic", " Grading ", "DETERMINISTIC"])
def test_grading_profile_sets_deterministic_task_options(tmp_path: Path, profile: str) -> None:
    settings = _settings(tmp_path, temperature=0.7)
    resolved = llm_options_for_run(
        settings,
        {"temperature": 0.4, "num_ctx": 4096},
        profile=profile,
    )
    assert resolved["temperature"] == 0
    assert resolved["seed"] == GRADING_SEED
    assert resolved["think"] is False
    assert resolved["num_ctx"] == 4096
    assert "profile" not in resolved
    assert grading_task_options() == {"temperature": 0, "seed": GRADING_SEED, "think": False}


def test_profile_in_run_options_opts_in(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    resolved = resolve_task_options(
        temperature=settings.temperature,
        num_ctx=settings.num_ctx,
        run_options={"profile": "grading", "num_ctx": 1024},
    )
    assert resolved == {
        "temperature": 0,
        "num_ctx": 1024,
        "seed": GRADING_SEED,
        "think": False,
    }


def test_explicit_profile_argument_wins_over_run_options(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    resolved = llm_options_for_run(settings, {"profile": "chatty"}, profile="grading")
    assert resolved["temperature"] == 0
    assert resolved["think"] is False


def test_unknown_profile_is_rejected(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with pytest.raises(UnknownTaskProfile, match="unknown task profile"):
        llm_options_for_run(settings, {}, profile="creative")
    with pytest.raises(UnknownTaskProfile):
        resolve_task_options(temperature=0.7, num_ctx=8192, run_options={"profile": "fast"})


def test_blank_profile_keeps_chat_defaults(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    resolved = llm_options_for_run(settings, {"profile": "  "})
    assert resolved == {"temperature": 0.7, "num_ctx": 8192}


class _RecordingGateway:
    def __init__(self) -> None:
        self.tasks = []

    async def post_task(self, task) -> dict:
        self.tasks.append(task)
        return {}

    async def get_responses(self, agent_id: str, max: int = 10) -> list[Response]:
        task = self.tasks[-1]
        return [
            Response(
                agent_id=agent_id,
                conversation_id=task.conversation_id,
                round=task.round,
                puller_name="puller-01",
                message=Message(role="assistant", content="ok"),
                completed_at="2026-01-01T00:00:00Z",
            )
        ]


@pytest.mark.asyncio
async def test_conversation_turn_uses_chat_defaults(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    gateway = _RecordingGateway()
    store = ConversationStore(settings.paths.conversation_db)
    await store.connect()
    tools = ToolRegistry(settings, gateway, conversation_id="task")  # type: ignore[arg-type]
    reply = await run_conversation_turn(
        settings=settings,
        gateway=gateway,  # type: ignore[arg-type]
        store=store,
        tools=tools,
        conversation_id="task",
        user_input="hello",
    )
    assert reply == "ok"
    assert gateway.tasks[0].options == {"temperature": 0.7, "num_ctx": 8192}


@pytest.mark.asyncio
async def test_conversation_turn_opts_into_grading_profile(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    gateway = _RecordingGateway()
    store = ConversationStore(settings.paths.conversation_db)
    await store.connect()
    tools = ToolRegistry(settings, gateway, conversation_id="task")  # type: ignore[arg-type]
    await run_conversation_turn(
        settings=settings,
        gateway=gateway,  # type: ignore[arg-type]
        store=store,
        tools=tools,
        conversation_id="task",
        user_input="grade this",
        run_options={"temperature": 0.9, "num_ctx": 8192},
        profile="deterministic",
    )
    options = gateway.tasks[0].options
    assert options["temperature"] == 0
    assert options["seed"] == GRADING_SEED
    assert options["think"] is False
    assert options["num_ctx"] == 8192


@pytest.mark.asyncio
async def test_handoff_opts_into_grading_and_defaults_to_chat(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    gateway = _RecordingGateway()
    context = RunToolContext(settings=settings, gateway=gateway, conversation_id="task")  # type: ignore[arg-type]
    run_store = RunStore(settings.paths.root)
    run_store.create_run("task", goal="grade")
    artifact = run_store.record_artifact(
        "task",
        artifact_type="file",
        summary="notes",
        ref={"path": "notes.md"},
    )
    await context.send_artifact_to_agent("other", artifact.artifact_id, "review")
    assert gateway.tasks[0].options == {"temperature": 0.7, "num_ctx": 8192}

    await context.send_artifact_to_agent(
        "other",
        artifact.artifact_id,
        "grade",
        profile="grading",
    )
    graded = gateway.tasks[1].options
    assert graded["temperature"] == 0
    assert graded["seed"] == GRADING_SEED
    assert graded["think"] is False


@pytest.fixture
def gateway_config(tmp_path: Path) -> GatewayConfig:
    agents = tmp_path / "agents"
    definitions = tmp_path / "definitions"
    agents.mkdir()
    definitions.mkdir()
    return GatewayConfig(
        node=NodeSection(id="test-node"),
        server=ServerSection(host="127.0.0.1", port=8080),
        agents_root=str(agents),
        definitions_root=str(definitions),
        database=str(tmp_path / "gateway.db"),
        control_plane=ControlPlaneSection(url="http://127.0.0.1:8000"),
    )


@pytest.mark.asyncio
async def test_spawn_and_new_run_can_opt_into_grading(gateway_config: GatewayConfig) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/definitions", json=reviewed_definition("writer"))
            plain = await client.post(
                "/api/definitions/writer/spawn",
                json=spawn_payload(mode="interactive", base_name="writer", auto_start=False),
            )
            assert plain.status_code == 201
            plain_options = plain.json()["current_run"]["run"]["options"]
            assert plain_options["temperature"] == 0.7
            assert "profile" not in plain_options
            assert "seed" not in plain_options
            assert "think" not in plain_options

            graded = await client.post(
                "/api/definitions/writer/spawn",
                json=spawn_payload(
                    mode="interactive",
                    base_name="grader",
                    auto_start=False,
                    profile="grading",
                    temperature=0.8,
                ),
            )
            assert graded.status_code == 201
            body = graded.json()
            assert body["config"]["temperature"] == 0.8
            stored = body["current_run"]["run"]["options"]
            assert stored["profile"] == "grading"
            assert stored["temperature"] == 0.8

            instance_id = body["instance_id"]
            new_run = await client.post(
                f"/api/fleet/instances/{instance_id}/runs",
                json={"goal": "Score the essay", "profile": "deterministic", "temperature": 0.5},
            )
            assert new_run.status_code == 201
            run_options = new_run.json()["run"]["options"]
            assert run_options["profile"] == "deterministic"
            assert run_options["temperature"] == 0.5
            task_options = resolve_task_options(
                temperature=0.8,
                num_ctx=8192,
                run_options=run_options,
            )
            assert task_options["temperature"] == 0
            assert task_options["seed"] == GRADING_SEED
            assert task_options["think"] is False

            rejected = await client.post(
                "/api/definitions/writer/spawn",
                json=spawn_payload(
                    mode="interactive",
                    base_name="bad-profile",
                    auto_start=False,
                    profile="creative",
                ),
            )
            assert rejected.status_code == 422
            assert "unknown task profile" in rejected.json()["detail"]
