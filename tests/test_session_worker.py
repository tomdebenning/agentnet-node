"""Builder session worker helpers."""

from __future__ import annotations

from pathlib import Path

from shared.markdown_io import parse_markdown_document
from shared.schemas import Message, Task
from node_agent.session_worker import (
    DEFAULT_AGENT_ID,
    _ensure_builder_instance,
    _goal_from_task,
)


def test_goal_from_task_uses_first_user_message() -> None:
    task = Task(
        agent_id="harness-1",
        conversation_id="conv-1",
        round=1,
        target_puller="builder-01",
        model="llama3.1:8b",
        messages=[
            Message(role="system", content="ignore"),
            Message(role="user", content="  Ship the health route  "),
        ],
        submitted_at="2026-08-18T00:00:00Z",
    )
    assert _goal_from_task(task) == "Ship the health route"


def test_ensure_builder_instance_copies_memory(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    instance = _ensure_builder_instance(
        agents_root=tmp_path / "agents",
        definitions_root=repo / "definitions",
        agent_id=DEFAULT_AGENT_ID,
        llm_puller="puller-01",
        model="llama3.1:8b",
    )
    assert instance.name == "builder-01"
    assert (instance / "memory.md").exists()
    assert (instance / "persona.md").exists()
    assert (instance / "workspace").is_dir()
    meta, _ = parse_markdown_document((instance / "config.md").read_text(encoding="utf-8"))
    assert meta["default_target_puller"] == "puller-01"
    assert meta["agent_id"] == "builder-01"
    # Second call keeps memory and does not clobber it.
    (instance / "memory.md").write_text("---\n---\n# Memory\n\nkept\n", encoding="utf-8")
    _ensure_builder_instance(
        agents_root=tmp_path / "agents",
        definitions_root=repo / "definitions",
        agent_id=DEFAULT_AGENT_ID,
        llm_puller="puller-01",
        model="llama3.1:8b",
    )
    assert "kept" in (instance / "memory.md").read_text(encoding="utf-8")
