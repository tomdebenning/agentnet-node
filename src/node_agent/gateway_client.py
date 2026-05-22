"""Gateway HTTP client for slim agents."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from gateway.schemas import AgentHeartbeat, Response, Task


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.ConnectTimeout | httpx.ConnectError):
        return False
    return isinstance(exc, httpx.TransportError | httpx.TimeoutException)


class GatewayClient:
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
            return await self._client.post("/proxy/tasks", json=task.model_dump(mode="json"))

        response = await _do()
        response.raise_for_status()
        return response.json() if response.content else {}

    async def get_responses(self, agent_id: str, max: int = 10) -> list[Response]:
        @self._retrying()
        async def _do() -> httpx.Response:
            return await self._client.get(
                "/proxy/responses",
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
            "/proxy/heartbeat/agent",
            json=heartbeat.model_dump(mode="json"),
        )
        response.raise_for_status()

    async def web_search(self, query: str, count: int = 5) -> str:
        response = await self._client.post(
            "/proxy/tools/search",
            json={"query": query, "count": count},
        )
        response.raise_for_status()
        return response.json().get("formatted", "")

    async def fetch_url(self, url: str) -> str:
        response = await self._client.post("/proxy/tools/fetch", json={"url": url})
        response.raise_for_status()
        return response.json().get("content", "")
