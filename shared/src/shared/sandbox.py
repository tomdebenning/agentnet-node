"""Path sandbox validation."""

from __future__ import annotations

from pathlib import Path


class SandboxViolation(Exception):
    pass


def resolve_safe_path(root: Path, requested: str) -> Path:
    if not isinstance(requested, str):
        raise SandboxViolation("Path must be a string")
    if requested == "" or requested == ".":
        return root.resolve()
    path = Path(requested)
    if path.is_absolute():
        raise SandboxViolation("Absolute paths are not allowed")
    candidate = (root / path).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise SandboxViolation(f"Path escapes sandbox root: {requested}") from exc
    return candidate
