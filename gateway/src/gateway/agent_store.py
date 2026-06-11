"""Agent directory storage on disk."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from shared.markdown_io import (
    default_config_markdown,
    default_memory_markdown,
    default_persona_markdown,
    default_skills_markdown,
    default_task_markdown,
    parse_markdown_document,
    render_markdown_document,
)


class AgentFileKind(str, Enum):
    CONFIG = "config"
    PERSONA = "persona"
    SKILLS = "skills"
    MEMORY = "memory"
    TASK = "task"


@dataclass
class AgentSummary:
    agent_id: str
    path: Path


class AgentStore:
    """Filesystem-backed agent registry."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def agent_dir(self, agent_id: str) -> Path:
        safe = agent_id.strip()
        if not safe or "/" in safe or ".." in safe:
            raise ValueError("invalid agent_id")
        return self.root / safe

    def list_agents(self) -> list[AgentSummary]:
        if not self.root.exists():
            return []
        out: list[AgentSummary] = []
        for entry in sorted(self.root.iterdir()):
            if entry.is_dir() and (entry / "config.md").exists():
                out.append(AgentSummary(agent_id=entry.name, path=entry))
        return out

    def create_agent(
        self,
        agent_id: str,
        *,
        target_puller: str = "puller-01",
        model: str = "llama3.1:8b",
        temperature: float = 0.7,
        num_ctx: int = 8192,
        persona_name: str | None = None,
        persona_role: str = "helpful assistant",
    ) -> Path:
        agent_path = self.agent_dir(agent_id)
        if agent_path.exists():
            raise FileExistsError(f"agent already exists: {agent_id}")

        agent_path.mkdir(parents=True)
        (agent_path / "workspace").mkdir()
        (agent_path / "databases").mkdir()

        name = persona_name or agent_id
        (agent_path / "config.md").write_text(
            default_config_markdown(
                agent_id,
                target_puller,
                model,
                temperature=temperature,
                num_ctx=num_ctx,
            ),
            encoding="utf-8",
        )
        (agent_path / "persona.md").write_text(
            default_persona_markdown(name, persona_role),
            encoding="utf-8",
        )
        (agent_path / "skills.md").write_text(default_skills_markdown(), encoding="utf-8")
        (agent_path / "memory.md").write_text(default_memory_markdown(), encoding="utf-8")
        (agent_path / "task.md").write_text(default_task_markdown(), encoding="utf-8")
        return agent_path

    def delete_agent(self, agent_id: str) -> None:
        agent_path = self.agent_dir(agent_id)
        if not agent_path.exists():
            raise FileNotFoundError(f"agent not found: {agent_id}")
        shutil.rmtree(agent_path)

    def read_file(self, agent_id: str, kind: AgentFileKind) -> str:
        path = self.agent_dir(agent_id) / f"{kind.value}.md"
        if not path.exists():
            raise FileNotFoundError(f"{kind.value}.md not found for {agent_id}")
        return path.read_text(encoding="utf-8")

    def write_file(self, agent_id: str, kind: AgentFileKind, content: str) -> None:
        agent_path = self.agent_dir(agent_id)
        if not agent_path.exists():
            raise FileNotFoundError(f"agent not found: {agent_id}")
        path = agent_path / f"{kind.value}.md"
        path.write_text(content, encoding="utf-8")

    def read_parsed(self, agent_id: str, kind: AgentFileKind) -> dict:
        content = self.read_file(agent_id, kind)
        meta, body = parse_markdown_document(content)
        return {"frontmatter": meta, "body": body, "raw": content}

    def write_parsed(
        self,
        agent_id: str,
        kind: AgentFileKind,
        *,
        frontmatter: dict | None = None,
        body: str | None = None,
    ) -> str:
        current_meta, current_body = parse_markdown_document(self.read_file(agent_id, kind))
        meta = current_meta if frontmatter is None else frontmatter
        text_body = current_body if body is None else body
        rendered = render_markdown_document(meta, text_body)
        self.write_file(agent_id, kind, rendered)
        return rendered

    def get_config_agent_id(self, agent_id: str) -> str:
        meta, _ = parse_markdown_document(self.read_file(agent_id, AgentFileKind.CONFIG))
        configured = meta.get("agent_id")
        return str(configured) if configured else agent_id
