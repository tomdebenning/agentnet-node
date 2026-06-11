"""Tests for skills.md in templates and system prompt."""

from __future__ import annotations

from pathlib import Path

from gateway.agent_store import AgentFileKind, AgentStore
from shared.markdown_io import default_skills_markdown, parse_markdown_document, render_markdown_document
from node_agent.markdown_config import load_agent_settings, render_system_prompt


def test_create_agent_includes_skills(tmp_path: Path) -> None:
    store = AgentStore(tmp_path / "agents")
    store.create_agent("worker")
    skills = store.read_file("worker", AgentFileKind.SKILLS)
    assert "# Skills" in skills


def test_skills_in_system_prompt(tmp_path: Path) -> None:
    store = AgentStore(tmp_path / "agents")
    store.create_agent("worker")
    skills_path = store.agent_dir("worker") / "skills.md"
    skills_path.write_text(
        render_markdown_document({}, "# Skills\n\nAlways cite sources.\n"),
        encoding="utf-8",
    )
    settings = load_agent_settings(store.agent_dir("worker"))
    prompt = render_system_prompt(settings)
    assert "## Skills" in prompt
    assert "Always cite sources." in prompt


def test_legacy_agent_without_skills(tmp_path: Path) -> None:
    store = AgentStore(tmp_path / "agents")
    store.create_agent("legacy")
    (store.agent_dir("legacy") / "skills.md").unlink()
    settings = load_agent_settings(store.agent_dir("legacy"))
    prompt = render_system_prompt(settings)
    assert "## Skills" not in prompt


def test_agent_without_memory_omits_memory_section(tmp_path: Path) -> None:
    store = AgentStore(tmp_path / "agents")
    store.create_agent("stateless")
    config_path = store.agent_dir("stateless") / "config.md"
    meta, body = parse_markdown_document(config_path.read_text(encoding="utf-8"))
    meta["uses_memory"] = False
    config_path.write_text(render_markdown_document(meta, body), encoding="utf-8")
    (store.agent_dir("stateless") / "memory.md").unlink()

    settings = load_agent_settings(store.agent_dir("stateless"))
    assert settings.uses_memory is False
    prompt = render_system_prompt(settings)
    assert "## Persistent memory" not in prompt


def test_tools_for_agent_without_memory() -> None:
    from node_agent.tools.definitions import tools_for_agent

    names = {tool.function.get("name") for tool in tools_for_agent(uses_memory=False)}
    assert "read_memory" not in names
    assert "write_memory" not in names
    assert "set_plan" in names
