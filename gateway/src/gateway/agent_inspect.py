"""Read-only inspection of agent conversations, workspace, and databases."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from shared.sandbox import SandboxViolation, resolve_safe_path

MAX_FILE_BYTES = 512 * 1024
MAX_PREVIEW_ROWS = 100


def _conversation_db(agent_dir: Path) -> Path:
    return agent_dir / "agent_state.db"


def list_conversations(agent_dir: Path) -> list[dict]:
    db_path = _conversation_db(agent_dir)
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT c.conversation_id, c.status,
                   (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.conversation_id)
            FROM conversations c
            ORDER BY c.conversation_id
            """
        ).fetchall()
        if not rows:
            rows = conn.execute(
                """
                SELECT conversation_id, 'unknown', COUNT(*)
                FROM messages
                GROUP BY conversation_id
                ORDER BY conversation_id
                """
            ).fetchall()
        return [
            {
                "conversation_id": row[0],
                "status": row[1],
                "message_count": int(row[2]),
            }
            for row in rows
        ]
    finally:
        conn.close()


def get_conversation_messages(agent_dir: Path, conversation_id: str) -> list[dict]:
    db_path = _conversation_db(agent_dir)
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, round, payload
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id
            """,
            (conversation_id,),
        ).fetchall()
    finally:
        conn.close()

    out: list[dict] = []
    for msg_id, round_num, payload_raw in rows:
        payload = json.loads(payload_raw)
        out.append(
            {
                "id": msg_id,
                "round": round_num,
                "role": payload.get("role"),
                "content": payload.get("content") or "",
                "tool_calls": payload.get("tool_calls"),
                "name": payload.get("name"),
                "tool_call_id": payload.get("tool_call_id"),
            }
        )
    return out


def format_messages_for_display(messages: list[dict]) -> str:
    lines: list[str] = []
    for msg in messages:
        header = f"--- [{msg['id']}] round={msg['round']} role={msg['role']}"
        if msg.get("name"):
            header += f" name={msg['name']}"
        if msg.get("tool_call_id"):
            header += f" tool_call_id={msg['tool_call_id']}"
        lines.append(header + " ---")
        if msg.get("tool_calls"):
            lines.append(json.dumps(msg["tool_calls"], indent=2))
        content = msg.get("content") or ""
        if content:
            lines.append(content)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def list_workspace(agent_dir: Path, subpath: str = ".") -> list[dict]:
    root = agent_dir / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    try:
        target = resolve_safe_path(root, subpath)
    except SandboxViolation as exc:
        raise ValueError(str(exc)) from exc

    entries: list[dict] = []
    for entry in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        rel = entry.relative_to(root.resolve()).as_posix()
        entries.append(
            {
                "path": rel,
                "name": entry.name,
                "is_dir": entry.is_dir(),
                "size": entry.stat().st_size if entry.is_file() else None,
            }
        )
    return entries


def read_workspace_file(agent_dir: Path, path: str) -> dict:
    root = agent_dir / "workspace"
    try:
        target = resolve_safe_path(root, path)
    except SandboxViolation as exc:
        raise ValueError(str(exc)) from exc
    if not target.exists():
        raise FileNotFoundError(f"file not found: {path}")
    if target.is_dir():
        raise IsADirectoryError(f"is a directory: {path}")

    data = target.read_bytes()
    truncated = len(data) > MAX_FILE_BYTES
    if truncated:
        data = data[:MAX_FILE_BYTES]
    text = data.decode("utf-8", errors="replace")
    if truncated:
        text += "\n\n[... truncated ...]"
    return {
        "path": path,
        "size": target.stat().st_size,
        "truncated": truncated,
        "content": text,
    }


def list_databases(agent_dir: Path) -> list[str]:
    root = agent_dir / "databases"
    root.mkdir(parents=True, exist_ok=True)
    return sorted(p.stem for p in root.glob("*.sqlite"))


def _db_path(agent_dir: Path, db_name: str) -> Path:
    if not db_name or "/" in db_name or ".." in db_name:
        raise ValueError("invalid database name")
    return agent_dir / "databases" / f"{db_name}.sqlite"


def get_database_info(agent_dir: Path, db_name: str) -> dict:
    path = _db_path(agent_dir, db_name)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {db_name}")

    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        schema_rows = conn.execute(
            """
            SELECT type, name, sql
            FROM sqlite_master
            WHERE sql IS NOT NULL
            ORDER BY type, name
            """
        ).fetchall()
        tables: list[dict] = []
        for obj_type, name, sql in schema_rows:
            if obj_type != "table":
                continue
            count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            cursor = conn.execute(f'SELECT * FROM "{name}" LIMIT {MAX_PREVIEW_ROWS}')
            col_names = [d[0] for d in cursor.description] if cursor.description else []
            preview_rows = cursor.fetchall()
            tables.append(
                {
                    "name": name,
                    "row_count": count,
                    "columns": col_names,
                    "preview_rows": [list(row) for row in preview_rows],
                    "create_sql": sql,
                }
            )
        return {
            "db_name": db_name,
            "path": str(path),
            "schema": [{"type": t, "name": n, "sql": s} for t, n, s in schema_rows],
            "tables": tables,
        }
    finally:
        conn.close()
