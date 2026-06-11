"""Orchestrate template spawn, autonomous processes, and interactive sessions."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Awaitable

import structlog

from gateway.agent_manager import AgentManager, AgentProcessState
from gateway.completion_log import CompletionLog
from gateway.instance_store import InstanceMode, InstanceStatus, InstanceStore
from gateway.interactive_sessions import InteractiveSessionManager, SessionState
from gateway.definition_store import DefinitionStore
from shared.run_store import RunStatus, RunStore

logger = structlog.get_logger(__name__)

StatusCallback = Callable[[str, InstanceStatus], Awaitable[None]]


def _timestamp_suffix() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


class InstanceLifecycle:
    def __init__(
        self,
        *,
        instance_store: InstanceStore,
        definition_store: DefinitionStore,
        agent_manager: AgentManager,
        interactive_manager: InteractiveSessionManager,
        completion_log: CompletionLog,
        on_status_change: StatusCallback | None = None,
    ) -> None:
        self.instances = instance_store
        self.definitions = definition_store
        self.processes = agent_manager
        self.interactive = interactive_manager
        self.completions = completion_log
        self._on_status_change = on_status_change
        self._wire_process_callbacks()

    def _wire_process_callbacks(self) -> None:
        original_watch = self.processes._watch_process

        async def watch_with_completion(managed) -> None:
            await original_watch(managed)
            meta = {}
            try:
                meta = self.instances.read_instance_meta(managed.agent_id)
            except FileNotFoundError:
                return
            mode = meta.get("mode")
            if mode != "autonomous":
                return
            if managed.state == AgentProcessState.ERROR:
                await self._set_status(managed.agent_id, InstanceStatus.ERROR)
                self.completions.record(
                    instance_id=managed.agent_id,
                    definition_id=meta.get("definition_id") or meta.get("template_id"),
                    success=False,
                    error=managed.error,
                )
            elif managed.state == AgentProcessState.STOPPED and managed.return_code == 0:
                disk_status = meta.get("instance_status")
                if disk_status in (
                    InstanceStatus.COMPLETED.value,
                    InstanceStatus.PAUSED.value,
                    None,
                    InstanceStatus.RUNNING.value,
                ):
                    conv_id = meta.get("current_conversation_id")
                    run_done = False
                    if conv_id:
                        try:
                            run_done = (
                                RunStore(managed.directory).get_run(str(conv_id)).status
                                == RunStatus.DONE
                            )
                        except FileNotFoundError:
                            pass
                    if run_done:
                        await self._set_status(managed.agent_id, InstanceStatus.COMPLETED)
                        self.completions.record(
                            instance_id=managed.agent_id,
                            definition_id=meta.get("definition_id") or meta.get("template_id"),
                            success=True,
                        )

        self.processes._watch_process = watch_with_completion  # type: ignore[method-assign]

    async def _set_status(self, instance_id: str, status: InstanceStatus) -> None:
        try:
            self.instances.update_instance_status(instance_id, status)
        except FileNotFoundError:
            return
        if self._on_status_change is not None:
            await self._on_status_change(instance_id, status)

    async def spawn(
        self,
        definition_id: str,
        *,
        base_name: str,
        target_puller: str,
        model: str,
        temperature: float,
        num_ctx: int,
        mode: InstanceMode,
        goal: str = "",
        task_body: str = "",
        conversation_id: str | None = None,
        resume: bool = False,
        auto_start: bool = True,
        persona_content: str | None = None,
        skills_content: str | None = None,
        run_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        effective_goal = goal.strip() or task_body.strip()
        path = self.instances.spawn_from_definition(
            self.definitions,
            definition_id,
            base_name=base_name,
            target_puller=target_puller,
            model=model,
            temperature=temperature,
            num_ctx=num_ctx,
            mode=mode,
            goal=effective_goal,
            conversation_id=conversation_id,
            resume=resume,
            persona_content=persona_content,
            skills_content=skills_content,
            run_options=run_options,
        )
        instance_id = path.name
        if mode == "interactive":
            self.interactive.register(instance_id, path)
            await self._set_status(instance_id, InstanceStatus.INTERACTIVE_IDLE)
            return self.instance_view(instance_id)

        self.processes.register(instance_id, path)
        if auto_start and effective_goal:
            await self.start_autonomous(instance_id)
        return self.instance_view(instance_id)

    async def start_autonomous(self, instance_id: str) -> None:
        await self._set_status(instance_id, InstanceStatus.RUNNING)
        meta = self.instances.read_instance_meta(instance_id)
        resume = bool(meta.get("resume_on_start"))
        conv_id = meta.get("current_conversation_id")
        if conv_id:
            RunStore(self.instances.agent_dir(instance_id)).update_run_status(
                str(conv_id), RunStatus.EXECUTING
            )
        await self.processes.start(instance_id, resume=resume)

    async def pause_instance(self, instance_id: str) -> None:
        meta = self.instances.read_instance_meta(instance_id)
        mode = meta.get("mode")
        conv_id = meta.get("current_conversation_id")
        if conv_id:
            RunStore(self.instances.agent_dir(instance_id)).update_run_status(
                str(conv_id), RunStatus.PAUSED
            )
        if mode == "interactive":
            await self._set_status(instance_id, InstanceStatus.PAUSED)
            return
        managed = self.processes.get(instance_id)
        if managed and managed.state != AgentProcessState.STOPPED:
            await self.processes.stop(instance_id)
        await self._set_status(instance_id, InstanceStatus.PAUSED)

    async def resume_instance(self, instance_id: str) -> None:
        meta = self.instances.read_instance_meta(instance_id)
        mode = meta.get("mode")
        conv_id = meta.get("current_conversation_id")
        if conv_id:
            RunStore(self.instances.agent_dir(instance_id)).update_run_status(
                str(conv_id), RunStatus.EXECUTING
            )
        if mode == "interactive":
            await self._set_status(instance_id, InstanceStatus.INTERACTIVE_IDLE)
            return
        await self.start_autonomous(instance_id)

    async def start_new_run(
        self,
        instance_id: str,
        *,
        goal: str,
        run_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        path = self.instances.agent_dir(instance_id)
        if not path.exists():
            raise FileNotFoundError(instance_id)
        meta = self.instances.read_instance_meta(instance_id)
        conversation_id = f"run-{_timestamp_suffix()}"
        self.instances.init_run(
            instance_id,
            conversation_id,
            goal=goal.strip(),
            run_options=run_options,
        )
        mode = meta.get("mode")
        if mode == "autonomous":
            self.processes.register(instance_id, path)
            await self.start_autonomous(instance_id)
        elif mode == "interactive":
            self.interactive.register(instance_id, path)
            await self._set_status(instance_id, InstanceStatus.INTERACTIVE_IDLE)
        return self.run_view(instance_id, conversation_id)

    async def stop_instance(self, instance_id: str) -> None:
        meta = self.instances.read_instance_meta(instance_id)
        mode = meta.get("mode")
        if mode == "interactive":
            await self.interactive.unregister(instance_id)
            await self._set_status(instance_id, InstanceStatus.STOPPED)
            return
        managed = self.processes.get(instance_id)
        if managed and managed.state != AgentProcessState.STOPPED:
            await self.processes.stop(instance_id)
        await self._set_status(instance_id, InstanceStatus.STOPPED)

    async def send_interactive(self, instance_id: str, message: str) -> None:
        session = self.interactive.get(instance_id)
        if session is None:
            path = self.instances.agent_dir(instance_id)
            if not path.exists():
                raise KeyError(instance_id)
            session = self.interactive.register(instance_id, path)
            await self._set_status(instance_id, InstanceStatus.INTERACTIVE_IDLE)

        async def status_cb(status: InstanceStatus) -> None:
            await self._set_status(instance_id, status)

        async def runner() -> None:
            await session.send_message(
                message,
                status_callback=status_cb,
                lifecycle=self,
            )

        asyncio.create_task(runner())

    def run_view(self, instance_id: str, conversation_id: str) -> dict[str, Any]:
        path = self.instances.agent_dir(instance_id)
        summary = RunStore(path).run_summary(conversation_id)
        return {"instance_id": instance_id, "conversation_id": conversation_id, **summary}

    def current_run_view(self, instance_id: str) -> dict[str, Any] | None:
        conv_id = self.instances.read_current_conversation_id(instance_id)
        if not conv_id:
            return None
        path = self.instances.agent_dir(instance_id)
        if not (path / "conversations" / conv_id / "run.json").exists():
            return None
        return self.run_view(instance_id, conv_id)

    def list_runs(self, instance_id: str) -> list[dict[str, Any]]:
        path = self.instances.agent_dir(instance_id)
        runs = RunStore(path).list_runs()
        return [self.run_view(instance_id, run.conversation_id) for run in runs]

    def instance_view(self, instance_id: str) -> dict[str, Any]:
        path = self.instances.agent_dir(instance_id)
        if not path.exists():
            raise FileNotFoundError(instance_id)
        meta = self.instances.read_instance_meta(instance_id)
        mode = meta.get("mode")
        process = self.processes.get(instance_id)
        interactive = self.interactive.get(instance_id)

        process_state = process.state.value if process else "stopped"
        pid = process.pid if process else None
        error = process.error if process else None

        if mode == "interactive" and interactive is not None:
            process_state = interactive.state.value
            error = interactive.last_error

        current_run = self.current_run_view(instance_id)

        return {
            "instance_id": instance_id,
            "definition_id": meta.get("definition_id") or meta.get("template_id"),
            "mode": mode,
            "instance_status": meta.get("instance_status"),
            "spawned_at": meta.get("spawned_at"),
            "path": str(path),
            "process_state": process_state,
            "pid": pid,
            "error": error,
            "config": meta,
            "current_conversation_id": meta.get("current_conversation_id"),
            "current_run": current_run,
        }

    def fleet(self) -> list[dict[str, Any]]:
        views: list[dict[str, Any]] = []
        for summary in self.instances.list_instances():
            try:
                views.append(self.instance_view(summary.instance_id))
            except FileNotFoundError:
                continue
            except Exception as exc:
                logger.warning(
                    "instance_view_skipped",
                    instance_id=summary.instance_id,
                    error=str(exc),
                )
        return views
