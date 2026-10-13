"""Spawn fails fast when the target puller is missing, stale, or lacks the model."""

from __future__ import annotations

from pathlib import Path

import pytest
import respx
from httpx import ASGITransport, AsyncClient

from gateway.app import create_app
from gateway.config import ControlPlaneSection, GatewayConfig, NodeSection, ServerSection
from gateway.control_plane_client import SHARED_SECRET_HEADER, ControlPlaneClient
from gateway.puller_liveness import PullerUnavailable, check_puller_liveness
from conftest import reviewed_definition, spawn_payload

PULLER_URL = "http://127.0.0.1:8000/pullers"


def _record(
    name: str = "puller-01",
    *,
    models: list[str] | None = None,
    stale: bool = False,
) -> dict[str, object]:
    return {
        "puller_name": name,
        "status": "idle",
        "is_stale": stale,
        "supported_models": ["llama3.1:8b"] if models is None else models,
    }


def test_active_puller_that_lists_the_model_is_ready() -> None:
    check_puller_liveness(
        [_record(), _record("other", models=["other-model"])],
        target_puller="puller-01",
        model="llama3.1:8b",
    )


def test_missing_puller_is_reported() -> None:
    with pytest.raises(PullerUnavailable, match="missing or stale") as exc:
        check_puller_liveness([_record("puller-02")], target_puller="puller-01", model="llama3.1:8b")
    assert "GET /pullers?active_only=true" in str(exc.value)


def test_stale_puller_is_reported() -> None:
    with pytest.raises(PullerUnavailable, match="is stale") as exc:
        check_puller_liveness(
            [_record(stale=True, models=["llama3.1:8b"])],
            target_puller="puller-01",
            model="llama3.1:8b",
        )
    message = str(exc.value)
    assert "missing or stale" not in message
    assert "puller-01" in message


def test_puller_without_the_model_is_reported() -> None:
    with pytest.raises(PullerUnavailable, match="does not list model 'qwen3:8b'") as exc:
        check_puller_liveness(
            [_record(models=["llama3.1:8b"])],
            target_puller="puller-01",
            model="qwen3:8b",
        )
    assert "supported: llama3.1:8b" in str(exc.value)


def test_empty_model_list_is_reported() -> None:
    with pytest.raises(PullerUnavailable, match=r"supported: \(none\)"):
        check_puller_liveness(
            [_record(models=[])],
            target_puller="puller-01",
            model="llama3.1:8b",
        )


def test_stale_wins_over_a_missing_model() -> None:
    with pytest.raises(PullerUnavailable, match="is stale"):
        check_puller_liveness(
            [_record(stale=True, models=[])],
            target_puller="puller-01",
            model="llama3.1:8b",
        )


@pytest.mark.real_pullers
@pytest.mark.asyncio
async def test_list_pullers_uses_active_only_and_shared_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTNET_SHARED_SECRET", "puller-secret")
    client = ControlPlaneClient(ControlPlaneSection(url="http://127.0.0.1:8000"))
    record = _record()
    try:
        with respx.mock(assert_all_called=False) as router:
            listed = router.get(PULLER_URL).respond(200, json=[record])
            wrapped = router.get(PULLER_URL).respond(200, json={"pullers": [record]})
            active = await client.list_pullers(active_only=True)
            assert active == [record]
            active_request = listed.calls.last.request
            assert "active_only=true" in str(active_request.url)
            assert active_request.headers[SHARED_SECRET_HEADER] == "puller-secret"

            monkeypatch.delenv("AGENTNET_SHARED_SECRET", raising=False)
            again = await client.list_pullers(active_only=True)
            assert again == [record]
            quiet = wrapped.calls.last.request
            assert "active_only=true" in str(quiet.url)
            assert SHARED_SECRET_HEADER not in quiet.headers

            all_pullers = router.get(PULLER_URL).respond(204)
            empty = await client.list_pullers(active_only=False)
            assert empty == []
            assert "active_only" not in str(all_pullers.calls.last.request.url)
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


async def _spawn(client: AsyncClient, **payload: object):
    await client.post("/api/definitions", json=reviewed_definition("worker"))
    return await client.post(
        "/api/definitions/worker/spawn",
        json=spawn_payload(mode="autonomous", base_name="worker", auto_start=False, **payload),
    )


@pytest.mark.real_pullers
@pytest.mark.asyncio
async def test_spawn_fails_fast_for_missing_stale_or_unlisted_model(
    gateway_config: GatewayConfig,
) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    cases = [
        ([], "missing or stale"),
        ([_record(stale=True)], "is stale"),
        ([_record(models=["other-model"])], "does not list model 'llama3.1:8b'"),
    ]
    with respx.mock(assert_all_called=False) as router:
        route = router.get(PULLER_URL).respond(200, json=[])
        router.post("http://127.0.0.1:8000/heartbeat/node").respond(200, json={"acknowledged": True})
        async with LifespanManager(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                created = await client.post("/api/definitions", json=reviewed_definition("worker"))
                assert created.status_code == 201
                for body, expected in cases:
                    route.respond(200, json=body)
                    response = await client.post(
                        "/api/definitions/worker/spawn",
                        json=spawn_payload(
                            mode="autonomous",
                            base_name="worker",
                            auto_start=False,
                        ),
                    )
                    assert response.status_code == 409
                    assert expected in response.json()["detail"]
                    assert "active_only=true" in str(route.calls.last.request.url)
                listing = await client.get("/api/fleet/instances")
                assert listing.json()["instances"] == []


@pytest.mark.real_pullers
@pytest.mark.asyncio
async def test_spawn_fails_fast_when_puller_check_cannot_reach_control_plane(
    gateway_config: GatewayConfig,
) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    with respx.mock(assert_all_called=False) as router:
        router.get(PULLER_URL).respond(500, text="control plane down")
        router.post("http://127.0.0.1:8000/heartbeat/node").respond(200, json={"acknowledged": True})
        async with LifespanManager(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await _spawn(client)
                assert response.status_code == 502
                assert response.json()["detail"].startswith("puller liveness check failed:")
                listing = await client.get("/api/fleet/instances")
                assert listing.json()["instances"] == []


@pytest.mark.real_pullers
@pytest.mark.asyncio
async def test_spawn_submits_when_active_puller_lists_the_model(
    gateway_config: GatewayConfig,
) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    with respx.mock(assert_all_called=False) as router:
        route = router.get(PULLER_URL).respond(200, json=[_record()])
        router.post("http://127.0.0.1:8000/heartbeat/node").respond(200, json={"acknowledged": True})
        async with LifespanManager(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await _spawn(client, goal="Write a note")
                assert response.status_code == 201
                assert response.json()["config"]["default_target_puller"] == "puller-01"
                assert response.json()["config"]["default_model"] == "llama3.1:8b"
                assert route.called
                assert "active_only=true" in str(route.calls.last.request.url)
