"""Gateway heartbeat loop for control-plane node registration."""

from __future__ import annotations

import asyncio

import httpx
import structlog

from gateway.agent_manager import AgentManager, AgentProcessState
from gateway.config import GatewayConfig
from gateway.control_plane_client import ControlPlaneClient
from shared.schemas import NodeHeartbeat

logger = structlog.get_logger(__name__)


async def node_heartbeat_loop(
    config: GatewayConfig,
    client: ControlPlaneClient,
    manager: AgentManager,
    stop_event: asyncio.Event,
) -> None:
    while not stop_event.is_set():
        busy = any(item.state == AgentProcessState.RUNNING for item in manager.list_managed())
        status = "busy" if busy else "idle"
        heartbeat = NodeHeartbeat(
            node_id=config.node.id,
            status=status,
            agent_count=len(manager.list_managed()),
            running_agent_count=manager.running_count(),
            descriptive_info=config.node.descriptive_info,
        )
        try:
            await client.post_node_heartbeat(heartbeat)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.warning(
                    "node_heartbeat_not_supported",
                    url=str(exc.request.url),
                    hint=(
                        "Control plane is missing /heartbeat/node — deploy the updated "
                        "control-plane from this repo, then restart the service on that host"
                    ),
                )
            else:
                logger.warning("node_heartbeat_failed", error=str(exc))
        except Exception as exc:
            logger.warning("node_heartbeat_failed", error=str(exc))

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=config.heartbeat.interval_seconds)
        except asyncio.TimeoutError:
            continue
