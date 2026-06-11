"""Load agent configuration from Markdown files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shared.markdown_io import parse_markdown_document


def _read_task_markdown(agent_dir: Path) -> tuple[dict, str]:
    task_path = agent_dir / "task.md"
    if not task_path.exists():
        return {"conversation_id": "task"}, ""
    return parse_markdown_document(task_path.read_text(encoding="utf-8"))


def _read_optional_markdown(agent_dir: Path, filename: str) -> str:
    path = agent_dir / filename
    if not path.exists():
        return ""
    _, body = parse_markdown_document(path.read_text(encoding="utf-8"))
    return body.strip()


@dataclass
class AgentPaths:
    root: Path
    config_file: Path
    persona_file: Path
    skills_file: Path
    memory_file: Path
    workspace_root: Path
    sqlite_root: Path
    conversation_db: Path


@dataclass
class AgentSettings:
    agent_id: str
    default_target_puller: str
    default_model: str
    temperature: float
    num_ctx: int
    max_rounds_per_conversation: int
    response_poll_interval_seconds: float
    response_timeout_seconds: float
    persona_name: str
    persona_role: str
    persona_body: str
    skills_body: str
    memory_body: str
    uses_memory: bool
    task_body: str
    task_conversation_id: str
    paths: AgentPaths


def load_agent_settings(agent_dir: Path) -> AgentSettings:
    agent_dir = agent_dir.expanduser().resolve()
    config_meta, _ = parse_markdown_document((agent_dir / "config.md").read_text(encoding="utf-8"))
    persona_meta, persona_body = parse_markdown_document(
        (agent_dir / "persona.md").read_text(encoding="utf-8")
    )
    uses_memory = bool(config_meta.get("uses_memory", True))
    memory_path = agent_dir / "memory.md"
    if uses_memory and memory_path.exists():
        _, memory_body = parse_markdown_document(memory_path.read_text(encoding="utf-8"))
    else:
        memory_body = ""
    task_meta, task_body = _read_task_markdown(agent_dir)

    agent_id = str(config_meta.get("agent_id") or agent_dir.name)
    paths = AgentPaths(
        root=agent_dir,
        config_file=agent_dir / "config.md",
        persona_file=agent_dir / "persona.md",
        skills_file=agent_dir / "skills.md",
        memory_file=agent_dir / "memory.md",
        workspace_root=agent_dir / "workspace",
        sqlite_root=agent_dir / "databases",
        conversation_db=agent_dir / "agent_state.db",
    )
    paths.workspace_root.mkdir(parents=True, exist_ok=True)
    paths.sqlite_root.mkdir(parents=True, exist_ok=True)

    return AgentSettings(
        agent_id=agent_id,
        default_target_puller=str(config_meta.get("default_target_puller") or "puller-01"),
        default_model=str(config_meta.get("default_model") or "llama3.1:8b"),
        temperature=float(config_meta.get("temperature") or 0.7),
        num_ctx=int(config_meta.get("num_ctx") or 8192),
        max_rounds_per_conversation=int(config_meta.get("max_rounds_per_conversation") or 50),
        response_poll_interval_seconds=float(
            config_meta.get("response_poll_interval_seconds") or 2
        ),
        response_timeout_seconds=float(config_meta.get("response_timeout_seconds") or 300),
        persona_name=str(persona_meta.get("name") or agent_id),
        persona_role=str(persona_meta.get("role") or "assistant"),
        persona_body=persona_body.strip(),
        skills_body=_read_optional_markdown(agent_dir, "skills.md"),
        memory_body=memory_body.strip(),
        uses_memory=uses_memory,
        task_body=task_body.strip(),
        task_conversation_id=str(task_meta.get("conversation_id") or "task"),
        paths=paths,
    )


def render_system_prompt(settings: AgentSettings) -> str:
    memory_section = ""
    if settings.uses_memory:
        memory_body = settings.memory_body or "(empty memory)"
        memory_section = f"\n\n## Persistent memory\n\n{memory_body}\n"
    skills_section = ""
    if settings.skills_body:
        skills_section = f"\n\n## Skills\n\n{settings.skills_body}\n"
    return (
        f"You are {settings.persona_name}, a {settings.persona_role}.\n\n"
        f"{settings.persona_body}\n"
        f"{skills_section}\n"
        f"{memory_section}"
        "\n## Run workflow\n\n"
        "Each run has one goal. Use set_plan to outline steps, advance_step when a step "
        "is complete, and mark_goal_done with existing artifact id(s) when the goal is "
        "finished. File and database writes are recorded automatically as artifacts for "
        "the current step. Use send_artifact_to_agent to hand an artifact to another agent.\n"
    )


def llm_options(settings: AgentSettings) -> dict[str, Any]:
    return {"temperature": settings.temperature, "num_ctx": settings.num_ctx}


def llm_options_for_run(settings: AgentSettings, run_options: dict[str, Any]) -> dict[str, Any]:
    merged = llm_options(settings)
    for key in ("temperature", "num_ctx"):
        if key in run_options:
            merged[key] = run_options[key]
    return merged


def task_user_prompt(settings: AgentSettings) -> str:
    """Markdown body of task.md — the user message for a managed start."""
    return settings.task_body.strip()
