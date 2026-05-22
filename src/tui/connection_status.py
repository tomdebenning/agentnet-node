"""Format connection status lines for the TUI."""

from __future__ import annotations

from typing import Any


def _flag(connected: bool) -> str:
    return "connected" if connected else "DISCONNECTED"


def format_connection_status(info: dict[str, Any]) -> str:
    lines: list[str] = []

    if info.get("gateway_connected"):
        lines.append(f"Gateway: {_flag(True)}  {info['gateway_url']}")
    else:
        err = info.get("gateway_error") or "unreachable"
        lines.append(f"Gateway: {_flag(False)}  {info['gateway_url']}  ({err})")

    cp_url = info.get("control_plane_url")
    if not info.get("gateway_connected"):
        lines.append("Control plane: (unknown — gateway unreachable)")
    elif cp_url:
        if info.get("control_plane_connected"):
            lines.append(f"Control plane: {_flag(True)}  {cp_url}")
        else:
            err = info.get("control_plane_error") or "unreachable"
            lines.append(f"Control plane: {_flag(False)}  {cp_url}  ({err})")
    else:
        lines.append("Control plane: (not reported by gateway)")

    node_id = info.get("node_id")
    if node_id and info.get("gateway_connected"):
        running = info.get("running_agent_count")
        total = info.get("agent_count")
        if running is not None and total is not None:
            lines.append(f"Node: {node_id}  ·  {running}/{total} agents running")

    return "\n".join(lines)


def format_connection_subtitle(info: dict[str, Any]) -> str:
    if not info.get("gateway_connected"):
        return f"Gateway DISCONNECTED · {info['gateway_url']}"

    cp_url = info.get("control_plane_url") or "?"
    if info.get("control_plane_connected"):
        return f"Gateway OK · Control plane OK · {cp_url}"

    return f"Gateway OK · Control plane DISCONNECTED · {cp_url}"
