"""Agent definition library — persona, skills, memory, and review metadata."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gateway.definition_registry import DefinitionRegistry

from shared.markdown_io import (
    default_memory_markdown,
    default_persona_markdown,
    default_skills_markdown,
    parse_markdown_document,
    render_markdown_document,
)


@dataclass
class DefinitionSummary:
    definition_id: str
    path: Path


class DefinitionStore:
    """Filesystem-backed agent definition library."""

    def __init__(self, root: Path, *, registry: DefinitionRegistry | None = None) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.registry = registry

    def definition_dir(self, definition_id: str) -> Path:
        safe = definition_id.strip()
        if not safe or "/" in safe or ".." in safe:
            raise ValueError("invalid definition_id")
        return self.root / safe

    def list_definitions(self) -> list[DefinitionSummary]:
        if not self.root.exists():
            return []
        out: list[DefinitionSummary] = []
        for entry in sorted(self.root.iterdir()):
            if entry.is_dir() and self._is_definition_dir(entry):
                out.append(DefinitionSummary(definition_id=entry.name, path=entry))
        return out

    def create_definition(
        self,
        definition_id: str,
        *,
        persona_name: str | None = None,
        persona_role: str = "helpful assistant",
        persona_content: str | None = None,
        skills_content: str | None = None,
        memory_content: str | None = None,
        uses_memory: bool = True,
        persona_reviewed: bool = False,
        skills_reviewed: bool = False,
    ) -> Path:
        path = self.definition_dir(definition_id)
        if path.exists():
            raise FileExistsError(f"definition already exists: {definition_id}")

        path.mkdir(parents=True)
        self._write_meta(
            definition_id,
            {
                "definition_id": definition_id,
                "uses_memory": uses_memory,
                "persona_reviewed": persona_reviewed,
                "skills_reviewed": skills_reviewed,
                "spawnable": persona_reviewed and skills_reviewed,
            },
        )
        (path / "persona.md").write_text(
            persona_content
            if persona_content is not None
            else default_persona_markdown(persona_name or definition_id, persona_role),
            encoding="utf-8",
        )
        (path / "skills.md").write_text(
            skills_content if skills_content is not None else default_skills_markdown(),
            encoding="utf-8",
        )
        if uses_memory:
            (path / "memory.md").write_text(
                memory_content if memory_content is not None else default_memory_markdown(),
                encoding="utf-8",
            )
        self._sync_registry(definition_id)
        return path

    def write_persona_raw(self, definition_id: str, content: str) -> None:
        self._require_definition(definition_id)
        (self.definition_dir(definition_id) / "persona.md").write_text(content, encoding="utf-8")
        self._sync_registry(definition_id)

    def write_skills_raw(self, definition_id: str, content: str) -> None:
        self._require_definition(definition_id)
        (self.definition_dir(definition_id) / "skills.md").write_text(content, encoding="utf-8")
        self._sync_registry(definition_id)

    def write_memory_raw(self, definition_id: str, content: str) -> None:
        self._require_definition(definition_id)
        if not self.read_uses_memory(definition_id):
            raise ValueError("definition does not use memory")
        (self.definition_dir(definition_id) / "memory.md").write_text(content, encoding="utf-8")
        self._sync_registry(definition_id)

    def read_uses_memory(self, definition_id: str) -> bool:
        meta = self.read_meta(definition_id)
        return bool(meta.get("uses_memory", True))

    def set_uses_memory(self, definition_id: str, uses_memory: bool) -> dict[str, Any]:
        self._require_definition(definition_id)
        path = self.definition_dir(definition_id)
        meta = self.read_meta(definition_id)
        meta["uses_memory"] = uses_memory
        self._write_meta(definition_id, meta)
        memory_path = path / "memory.md"
        if uses_memory:
            if not memory_path.exists():
                memory_path.write_text(default_memory_markdown(), encoding="utf-8")
        elif memory_path.exists():
            memory_path.unlink()
        self._sync_registry(definition_id)
        return meta

    def delete_definition(self, definition_id: str) -> None:
        path = self.definition_dir(definition_id)
        if not path.exists():
            raise FileNotFoundError(f"definition not found: {definition_id}")
        shutil.rmtree(path)
        if self.registry is not None:
            self.registry.delete(definition_id)

    def read_meta(self, definition_id: str) -> dict[str, Any]:
        path = self.definition_dir(definition_id)
        meta_path = path / "meta.json"
        if meta_path.exists():
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        legacy = path / "config.md"
        if legacy.exists():
            meta, _ = parse_markdown_document(legacy.read_text(encoding="utf-8"))
            normalized = {
                "definition_id": str(
                    meta.get("definition_id") or meta.get("template_id") or definition_id
                ),
                "uses_memory": bool(meta.get("uses_memory", True)),
                "persona_reviewed": bool(meta.get("persona_reviewed")),
                "skills_reviewed": bool(meta.get("skills_reviewed")),
                "spawnable": bool(meta.get("spawnable")),
            }
            self._write_meta(definition_id, normalized)
            return normalized
        raise FileNotFoundError(f"definition not found: {definition_id}")

    def read_persona_raw(self, definition_id: str) -> str:
        self._require_definition(definition_id)
        return (self.definition_dir(definition_id) / "persona.md").read_text(encoding="utf-8")

    def read_skills_raw(self, definition_id: str) -> str:
        path = self.definition_dir(definition_id) / "skills.md"
        if not path.exists():
            return default_skills_markdown()
        return path.read_text(encoding="utf-8")

    def read_memory_raw(self, definition_id: str) -> str:
        if not self.read_uses_memory(definition_id):
            return ""
        path = self.definition_dir(definition_id) / "memory.md"
        if not path.exists():
            return default_memory_markdown()
        return path.read_text(encoding="utf-8")

    def read_review_status(self, definition_id: str) -> dict[str, bool]:
        meta = self.read_meta(definition_id)
        persona = bool(meta.get("persona_reviewed"))
        skills = bool(meta.get("skills_reviewed"))
        return {
            "persona_reviewed": persona,
            "skills_reviewed": skills,
            "spawnable": persona and skills,
        }

    def set_review_flag(
        self,
        definition_id: str,
        *,
        persona_reviewed: bool | None = None,
        skills_reviewed: bool | None = None,
    ) -> dict[str, bool]:
        meta = self.read_meta(definition_id)
        if persona_reviewed is not None:
            meta["persona_reviewed"] = persona_reviewed
        if skills_reviewed is not None:
            meta["skills_reviewed"] = skills_reviewed
        meta["spawnable"] = bool(meta.get("persona_reviewed")) and bool(meta.get("skills_reviewed"))
        self._write_meta(definition_id, meta)
        self._sync_registry(definition_id)
        return self.read_review_status(definition_id)

    def _sync_registry(self, definition_id: str) -> None:
        if self.registry is None:
            return
        self.registry.sync_definition(self, definition_id)

    def _write_meta(self, definition_id: str, meta: dict[str, Any]) -> None:
        path = self.definition_dir(definition_id)
        path.mkdir(parents=True, exist_ok=True)
        meta["definition_id"] = definition_id
        meta["spawnable"] = bool(meta.get("persona_reviewed")) and bool(meta.get("skills_reviewed"))
        (path / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    def _require_definition(self, definition_id: str) -> None:
        if not self._is_definition_dir(self.definition_dir(definition_id)):
            raise FileNotFoundError(f"definition not found: {definition_id}")

    @staticmethod
    def _is_definition_dir(path: Path) -> bool:
        return path.is_dir() and (path / "persona.md").exists()
