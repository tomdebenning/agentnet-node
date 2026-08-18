"""On-disk builder definition is a software worker, not a newsroom desk."""

from __future__ import annotations

import json
from pathlib import Path

from node_agent.session_worker import BUILDER_DEFINITION, BUILDER_PULLER_NAME, resolve_builder_target
from shared.markdown_io import parse_markdown_document

REPO = Path(__file__).resolve().parents[1]
BUILDER = REPO / "definitions" / "builder"


def test_builder_definition_is_spawnable_with_memory() -> None:
    meta = json.loads((BUILDER / "meta.json").read_text(encoding="utf-8"))
    assert meta["definition_id"] == "builder"
    assert meta["uses_memory"] is True
    assert meta["persona_reviewed"] is True
    assert meta["skills_reviewed"] is True
    assert meta["spawnable"] is True
    assert (BUILDER / "memory.md").exists()
    assert (BUILDER / "persona.md").exists()
    assert (BUILDER / "skills.md").exists()


def test_builder_persona_is_software_not_newsroom() -> None:
    persona = (BUILDER / "persona.md").read_text(encoding="utf-8")
    skills = (BUILDER / "skills.md").read_text(encoding="utf-8")
    assert "software" in persona.lower()
    assert "run_command" in skills
    assert "newsroom" in persona.lower()
    assert "not" in persona.lower()
    assert "edition" not in skills.lower()
    assert "reporter" not in persona.lower()
    assert "editor" not in persona.lower()


def test_builder_config_keeps_llm_on_factory_puller() -> None:
    meta, _ = parse_markdown_document((BUILDER / "config.md").read_text(encoding="utf-8"))
    assert meta["default_target_puller"] == "puller-01"
    assert meta["template_id"] == "builder"


def test_session_target_defaults_builder_puller() -> None:
    assert resolve_builder_target(definition="builder", target_puller=None) == BUILDER_PULLER_NAME
    assert resolve_builder_target(definition=BUILDER_DEFINITION, target_puller="gpu-01") == "gpu-01"
    assert resolve_builder_target(definition=None, target_puller=None) == "puller-01"
