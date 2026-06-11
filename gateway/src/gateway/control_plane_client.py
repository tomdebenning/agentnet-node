"""HTTP client for the control plane."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from gateway.config import ControlPlaneSection
from shared.schemas import AgentHeartbeat, NodeHeartbeat, Response, Task


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.ConnectTimeout | httpx.ConnectError):
        return False
    return isinstance(exc, httpx.TransportError | httpx.TimeoutException)


class ControlPlaneClient:
    def __init__(self, config: ControlPlaneSection, client: httpx.AsyncClient | None = None) -> None:
        self._config = config
        self._owns_client = client is None
        connect_timeout = min(2.0, config.request_timeout_seconds)
        self._client = client or httpx.AsyncClient(
            base_url=config.url.rstrip("/"),
            timeout=httpx.Timeout(
                connect=connect_timeout,
                read=config.request_timeout_seconds,
                write=config.request_timeout_seconds,
                pool=config.request_timeout_seconds,
            ),
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _retrying(self):
        return retry(
            reraise=True,
            stop=stop_after_attempt(self._config.max_retries),
            wait=wait_exponential(
                multiplier=self._config.retry_backoff_base_seconds,
                min=self._config.retry_backoff_base_seconds,
            ),
            retry=retry_if_exception(_is_retryable),
        )

    async def post_task(self, task: Task) -> dict[str, Any]:
        @self._retrying()
        async def _do() -> httpx.Response:
            return await self._client.post("/tasks", json=task.model_dump(mode="json"))

        response = await _do()
        response.raise_for_status()
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    async def get_responses(self, agent_id: str, max: int) -> list[Response]:
        @self._retrying()
        async def _do() -> httpx.Response:
            return await self._client.get("/responses", params={"agent_id": agent_id, "max": max})

        response = await _do()
        if response.status_code == 204:
            return []
        response.raise_for_status()
        data = response.json()
        items = data if isinstance(data, list) else data.get("responses", [])
        return [Response.model_validate(item) for item in items]

    async def post_agent_heartbeat(self, heartbeat: AgentHeartbeat) -> None:
        response = await self._client.post(
            "/heartbeat/agent",
            json=heartbeat.model_dump(mode="json"),
        )
        response.raise_for_status()

    async def post_node_heartbeat(self, heartbeat: NodeHeartbeat) -> None:
        response = await self._client.post(
            "/heartbeat/node",
            json=heartbeat.model_dump(mode="json"),
        )
        response.raise_for_status()

    @property
    def base_url(self) -> str:
        return str(self._client.base_url)

    async def check_health(self) -> tuple[bool, str | None]:
        """Return (ok, error_message). Does not retry — for status probes."""
        try:
            response = await self._client.get("/health")
            if response.status_code != 200:
                return False, f"HTTP {response.status_code}"
            payload = response.json()
            if payload.get("status") == "ok":
                return True, None
            return False, f"status={payload.get('status')!r}"
        except httpx.HTTPError as exc:
            return False, str(exc) or type(exc).__name__
