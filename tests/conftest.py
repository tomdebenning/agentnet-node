"""Shared test helpers."""

from __future__ import annotations

from typing import Any

import pytest

from gateway.control_plane_client import ControlPlaneClient

REVIEWED_FLAGS = {"persona_reviewed": True, "skills_reviewed": True}

# Models and pullers referenced by existing spawn tests.
_STUB_PULLERS: list[dict[str, Any]] = [
    {
        "puller_name": "puller-01",
        "status": "idle",
        "is_stale": False,
        "supported_models": ["llama3.1:8b", "custom-model"],
    },
    {
        "puller_name": "puller-99",
        "status": "idle",
        "is_stale": False,
        "supported_models": ["llama3.1:8b", "custom-model"],
    },
]


@pytest.fixture(autouse=True)
def _stub_active_pullers(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """Keep spawn tests off the network unless they opt into the real client.

    Production spawn calls ``GET /pullers?active_only=true``. Tests marked
    ``real_pullers`` exercise that HTTP call; everything else gets a healthy
    puller so older spawn cases stay focused on their own behavior.
    """
    if request.node.get_closest_marker("real_pullers"):
        return

    async def list_pullers(
        self: ControlPlaneClient, *, active_only: bool = True
    ) -> list[dict[str, Any]]:
        del self
        if active_only is not True:
            raise AssertionError("spawn liveness checks request active pullers only")
        return [
            {
                "puller_name": item["puller_name"],
                "status": item["status"],
                "is_stale": item["is_stale"],
                "supported_models": list(item["supported_models"]),
            }
            for item in _STUB_PULLERS
        ]

    monkeypatch.setattr(ControlPlaneClient, "list_pullers", list_pullers)


def reviewed_definition(definition_id: str, **kwargs: object) -> dict[str, object]:
    return {"definition_id": definition_id, **REVIEWED_FLAGS, **kwargs}


def spawn_payload(**kwargs: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "base_name": "test-inst",
        "target_puller": "puller-01",
        "model": "llama3.1:8b",
    }
    return {**defaults, **kwargs}
