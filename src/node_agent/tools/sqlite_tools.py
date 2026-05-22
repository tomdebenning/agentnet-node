"""Sandboxed SQLite tools."""

from __future__ import annotations

import re
from pathlib import Path

import aiosqlite

DB_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
MAX_ROWS = 100


def _validate_db_name(db_name: str) -> str | None:
    if not DB_NAME_PATTERN.match(db_name):
        return "Error: db_name must match ^[a-zA-Z0-9_-]+$"
    return None


def _db_path(sqlite_root: Path, db_name: str) -> Path:
    sqlite_root.mkdir(parents=True, exist_ok=True)
    return sqlite_root / f"{db_name}.sqlite"


def _format_rows(columns: list[str], rows: list[tuple]) -> str:
    if not rows:
        return "(no rows)"
    col_widths = [len(col) for col in columns]
    str_rows: list[list[str]] = []
    for row in rows:
        str_row = ["" if value is None else str(value) for value in row]
        str_rows.append(str_row)
        for idx, cell in enumerate(str_row):
            col_widths[idx] = max(col_widths[idx], len(cell))
    header = " | ".join(col.ljust(col_widths[i]) for i, col in enumerate(columns))
    separator = "-+-".join("-" * width for width in col_widths)
    lines = [header, separator]
    for str_row in str_rows:
        lines.append(" | ".join(str_row[i].ljust(col_widths[i]) for i in range(len(columns))))
    return "\n".join(lines)


async def list_databases(sqlite_root: Path) -> str:
    files = sorted(sqlite_root.glob("*.sqlite"))
    return "\n".join(f.stem for f in files) if files else "(no databases)"


async def sqlite_query(
    sqlite_root: Path,
    db_name: str,
    sql: str,
    params: list | None = None,
) -> str:
    error = _validate_db_name(db_name)
    if error:
        return error
    path = _db_path(sqlite_root, db_name)
    if not path.exists():
        return f"Error: database not found: {db_name}"
    uri = f"file:{path}?mode=ro"
    try:
        async with aiosqlite.connect(uri, uri=True) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(sql, params or [])
            rows = await cursor.fetchmany(MAX_ROWS + 1)
            truncated = len(rows) > MAX_ROWS
            if truncated:
                rows = rows[:MAX_ROWS]
            if cursor.description is None:
                return "(no result set)"
            columns = [col[0] for col in cursor.description]
            result = _format_rows(columns, [tuple(row) for row in rows])
            if truncated:
                result += f"\n\n[... truncated after {MAX_ROWS} rows ...]"
            return result
    except Exception as exc:
        return f"Error: {exc}"


async def sqlite_execute(
    sqlite_root: Path,
    db_name: str,
    sql: str,
    params: list | None = None,
) -> str:
    error = _validate_db_name(db_name)
    if error:
        return error
    path = _db_path(sqlite_root, db_name)
    try:
        async with aiosqlite.connect(path) as conn:
            cursor = await conn.execute(sql, params or [])
            await conn.commit()
            return f"executed; rowcount={cursor.rowcount}"
    except Exception as exc:
        return f"Error: {exc}"


async def sqlite_schema(sqlite_root: Path, db_name: str) -> str:
    error = _validate_db_name(db_name)
    if error:
        return error
    path = _db_path(sqlite_root, db_name)
    if not path.exists():
        return f"Error: database not found: {db_name}"
    uri = f"file:{path}?mode=ro"
    try:
        async with aiosqlite.connect(uri, uri=True) as conn:
            cursor = await conn.execute(
                "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name"
            )
            rows = await cursor.fetchall()
            return "\n\n".join(row[0] for row in rows) if rows else "(empty schema)"
    except Exception as exc:
        return f"Error: {exc}"
