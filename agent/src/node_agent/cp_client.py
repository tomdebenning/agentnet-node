"""Control-plane HTTP client with the GatewayClient surface plus puller ops."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from shared.schemas import AgentHeartbeat, PullerHeartbeat, Response, Task


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.ConnectTimeout | httpx.ConnectError):
        return False
    return isinstance(exc, httpx.TransportError | httpx.TimeoutException)


class ControlPlaneClient:
    """Talks to the control plane directly (no node gateway required)."""

    def __init__(self, base_url: str, *, timeout: float = 30.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _retrying(self):
        return retry(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1),
            retry=retry_if_exception(_is_retryable),
        )

    async def post_task(self, task: Task) -> dict[str, Any]:
        @self._retrying()
        async def _do() -> httpx.Response:
            return await self._client.post("/tasks", json=task.model_dump(mode="json"))

        response = await _do()
        response.raise_for_status()
        return response.json() if response.content else {}

    async def get_responses(self, agent_id: str, max: int = 10) -> list[Response]:
        @self._retrying()
        async def _do() -> httpx.Response:
            return await self._client.get(
                "/responses",
                params={"agent_id": agent_id, "max": max},
            )

        response = await _do()
        if response.status_code == 204:
            return []
        response.raise_for_status()
        data = response.json()
        items = data if isinstance(data, list) else data.get("responses", [])
        return [Response.model_validate(item) for item in items]

    async def post_heartbeat(self, heartbeat: AgentHeartbeat) -> None:
        response = await self._client.post(
            "/heartbeat/agent",
            json=heartbeat.model_dump(mode="json"),
        )
        response.raise_for_status()

    async def web_search(self, query: str, count: int = 5) -> str:
        return "Error: web_search requires the node gateway; use run_command and files instead."

    async def fetch_url(self, url: str) -> str:
        return "Error: fetch_url requires the node gateway; use run_command and files instead."

    async def post_puller_heartbeat(self, heartbeat: PullerHeartbeat) -> None:
        response = await self._client.post(
            "/heartbeat/puller",
            json=heartbeat.model_dump(mode="json"),
        )
        response.raise_for_status()

    async def fetch_next_task(self, puller_name: str) -> Task | None:
        response = await self._client.get(
            "/tasks/next",
            params={"puller_name": puller_name},
        )
        if response.status_code == 204:
            return None
        response.raise_for_status()
        return Task.model_validate(response.json())

    async def post_response(self, payload: Response) -> None:
        response = await self._client.post(
            "/responses",
            json=payload.model_dump(mode="json"),
        )
        response.raise_for_status()
