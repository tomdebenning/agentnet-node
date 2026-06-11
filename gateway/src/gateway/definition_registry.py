"""SQLite registry of agent definition references for the gateway."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from shared.markdown_io import parse_markdown_document

if TYPE_CHECKING:
    from gateway.definition_store import DefinitionStore


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class DefinitionRegistryEntry:
    definition_id: str
    path: str
    uses_memory: bool
    persona_reviewed: bool
    skills_reviewed: bool
    spawnable: bool
    persona_name: str | None
    persona_role: str | None
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "definition_id": self.definition_id,
            "path": self.path,
            "uses_memory": self.uses_memory,
            "persona_reviewed": self.persona_reviewed,
            "skills_reviewed": self.skills_reviewed,
            "spawnable": self.spawnable,
            "persona_name": self.persona_name,
            "persona_role": self.persona_role,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class DefinitionRegistry:
    """Gateway catalog of known agent definitions (filesystem paths + review metadata)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path.expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS definitions (
                    definition_id TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    uses_memory INTEGER NOT NULL DEFAULT 1,
                    persona_reviewed INTEGER NOT NULL DEFAULT 0,
                    skills_reviewed INTEGER NOT NULL DEFAULT 0,
                    spawnable INTEGER NOT NULL DEFAULT 0,
                    persona_name TEXT,
                    persona_role TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def upsert(
        self,
        *,
        definition_id: str,
        path: str,
        uses_memory: bool,
        persona_reviewed: bool,
        skills_reviewed: bool,
        spawnable: bool,
        persona_name: str | None = None,
        persona_role: str | None = None,
    ) -> DefinitionRegistryEntry:
        now = _utcnow_iso()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT created_at FROM definitions WHERE definition_id = ?",
                (definition_id,),
            ).fetchone()
            created_at = existing["created_at"] if existing else now
            conn.execute(
                """
                INSERT INTO definitions (
                    definition_id, path, uses_memory, persona_reviewed, skills_reviewed,
                    spawnable, persona_name, persona_role, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(definition_id) DO UPDATE SET
                    path = excluded.path,
                    uses_memory = excluded.uses_memory,
                    persona_reviewed = excluded.persona_reviewed,
                    skills_reviewed = excluded.skills_reviewed,
                    spawnable = excluded.spawnable,
                    persona_name = excluded.persona_name,
                    persona_role = excluded.persona_role,
                    updated_at = excluded.updated_at
                """,
                (
                    definition_id,
                    path,
                    int(uses_memory),
                    int(persona_reviewed),
                    int(skills_reviewed),
                    int(spawnable),
                    persona_name,
                    persona_role,
                    created_at,
                    now,
                ),
            )
            conn.commit()
        return self.get(definition_id)  # type: ignore[return-value]

    def delete(self, definition_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM definitions WHERE definition_id = ?", (definition_id,))
            conn.commit()

    def get(self, definition_id: str) -> DefinitionRegistryEntry | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM definitions WHERE definition_id = ?",
                (definition_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_entry(row)

    def list_all(self) -> list[DefinitionRegistryEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM definitions ORDER BY definition_id COLLATE NOCASE"
            ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def reconcile(self, store: DefinitionStore) -> None:
        """Sync registry rows with the filesystem definition library."""
        seen: set[str] = set()
        for item in store.list_definitions():
            seen.add(item.definition_id)
            self.sync_definition(store, item.definition_id)
        for entry in self.list_all():
            if entry.definition_id not in seen:
                self.delete(entry.definition_id)

    def sync_definition(self, store: DefinitionStore, definition_id: str) -> DefinitionRegistryEntry | None:
        path = store.definition_dir(definition_id)
        if not store._is_definition_dir(path):
            self.delete(definition_id)
            return None
        meta = store.read_meta(definition_id)
        review = store.read_review_status(definition_id)
        persona_raw = store.read_persona_raw(definition_id)
        persona_meta, _ = parse_markdown_document(persona_raw)
        return self.upsert(
            definition_id=definition_id,
            path=str(path),
            uses_memory=bool(meta.get("uses_memory", True)),
            persona_reviewed=review["persona_reviewed"],
            skills_reviewed=review["skills_reviewed"],
            spawnable=review["spawnable"],
            persona_name=str(persona_meta.get("name") or definition_id),
            persona_role=str(persona_meta.get("role") or "") or None,
        )

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> DefinitionRegistryEntry:
        return DefinitionRegistryEntry(
            definition_id=row["definition_id"],
            path=row["path"],
            uses_memory=bool(row["uses_memory"]),
            persona_reviewed=bool(row["persona_reviewed"]),
            skills_reviewed=bool(row["skills_reviewed"]),
            spawnable=bool(row["spawnable"]),
            persona_name=row["persona_name"],
            persona_role=row["persona_role"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
