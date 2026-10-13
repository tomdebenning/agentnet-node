"""Optional X-AgentNet-Secret header on control-plane calls."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient

from gateway.app import create_app
from gateway.config import ControlPlaneSection, GatewayConfig, NodeSection, ServerSection
from gateway.control_plane_client import (
    SHARED_SECRET_HEADER,
    ControlPlaneClient,
    shared_secret_headers,
)
from shared.schemas import AgentHeartbeat, Message, NodeHeartbeat, Task


def _task() -> Task:
    return Task(
        agent_id="agent-1",
        conversation_id="conv-1",
        round=1,
        target_puller="puller-01",
        model="llama3.1:8b",
        messages=[Message(role="user", content="hi")],
        submitted_at="2026-01-01T00:00:00Z",
    )


def _header(request: httpx.Request) -> str | None:
    return request.headers.get(SHARED_SECRET_HEADER)


def test_shared_secret_header_absent_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENTNET_SHARED_SECRET", raising=False)
    assert shared_secret_headers() == {}
    monkeypatch.setenv("AGENTNET_SHARED_SECRET", "   ")
    assert shared_secret_headers() == {}


def test_shared_secret_header_uses_stripped_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTNET_SHARED_SECRET", "  top-secret  ")
    assert shared_secret_headers() == {SHARED_SECRET_HEADER: "top-secret"}


@pytest.mark.asyncio
async def test_every_control_plane_call_omits_header_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGENTNET_SHARED_SECRET", raising=False)
    config = ControlPlaneSection(url="http://127.0.0.1:8000")
    client = ControlPlaneClient(config)
    try:
        with respx.mock(assert_all_called=False) as router:
            tasks = router.post("http://127.0.0.1:8000/tasks").respond(202, json={})
            responses = router.get("http://127.0.0.1:8000/responses").respond(204)
            agent_hb = router.post("http://127.0.0.1:8000/heartbeat/agent").respond(
                200, json={"acknowledged": True}
            )
            node_hb = router.post("http://127.0.0.1:8000/heartbeat/node").respond(
                200, json={"acknowledged": True}
            )
            health = router.get("http://127.0.0.1:8000/health").respond(200, json={"status": "ok"})

            await client.post_task(_task())
            await client.get_responses("agent-1", max=1)
            await client.post_agent_heartbeat(AgentHeartbeat(agent_id="agent-1", status="idle"))
            await client.post_node_heartbeat(NodeHeartbeat(node_id="node-01", status="idle"))
            ok, error = await client.check_health()

            assert ok is True
            assert error is None
            for route in (tasks, responses, agent_hb, node_hb, health):
                assert route.called
                assert _header(route.calls.last.request) is None
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_every_control_plane_call_sends_secret_when_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = ControlPlaneSection(url="http://127.0.0.1:8000")
    client = ControlPlaneClient(config)
    monkeypatch.setenv("AGENTNET_SHARED_SECRET", "node-secret")
    try:
        with respx.mock(assert_all_called=False) as router:
            tasks = router.post("http://127.0.0.1:8000/tasks").respond(202, json={"queued": True})
            responses = router.get("http://127.0.0.1:8000/responses").respond(
                200,
                json={
                    "responses": [
                        {
                            "agent_id": "agent-1",
                            "conversation_id": "conv-1",
                            "round": 1,
                            "puller_name": "puller-01",
                            "message": {"role": "assistant", "content": "ok"},
                            "completed_at": "2026-01-01T00:00:01Z",
                        }
                    ]
                },
            )
            agent_hb = router.post("http://127.0.0.1:8000/heartbeat/agent").respond(
                200, json={"acknowledged": True}
            )
            node_hb = router.post("http://127.0.0.1:8000/heartbeat/node").respond(
                200, json={"acknowledged": True}
            )
            health = router.get("http://127.0.0.1:8000/health").respond(200, json={"status": "ok"})

            await client.post_task(_task())
            found = await client.get_responses("agent-1", max=1)
            await client.post_agent_heartbeat(AgentHeartbeat(agent_id="agent-1", status="working"))
            await client.post_node_heartbeat(NodeHeartbeat(node_id="node-01", status="busy"))
            ok, _error = await client.check_health()

            assert ok is True
            assert found[0].message is not None
            assert found[0].message.content == "ok"
            for route in (tasks, responses, agent_hb, node_hb, health):
                assert _header(route.calls.last.request) == "node-secret"
    finally:
        await client.aclose()


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
async def test_proxy_task_forwards_secret_only_when_configured(
    gateway_config: GatewayConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    payload = _task().model_dump(mode="json")
    with respx.mock(assert_all_called=False) as router:
        tasks = router.post("http://127.0.0.1:8000/tasks").respond(202, json={})
        router.post("http://127.0.0.1:8000/heartbeat/node").respond(200, json={"acknowledged": True})
        async with LifespanManager(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                monkeypatch.delenv("AGENTNET_SHARED_SECRET", raising=False)
                unset = await client.post("/proxy/tasks", json=payload)
                assert unset.status_code == 202
                assert _header(tasks.calls.last.request) is None

                monkeypatch.setenv("AGENTNET_SHARED_SECRET", "from-proxy")
                sent = await client.post("/proxy/tasks", json=payload)
                assert sent.status_code == 202
                assert _header(tasks.calls.last.request) == "from-proxy"
