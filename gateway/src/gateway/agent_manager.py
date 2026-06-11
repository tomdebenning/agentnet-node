"""Local agent process lifecycle."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


class AgentProcessState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class ManagedAgent:
    agent_id: str
    directory: Path
    state: AgentProcessState = AgentProcessState.STOPPED
    pid: int | None = None
    return_code: int | None = None
    error: str | None = None
    _process: asyncio.subprocess.Process | None = field(default=None, repr=False)
    _watch_task: asyncio.Task[None] | None = field(default=None, repr=False)


class AgentManager:
    """Spawn and stop node_agent child processes."""

    def __init__(self, *, gateway_url: str) -> None:
        self.gateway_url = gateway_url.rstrip("/")
        self._agents: dict[str, ManagedAgent] = {}

    def register(self, agent_id: str, directory: Path) -> ManagedAgent:
        if agent_id not in self._agents:
            self._agents[agent_id] = ManagedAgent(agent_id=agent_id, directory=directory)
        else:
            self._agents[agent_id].directory = directory
        return self._agents[agent_id]

    def unregister(self, agent_id: str) -> None:
        self._agents.pop(agent_id, None)

    def get(self, agent_id: str) -> ManagedAgent | None:
        return self._agents.get(agent_id)

    def list_managed(self) -> list[ManagedAgent]:
        return sorted(self._agents.values(), key=lambda item: item.agent_id)

    def running_count(self) -> int:
        return sum(1 for item in self._agents.values() if item.state == AgentProcessState.RUNNING)

    async def start(self, agent_id: str, *, resume: bool = False) -> ManagedAgent:
        managed = self._agents.get(agent_id)
        if managed is None:
            raise KeyError(f"unknown agent: {agent_id}")
        if managed.state in (AgentProcessState.RUNNING, AgentProcessState.STARTING):
            return managed

        managed.state = AgentProcessState.STARTING
        managed.error = None
        managed.return_code = None

        env = os.environ.copy()
        env["AGENTNET_GATEWAY_URL"] = self.gateway_url

        cmd = [
            sys.executable,
            "-m",
            "node_agent",
            "--agent-dir",
            str(managed.directory),
            "--gateway-url",
            self.gateway_url,
        ]
        if resume:
            cmd.append("--resume")
        managed._process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(managed.directory),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        managed.pid = managed._process.pid
        managed.state = AgentProcessState.RUNNING
        managed._watch_task = asyncio.create_task(self._watch_process(managed))
        logger.info("agent_started", agent_id=agent_id, pid=managed.pid)
        return managed

    async def stop(self, agent_id: str, *, timeout: float = 10.0) -> ManagedAgent:
        managed = self._agents.get(agent_id)
        if managed is None:
            raise KeyError(f"unknown agent: {agent_id}")
        if managed.state == AgentProcessState.STOPPED:
            return managed

        managed.state = AgentProcessState.STOPPING
        proc = managed._process
        if proc is None or proc.returncode is not None:
            managed.state = AgentProcessState.STOPPED
            managed.pid = None
            return managed

        proc.send_signal(signal.SIGTERM)
        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()

        managed.state = AgentProcessState.STOPPED
        managed.pid = None
        logger.info("agent_stopped", agent_id=agent_id)
        return managed

    async def stop_all(self) -> None:
        for agent_id in list(self._agents):
            if self._agents[agent_id].state != AgentProcessState.STOPPED:
                await self.stop(agent_id)

    async def _watch_process(self, managed: ManagedAgent) -> None:
        proc = managed._process
        if proc is None:
            return
        stdout, stderr = await proc.communicate()
        managed.return_code = proc.returncode
        managed.pid = None
        if managed.state == AgentProcessState.STOPPING:
            managed.state = AgentProcessState.STOPPED
            return
        if proc.returncode not in (0, -15, -signal.SIGTERM.value if hasattr(signal, "SIGTERM") else None):
            managed.state = AgentProcessState.ERROR
            err = stderr.decode("utf-8", errors="replace").strip()
            managed.error = err or f"process exited with code {proc.returncode}"
            logger.warning(
                "agent_exited",
                agent_id=managed.agent_id,
                return_code=proc.returncode,
                stderr=err[:500],
            )
        else:
            managed.state = AgentProcessState.STOPPED
        if stdout:
            logger.debug("agent_stdout", agent_id=managed.agent_id, text=stdout.decode()[:300])
