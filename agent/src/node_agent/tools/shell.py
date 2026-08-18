"""Workspace-sandboxed shell tool."""

from __future__ import annotations

import asyncio
import contextlib
import os
from pathlib import Path

from shared.sandbox import SandboxViolation, resolve_safe_path

MAX_OUTPUT_BYTES = 100 * 1024
DEFAULT_TIMEOUT_SECONDS = 60.0
MAX_TIMEOUT_SECONDS = 120.0


def _limited_env(workspace_root: Path) -> dict[str, str]:
    path = os.environ.get("PATH", "/usr/bin:/bin")
    lang = os.environ.get("LANG", "C.UTF-8")
    return {
        "PATH": path,
        "HOME": str(workspace_root),
        "LANG": lang,
        "LC_ALL": lang,
        "TERM": "dumb",
    }


def _decode(data: bytes) -> str:
    chunk = data[:MAX_OUTPUT_BYTES]
    text = chunk.decode("utf-8", errors="replace")
    if len(data) > MAX_OUTPUT_BYTES:
        return text + "\n\n[... truncated ...]"
    return text


async def run_command(
    workspace_root: Path,
    command: str,
    *,
    cwd: str = ".",
    timeout_seconds: float | None = None,
) -> str:
    """Run a command with cwd constrained to the agent workspace."""
    if not isinstance(command, str) or not command.strip():
        return "Error: command must be a non-empty string"
    try:
        workdir = resolve_safe_path(workspace_root, cwd or ".")
    except SandboxViolation as exc:
        return f"Error: {exc}"
    if not workdir.exists():
        return f"Error: working directory not found: {cwd}"
    if not workdir.is_dir():
        return f"Error: not a directory: {cwd}"

    timeout = DEFAULT_TIMEOUT_SECONDS if timeout_seconds is None else float(timeout_seconds)
    if timeout <= 0:
        return "Error: timeout_seconds must be positive"
    timeout = min(timeout, MAX_TIMEOUT_SECONDS)

    try:
        proc = await asyncio.create_subprocess_exec(
            "/bin/bash",
            "-c",
            command,
            cwd=workdir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_limited_env(workspace_root.resolve()),
        )
    except OSError as exc:
        return f"Error: failed to start command: {exc}"

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        with contextlib.suppress(ProcessLookupError, OSError):
            await proc.communicate()
        return f"Error: command timed out after {timeout:.0f}s"

    stdout_text = _decode(stdout or b"")
    stderr_text = _decode(stderr or b"")
    parts = [f"exit_code={proc.returncode}"]
    if stdout_text:
        parts.append("stdout:\n" + stdout_text)
    if stderr_text:
        parts.append("stderr:\n" + stderr_text)
    if not stdout_text and not stderr_text:
        parts.append("(no output)")
    return "\n".join(parts)
