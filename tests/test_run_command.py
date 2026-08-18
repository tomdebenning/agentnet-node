"""Workspace-sandboxed run_command tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from node_agent.tools.definitions import tools_for_agent
from node_agent.tools.shell import run_command


def _tool_names() -> set[str]:
    return {str(tool.function.get("name")) for tool in tools_for_agent()}


@pytest.mark.asyncio
async def test_run_command_is_registered() -> None:
    assert "run_command" in _tool_names()


@pytest.mark.asyncio
async def test_run_command_runs_in_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "note.txt").write_text("hi\n", encoding="utf-8")
    result = await run_command(workspace, "cat note.txt && pwd")
    assert "exit_code=0" in result
    assert "hi" in result
    assert str(workspace.resolve()) in result


@pytest.mark.asyncio
async def test_run_command_rejects_absolute_cwd(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    result = await run_command(workspace, "echo no", cwd="/tmp")
    assert result.startswith("Error:")
    assert "Absolute" in result or "absolute" in result


@pytest.mark.asyncio
async def test_run_command_rejects_cwd_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    result = await run_command(workspace, "echo no", cwd="../")
    assert result.startswith("Error:")
    assert "sandbox" in result.lower() or "escapes" in result.lower()


@pytest.mark.asyncio
async def test_run_command_rejects_empty_command(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    result = await run_command(workspace, "   ")
    assert "Error:" in result


@pytest.mark.asyncio
async def test_run_command_timeout(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    result = await run_command(workspace, "sleep 5", timeout_seconds=0.2)
    assert "timed out" in result


@pytest.mark.asyncio
async def test_run_command_relative_cwd(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sub = workspace / "src"
    sub.mkdir(parents=True)
    (sub / "x.txt").write_text("ok\n", encoding="utf-8")
    result = await run_command(workspace, "cat x.txt", cwd="src")
    assert "exit_code=0" in result
    assert "ok" in result
