"""Long-running agent process."""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
from pathlib import Path

import structlog

from shared.run_store import RunStatus, RunStore
from shared.schemas import AgentHeartbeat
from node_agent.conversation import run_conversation_turn
from node_agent.conversation_store import ConversationStore
from node_agent.gateway_client import GatewayClient
from node_agent.markdown_config import AgentSettings, load_agent_settings
from node_agent.tools.registry import ToolRegistry

logger = structlog.get_logger(__name__)

RESUME_PROMPT = "Continue executing the plan toward the goal from where you left off."


async def heartbeat_loop(
    settings: AgentSettings,
    gateway: GatewayClient,
    stop_event: asyncio.Event,
    status_getter,
) -> None:
    while not stop_event.is_set():
        heartbeat = AgentHeartbeat(
            agent_id=settings.agent_id,
            status=status_getter(),
            descriptive_info={"node_agent": True, "directory": str(settings.paths.root)},
        )
        try:
            await gateway.post_heartbeat(heartbeat)
        except Exception as exc:
            logger.warning("heartbeat_failed", error=str(exc))
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            continue


async def run_agent(agent_dir: Path, gateway_url: str, *, resume: bool = False) -> None:
    settings = load_agent_settings(agent_dir)
    gateway = GatewayClient(gateway_url)
    store = ConversationStore(settings.paths.conversation_db)
    await store.connect()

    conversation_id = _current_conversation_id(settings)
    tools = ToolRegistry(settings, gateway, conversation_id=conversation_id)
    run_store = RunStore(settings.paths.root)

    status = {"value": "idle"}
    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        heartbeat_loop(settings, gateway, stop_event, lambda: status["value"])
    )

    logger.info("agent_ready", agent_id=settings.agent_id, gateway=gateway_url)

    if sys.stdin.isatty():
        print(f"Agent {settings.agent_id} ready. Type messages (Ctrl-D to exit).")
        try:
            while True:
                line = await asyncio.to_thread(sys.stdin.readline)
                if not line:
                    break
                user_input = line.strip()
                if not user_input:
                    continue
                status["value"] = "working"
                try:
                    reply = await run_conversation_turn(
                        settings=settings,
                        gateway=gateway,
                        store=store,
                        tools=tools,
                        conversation_id=conversation_id,
                        user_input=user_input,
                    )
                    print(reply)
                except Exception as exc:
                    print(f"Error: {exc}")
                finally:
                    status["value"] = "idle"
        finally:
            stop_event.set()
            heartbeat_task.cancel()
            await gateway.aclose()
        return

    success = await _run_managed_task(
        settings=settings,
        gateway=gateway,
        store=store,
        tools=tools,
        run_store=run_store,
        conversation_id=conversation_id,
        status=status,
        resume=resume,
    )
    stop_event.set()
    heartbeat_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await heartbeat_task
    await gateway.aclose()
    raise SystemExit(0 if success else 1)


def _current_conversation_id(settings: AgentSettings) -> str:
    from shared.markdown_io import parse_markdown_document

    meta, _ = parse_markdown_document(settings.paths.config_file.read_text(encoding="utf-8"))
    return str(meta.get("current_conversation_id") or settings.task_conversation_id or "task")


def _write_instance_status(settings: AgentSettings, status: str) -> None:
    from shared.markdown_io import parse_markdown_document, render_markdown_document

    meta, body = parse_markdown_document(settings.paths.config_file.read_text(encoding="utf-8"))
    meta["instance_status"] = status
    settings.paths.config_file.write_text(
        render_markdown_document(meta, body),
        encoding="utf-8",
    )


async def _run_managed_task(
    *,
    settings: AgentSettings,
    gateway: GatewayClient,
    store: ConversationStore,
    tools: ToolRegistry,
    run_store: RunStore,
    conversation_id: str,
    status: dict[str, str],
    resume: bool = False,
) -> bool:
    try:
        run = run_store.get_run(conversation_id)
    except FileNotFoundError:
        logger.warning("run_missing", conversation_id=conversation_id)
        _write_instance_status(settings, "error")
        return False

    goal = run.goal.strip()
    if not goal:
        logger.warning("goal_empty", agent_id=settings.agent_id)
        _write_instance_status(settings, "error")
        return False

    if resume or run.status == RunStatus.PAUSED:
        user_input = RESUME_PROMPT
    else:
        await store.clear_conversation(conversation_id)
        user_input = goal

    status["value"] = "working"
    _write_instance_status(settings, "running")
    run_store.update_run_status(conversation_id, RunStatus.EXECUTING)
    logger.info(
        "run_starting",
        agent_id=settings.agent_id,
        conversation_id=conversation_id,
        goal_chars=len(goal),
        resume=resume,
    )
    try:
        reply = await run_conversation_turn(
            settings=settings,
            gateway=gateway,
            store=store,
            tools=tools,
            conversation_id=conversation_id,
            user_input=user_input,
            run_options=run.options,
        )
        logger.info("run_turn_completed", agent_id=settings.agent_id, reply_chars=len(reply))
    except Exception as exc:
        status["value"] = "error"
        run_store.update_run_status(conversation_id, RunStatus.ERROR, error=str(exc))
        _write_instance_status(settings, "error")
        logger.error("run_failed", agent_id=settings.agent_id, error=str(exc))
        return False

    run = run_store.get_run(conversation_id)
    if run.status == RunStatus.DONE:
        status["value"] = "completed"
        _write_instance_status(settings, "completed")
        return True

    run_store.update_run_status(
        conversation_id,
        RunStatus.ERROR,
        error="goal not marked done",
    )
    status["value"] = "error"
    _write_instance_status(settings, "error")
    logger.error("run_incomplete", agent_id=settings.agent_id)
    return False


def resolve_gateway_url(explicit: str | None) -> str:
    if explicit:
        return explicit.rstrip("/")
    env = os.environ.get("AGENTNET_GATEWAY_URL", "").strip()
    if env:
        return env.rstrip("/")
    return "http://127.0.0.1:8080"
