"""Shared test helpers."""

from __future__ import annotations

REVIEWED_FLAGS = {"persona_reviewed": True, "skills_reviewed": True}


def reviewed_definition(definition_id: str, **kwargs: object) -> dict[str, object]:
    return {"definition_id": definition_id, **REVIEWED_FLAGS, **kwargs}


def spawn_payload(**kwargs: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "base_name": "test-inst",
        "target_puller": "puller-01",
        "model": "llama3.1:8b",
    }
    return {**defaults, **kwargs}
