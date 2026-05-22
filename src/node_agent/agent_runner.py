"""Long-running agent process."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import structlog

from gateway.schemas import AgentHeartbeat
from node_agent.conversation import run_conversation_turn
from node_agent.conversation_store import ConversationStore
from node_agent.gateway_client import GatewayClient
from node_agent.markdown_config import AgentSettings, load_agent_settings
from node_agent.tools.registry import ToolRegistry

logger = structlog.get_logger(__name__)


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


async def run_agent(agent_dir: Path, gateway_url: str) -> None:
    settings = load_agent_settings(agent_dir)
    gateway = GatewayClient(gateway_url)
    store = ConversationStore(settings.paths.conversation_db)
    await store.connect()
    tools = ToolRegistry(settings, gateway)

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
                        conversation_id="interactive",
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

    # Non-interactive: idle process until terminated (managed lifecycle).
    status["value"] = "idle"
    try:
        await stop_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        stop_event.set()
        heartbeat_task.cancel()
        await gateway.aclose()


def resolve_gateway_url(explicit: str | None) -> str:
    if explicit:
        return explicit.rstrip("/")
    env = os.environ.get("AGENTNET_GATEWAY_URL", "").strip()
    if env:
        return env.rstrip("/")
    return "http://127.0.0.1:8080"
