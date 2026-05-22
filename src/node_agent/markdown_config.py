"""Load agent configuration from Markdown files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gateway.markdown_io import parse_markdown_document


@dataclass
class AgentPaths:
    root: Path
    config_file: Path
    persona_file: Path
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
    memory_body: str
    paths: AgentPaths


def load_agent_settings(agent_dir: Path) -> AgentSettings:
    agent_dir = agent_dir.expanduser().resolve()
    config_meta, _ = parse_markdown_document((agent_dir / "config.md").read_text(encoding="utf-8"))
    persona_meta, persona_body = parse_markdown_document(
        (agent_dir / "persona.md").read_text(encoding="utf-8")
    )
    _, memory_body = parse_markdown_document((agent_dir / "memory.md").read_text(encoding="utf-8"))

    agent_id = str(config_meta.get("agent_id") or agent_dir.name)
    paths = AgentPaths(
        root=agent_dir,
        config_file=agent_dir / "config.md",
        persona_file=agent_dir / "persona.md",
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
        memory_body=memory_body.strip(),
        paths=paths,
    )


def render_system_prompt(settings: AgentSettings) -> str:
    memory_section = settings.memory_body or "(empty memory)"
    return (
        f"You are {settings.persona_name}, a {settings.persona_role}.\n\n"
        f"{settings.persona_body}\n\n"
        f"## Persistent memory\n\n{memory_section}\n"
    )


def llm_options(settings: AgentSettings) -> dict[str, Any]:
    return {"temperature": settings.temperature, "num_ctx": settings.num_ctx}
