"""Tests for task.md loading."""

from __future__ import annotations

from pathlib import Path

from gateway.agent_store import AgentStore
from node_agent.markdown_config import load_agent_settings, task_user_prompt


def test_task_prompt_from_body(tmp_path: Path) -> None:
    store = AgentStore(tmp_path / "agents")
    store.create_agent("worker")
    settings = load_agent_settings(store.agent_dir("worker"))
    assert settings.task_conversation_id == "task"
    assert "Describe what this agent should do" in task_user_prompt(settings)

    task_path = store.agent_dir("worker") / "task.md"
    task_path.write_text(
        "---\nconversation_id: job-1\n---\nSummarize the notes in workspace.\n",
        encoding="utf-8",
    )
    settings2 = load_agent_settings(store.agent_dir("worker"))
    assert settings2.task_conversation_id == "job-1"
    assert task_user_prompt(settings2) == "Summarize the notes in workspace."
