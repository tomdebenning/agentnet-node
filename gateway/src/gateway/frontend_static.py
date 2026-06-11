"""Validate the built frontend SPA is complete."""

from __future__ import annotations

import re
from pathlib import Path

_ASSET_REF = re.compile(r'(?:src|href)="(/assets/[^"]+)"')


def frontend_asset_refs(static_root: Path) -> list[str]:
    index = static_root / "index.html"
    if not index.is_file():
        return []
    return _ASSET_REF.findall(index.read_text(encoding="utf-8"))


def validate_frontend_build(static_root: Path) -> tuple[bool, list[str]]:
    """Return (ok, missing_asset_paths) for index.html-linked /assets/* files."""
    index = static_root / "index.html"
    if not index.is_file():
        return False, ["/index.html"]

    missing: list[str] = []
    for ref in frontend_asset_refs(static_root):
        rel = ref.removeprefix("/")
        if not (static_root / rel).is_file():
            missing.append(ref)
    return not missing, missing


def format_frontend_build_problem(static_root: Path, missing: list[str]) -> str:
    lines = [
        "Web UI build is incomplete or stale.",
        f"  dist: {static_root}",
    ]
    if missing:
        lines.append("  missing:")
        for item in missing:
            lines.append(f"    - {item}")
    lines.append("  fix: cd web && npm install && npm run build")
    lines.append("  then hard-refresh the browser (Ctrl+Shift+R)")
    return "\n".join(lines)
