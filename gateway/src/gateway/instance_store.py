"""Spawned agent instances (per-instance memory, task, persona copy)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from gateway.agent_store import AgentFileKind, AgentStore
from shared.markdown_io import parse_markdown_document, render_markdown_document
from shared.run_store import RunStore

InstanceMode = Literal["autonomous", "interactive"]


class InstanceStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    STOPPED = "stopped"
    PAUSED = "paused"
    INTERACTIVE_IDLE = "interactive_idle"
    INTERACTIVE_BUSY = "interactive_busy"


@dataclass
class InstanceSummary:
    instance_id: str
    path: Path
    definition_id: str | None
    mode: str | None
    instance_status: str | None


def _timestamp_suffix() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


class InstanceStore(AgentStore):
    """Extends agent store with template spawn and instance metadata."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def spawn_from_definition(
        self,
        definition_store: DefinitionStore,
        definition_id: str,
        *,
        base_name: str,
        target_puller: str,
        model: str,
        temperature: float,
        num_ctx: int,
        mode: InstanceMode,
        goal: str = "",
        conversation_id: str | None = None,
        resume: bool = False,
        persona_content: str | None = None,
        skills_content: str | None = None,
        run_options: dict[str, Any] | None = None,
    ) -> Path:
        if not definition_store.definition_dir(definition_id).exists():
            raise FileNotFoundError(f"definition not found: {definition_id}")
        base_name = base_name.strip()
        if not base_name:
            raise ValueError("base_name required")
        instance_id = f"{base_name}-{_timestamp_suffix()}"
        instance_path = self.agent_dir(instance_id)
        if instance_path.exists():
            raise FileExistsError(f"instance collision: {instance_id}")

        instance_path.mkdir(parents=True)
        (instance_path / "workspace").mkdir()
        (instance_path / "databases").mkdir()

        run_conversation_id = conversation_id or f"run-{_timestamp_suffix()}"
        uses_memory = definition_store.read_uses_memory(definition_id)

        instance_config: dict[str, Any] = {
            "instance_id": instance_id,
            "definition_id": definition_id,
            "base_name": base_name,
            "agent_id": instance_id,
            "mode": mode,
            "instance_status": InstanceStatus.PENDING.value,
            "spawned_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "default_target_puller": target_puller,
            "default_model": model,
            "temperature": temperature,
            "num_ctx": num_ctx,
            "uses_memory": uses_memory,
            "resume_on_start": resume,
            "current_conversation_id": run_conversation_id,
        }
        (instance_path / "config.md").write_text(
            render_markdown_document(
                instance_config,
                "# Instance configuration\n",
            ),
            encoding="utf-8",
        )
        persona_text = (
            persona_content
            if persona_content is not None
            else definition_store.read_persona_raw(definition_id)
        )
        (instance_path / "persona.md").write_text(persona_text, encoding="utf-8")
        skills_text = (
            skills_content
            if skills_content is not None
            else definition_store.read_skills_raw(definition_id)
        )
        (instance_path / "skills.md").write_text(skills_text, encoding="utf-8")
        if uses_memory:
            (instance_path / "memory.md").write_text(
                definition_store.read_memory_raw(definition_id),
                encoding="utf-8",
            )
        task_meta = {"conversation_id": run_conversation_id}
        task_body = goal.strip() or "Set the goal for this run.\n"
        (instance_path / "task.md").write_text(
            render_markdown_document(task_meta, task_body.rstrip() + "\n"),
            encoding="utf-8",
        )
        RunStore(instance_path).create_run(
            run_conversation_id,
            goal=goal.strip(),
            options=run_options or {},
        )
        return instance_path

    def init_run(
        self,
        instance_id: str,
        conversation_id: str,
        *,
        goal: str = "",
        run_options: dict[str, Any] | None = None,
    ) -> None:
        path = self.agent_dir(instance_id)
        RunStore(path).create_run(
            conversation_id,
            goal=goal.strip(),
            options=run_options or {},
        )
        self.set_current_conversation_id(instance_id, conversation_id)

    def set_current_conversation_id(self, instance_id: str, conversation_id: str) -> None:
        meta, body = parse_markdown_document(self.read_file(instance_id, AgentFileKind.CONFIG))
        meta["current_conversation_id"] = conversation_id
        self.write_file(instance_id, AgentFileKind.CONFIG, render_markdown_document(meta, body))

    def read_current_conversation_id(self, instance_id: str) -> str | None:
        meta = self.read_instance_meta(instance_id)
        value = meta.get("current_conversation_id")
        return str(value) if value else None

    def list_instances(self) -> list[InstanceSummary]:
        summaries: list[InstanceSummary] = []
        for item in self.list_agents():
            meta, _ = parse_markdown_document(self.read_file(item.agent_id, AgentFileKind.CONFIG))
            summaries.append(
                InstanceSummary(
                    instance_id=item.agent_id,
                    path=item.path,
                    definition_id=meta.get("definition_id") or meta.get("template_id"),
                    mode=meta.get("mode"),
                    instance_status=meta.get("instance_status"),
                )
            )
        return summaries

    def read_instance_meta(self, instance_id: str) -> dict[str, Any]:
        meta, _ = parse_markdown_document(self.read_file(instance_id, AgentFileKind.CONFIG))
        return meta

    def update_instance_status(self, instance_id: str, status: InstanceStatus | str) -> None:
        meta, body = parse_markdown_document(self.read_file(instance_id, AgentFileKind.CONFIG))
        meta["instance_status"] = str(status.value if isinstance(status, InstanceStatus) else status)
        self.write_file(instance_id, AgentFileKind.CONFIG, render_markdown_document(meta, body))

    def delete_instance(self, instance_id: str) -> None:
        self.delete_agent(instance_id)
