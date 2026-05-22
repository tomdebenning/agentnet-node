"""Textual API client."""

from __future__ import annotations

from typing import Any

import httpx


class ApiClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8080") -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=30.0)

    def close(self) -> None:
        self._client.close()

    def status(self) -> dict[str, Any]:
        response = self._client.get("/api/status")
        response.raise_for_status()
        return response.json()

    def connectivity(self) -> dict[str, Any]:
        """Probe gateway and report control-plane reachability from gateway."""
        try:
            status = self.status()
        except httpx.HTTPError as exc:
            return {
                "gateway_url": self.base_url,
                "gateway_connected": False,
                "gateway_error": str(exc) or type(exc).__name__,
                "control_plane_url": None,
                "control_plane_connected": False,
                "control_plane_error": None,
                "node_id": None,
                "agent_count": None,
                "running_agent_count": None,
            }

        return {
            "gateway_url": self.base_url,
            "gateway_connected": True,
            "gateway_error": None,
            "control_plane_url": status.get("control_plane_url"),
            "control_plane_connected": bool(status.get("control_plane_connected")),
            "control_plane_error": status.get("control_plane_error"),
            "node_id": status.get("node_id"),
            "agent_count": status.get("agent_count"),
            "running_agent_count": status.get("running_agent_count"),
        }

    def list_agents(self) -> list[dict[str, Any]]:
        return self._client.get("/api/agents").json()["agents"]

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        return self._client.get(f"/api/agents/{agent_id}").json()

    def create_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._client.post("/api/agents", json=payload).json()

    def delete_agent(self, agent_id: str) -> dict[str, Any]:
        return self._client.delete(f"/api/agents/{agent_id}").json()

    def start_agent(self, agent_id: str) -> dict[str, Any]:
        return self._client.post(f"/api/agents/{agent_id}/start").json()

    def stop_agent(self, agent_id: str) -> dict[str, Any]:
        return self._client.post(f"/api/agents/{agent_id}/stop").json()

    def read_file(self, agent_id: str, kind: str) -> dict[str, Any]:
        return self._client.get(f"/api/agents/{agent_id}/files/{kind}").json()

    def write_file(self, agent_id: str, kind: str, content: str) -> dict[str, Any]:
        return self._client.put(
            f"/api/agents/{agent_id}/files/{kind}",
            json={"content": content},
        ).json()
