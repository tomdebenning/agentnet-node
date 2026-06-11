"""Sandboxed filesystem tools."""

from __future__ import annotations

from pathlib import Path

from shared.sandbox import SandboxViolation, resolve_safe_path

MAX_READ_BYTES = 100 * 1024


async def read_file(workspace_root: Path, path: str) -> str:
    try:
        target = resolve_safe_path(workspace_root, path)
    except SandboxViolation as exc:
        return f"Error: {exc}"
    if not target.exists():
        return f"Error: file not found: {path}"
    if not target.is_file():
        return f"Error: not a file: {path}"
    data = target.read_bytes()
    if len(data) > MAX_READ_BYTES:
        return data[:MAX_READ_BYTES].decode("utf-8", errors="replace") + "\n\n[... truncated ...]"
    return data.decode("utf-8", errors="replace")


async def write_file(workspace_root: Path, path: str, content: str) -> str:
    try:
        target = resolve_safe_path(workspace_root, path)
    except SandboxViolation as exc:
        return f"Error: {exc}"
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = content.encode("utf-8")
    target.write_bytes(encoded)
    return f"wrote {len(encoded)} bytes to {path}"


async def list_files(workspace_root: Path, path: str = ".") -> str:
    try:
        target = resolve_safe_path(workspace_root, path)
    except SandboxViolation as exc:
        return f"Error: {exc}"
    if not target.is_dir():
        return f"Error: not a directory: {path}"
    entries = [entry.name + ("/" if entry.is_dir() else "") for entry in sorted(target.iterdir())]
    return "\n".join(entries) if entries else "(empty directory)"
