"""Format connection status lines for the TUI."""

from __future__ import annotations

from typing import Any

from textual.widgets import Static


def _flag(connected: bool) -> str:
    if connected:
        return "[state-ready]✅ connected[/]"
    return "[state-error]🔴 DISCONNECTED[/]"


def format_connection_status(info: dict[str, Any]) -> str:
    lines: list[str] = []

    if info.get("gateway_connected"):
        lines.append(f"Gateway: {_flag(True)}  [state-info]{info['gateway_url']}[/]")
    else:
        err = info.get("gateway_error") or "unreachable"
        lines.append(
            f"Gateway: {_flag(False)}  [state-info]{info['gateway_url']}[/]  ({err})"
        )

    cp_url = info.get("control_plane_url")
    if not info.get("gateway_connected"):
        lines.append("[state-info]Control plane: (unknown — gateway unreachable)[/]")
    elif cp_url:
        if info.get("control_plane_connected"):
            lines.append(f"Control plane: {_flag(True)}  [state-info]{cp_url}[/]")
        else:
            err = info.get("control_plane_error") or "unreachable"
            lines.append(
                f"Control plane: {_flag(False)}  [state-info]{cp_url}[/]  ({err})"
            )
    else:
        lines.append("[state-info]Control plane: (not reported by gateway)[/]")

    node_id = info.get("node_id")
    if node_id and info.get("gateway_connected"):
        running = info.get("running_agent_count")
        total = info.get("agent_count")
        if running is not None and total is not None:
            lines.append(f"[state-info]Node: {node_id}  ·  {running}/{total} agents running[/]")

    return "\n".join(lines)


def format_connection_subtitle(info: dict[str, Any]) -> str:
    if not info.get("gateway_connected"):
        return f"[state-error]🔴 Gateway DISCONNECTED[/] · {info['gateway_url']}"

    cp_url = info.get("control_plane_url") or "?"
    if info.get("control_plane_connected"):
        return f"[state-ready]✅ Gateway OK[/] · [state-ready]Control plane OK[/] · {cp_url}"

    return f"[state-ready]✅ Gateway OK[/] · [state-review]🟠 Control plane DISCONNECTED[/] · {cp_url}"


def format_gateway_unreachable_hint(info: dict[str, Any]) -> str:
    """Multi-line hint for list views when the gateway cannot be reached."""
    err = info.get("gateway_error") or "unreachable"
    url = info.get("gateway_url") or "?"
    return (
        f"[state-error]🔴 Gateway disconnected[/]\n"
        f"[state-info]{url}[/] — {err}\n"
        f"Start the gateway: [state-ready]./run-gateway.sh[/] then press [state-info]r[/] to refresh"
    )


def refresh_connection_panel(app: Any, screen: Any) -> dict[str, Any]:
    """Update header subtitle and optional #connection-status on the active screen."""
    info = app.api_client.connectivity()
    app.update_connection_subtitle(info)
    try:
        panel = screen.query_one("#connection-status", Static)
    except Exception:
        return info
    panel.update(format_connection_status(info))
    return info
