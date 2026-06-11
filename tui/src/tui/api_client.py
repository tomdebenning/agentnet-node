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

    def create_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = dict(payload)
        if "agent_id" in body and "instance_id" not in body:
            body["instance_id"] = body.pop("agent_id")
        response = self._client.post("/api/fleet/instances", json=body)
        response.raise_for_status()
        return response.json()

    def delete_agent(self, instance_id: str) -> dict[str, Any]:
        response = self._client.delete(f"/api/fleet/instances/{instance_id}")
        response.raise_for_status()
        return response.json()

    def start_agent(self, instance_id: str) -> dict[str, Any]:
        response = self._client.post(f"/api/fleet/instances/{instance_id}/start")
        response.raise_for_status()
        return response.json()

    def stop_agent(self, instance_id: str) -> dict[str, Any]:
        response = self._client.post(f"/api/fleet/instances/{instance_id}/stop")
        response.raise_for_status()
        return response.json()

    def read_file(self, instance_id: str, kind: str) -> dict[str, Any]:
        response = self._client.get(f"/api/fleet/instances/{instance_id}/files/{kind}")
        response.raise_for_status()
        return response.json()

    def read_file_raw(self, instance_id: str, kind: str, *, default: str = "") -> str:
        """Return markdown raw text, or default when the file is missing."""
        try:
            payload = self.read_file(instance_id, kind)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return default
            raise
        raw = payload.get("raw")
        if raw is None:
            return default
        return str(raw)

    def write_file(self, instance_id: str, kind: str, content: str) -> dict[str, Any]:
        response = self._client.put(
            f"/api/fleet/instances/{instance_id}/files/{kind}",
            json={"content": content},
        )
        response.raise_for_status()
        return response.json()

    def list_conversations(self, instance_id: str) -> list[dict[str, Any]]:
        response = self._client.get(f"/api/fleet/instances/{instance_id}/conversations")
        response.raise_for_status()
        return response.json()["conversations"]

    def get_conversation(self, instance_id: str, conversation_id: str) -> dict[str, Any]:
        response = self._client.get(
            f"/api/fleet/instances/{instance_id}/conversations/{conversation_id}"
        )
        response.raise_for_status()
        return response.json()

    def list_workspace(self, instance_id: str, path: str = ".") -> dict[str, Any]:
        response = self._client.get(
            f"/api/fleet/instances/{instance_id}/workspace",
            params={"path": path},
        )
        response.raise_for_status()
        return response.json()

    def read_workspace_file(self, instance_id: str, path: str) -> dict[str, Any]:
        response = self._client.get(
            f"/api/fleet/instances/{instance_id}/workspace/file",
            params={"path": path},
        )
        response.raise_for_status()
        return response.json()

    def list_databases(self, instance_id: str) -> list[str]:
        response = self._client.get(f"/api/fleet/instances/{instance_id}/databases")
        response.raise_for_status()
        return response.json()["databases"]

    def get_database(self, instance_id: str, db_name: str) -> dict[str, Any]:
        response = self._client.get(f"/api/fleet/instances/{instance_id}/databases/{db_name}")
        response.raise_for_status()
        return response.json()

    def spawn_defaults(self) -> dict[str, Any]:
        response = self._client.get("/api/spawn-defaults")
        response.raise_for_status()
        return response.json()

    def list_definitions(self) -> list[dict[str, Any]]:
        response = self._client.get("/api/definitions")
        response.raise_for_status()
        return response.json()["definitions"]

    def create_definition(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = dict(payload)
        if "definition_id" not in body and "template_id" in body:
            body["definition_id"] = body.pop("template_id")
        response = self._client.post("/api/definitions", json=body)
        response.raise_for_status()
        return response.json()

    def get_definition(self, definition_id: str) -> dict[str, Any]:
        response = self._client.get(f"/api/definitions/{definition_id}")
        response.raise_for_status()
        return response.json()

    def write_definition_persona(
        self, definition_id: str, content: str, *, mark_reviewed: bool = False
    ) -> dict[str, Any]:
        response = self._client.put(
            f"/api/definitions/{definition_id}/files/persona",
            json={"content": content, "mark_reviewed": mark_reviewed},
        )
        response.raise_for_status()
        return response.json()

    def write_definition_skills(
        self, definition_id: str, content: str, *, mark_reviewed: bool = False
    ) -> dict[str, Any]:
        response = self._client.put(
            f"/api/definitions/{definition_id}/files/skills",
            json={"content": content, "mark_reviewed": mark_reviewed},
        )
        response.raise_for_status()
        return response.json()

    def write_definition_memory(self, definition_id: str, content: str) -> dict[str, Any]:
        response = self._client.put(
            f"/api/definitions/{definition_id}/files/memory",
            json={"content": content},
        )
        response.raise_for_status()
        return response.json()

    def set_definition_uses_memory(self, definition_id: str, uses_memory: bool) -> dict[str, Any]:
        response = self._client.put(
            f"/api/definitions/{definition_id}/uses-memory",
            json={"uses_memory": uses_memory},
        )
        response.raise_for_status()
        return response.json()

    def delete_definition(self, definition_id: str) -> dict[str, Any]:
        response = self._client.delete(f"/api/definitions/{definition_id}")
        response.raise_for_status()
        return response.json()

    def spawn_instance(self, definition_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post(f"/api/definitions/{definition_id}/spawn", json=payload)
        response.raise_for_status()
        return response.json()

    def list_instances(self) -> list[dict[str, Any]]:
        response = self._client.get("/api/fleet/instances")
        response.raise_for_status()
        return response.json()["instances"]

    def get_instance(self, instance_id: str) -> dict[str, Any]:
        response = self._client.get(f"/api/fleet/instances/{instance_id}")
        response.raise_for_status()
        return response.json()

    def pause_instance(self, instance_id: str) -> dict[str, Any]:
        response = self._client.post(f"/api/fleet/instances/{instance_id}/pause")
        response.raise_for_status()
        return response.json()

    def resume_instance(self, instance_id: str) -> dict[str, Any]:
        response = self._client.post(f"/api/fleet/instances/{instance_id}/resume")
        response.raise_for_status()
        return response.json()

    def stop_instance(self, instance_id: str) -> dict[str, Any]:
        response = self._client.post(f"/api/fleet/instances/{instance_id}/stop")
        response.raise_for_status()
        return response.json()

    def recent_completions(self, limit: int = 20) -> list[dict[str, Any]]:
        response = self._client.get("/api/fleet/completions/recent", params={"limit": limit})
        response.raise_for_status()
        return response.json()["completions"]

    def post_interactive_message(self, instance_id: str, message: str) -> dict[str, Any]:
        response = self._client.post(
            f"/api/fleet/instances/{instance_id}/interactive/messages",
            json={"message": message},
        )
        response.raise_for_status()
        return response.json()

    def poll_interactive(self, instance_id: str) -> dict[str, Any]:
        response = self._client.get(f"/api/fleet/instances/{instance_id}/interactive")
        response.raise_for_status()
        return response.json()
