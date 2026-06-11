"""Connection status formatting tests."""

from __future__ import annotations

from tui.connection_status import format_connection_status, format_connection_subtitle


def test_format_when_gateway_unreachable() -> None:
    text = format_connection_status(
        {
            "gateway_url": "http://127.0.0.1:8080",
            "gateway_connected": False,
            "gateway_error": "Connection refused",
        }
    )
    assert "Gateway:" in text
    assert "DISCONNECTED" in text
    assert "Control plane: (unknown" in text


def test_format_when_all_connected() -> None:
    text = format_connection_status(
        {
            "gateway_url": "http://127.0.0.1:8080",
            "gateway_connected": True,
            "control_plane_url": "http://127.0.0.1:8000",
            "control_plane_connected": True,
            "node_id": "node-01",
            "agent_count": 2,
            "running_agent_count": 1,
        }
    )
    assert "Gateway:" in text
    assert "connected" in text
    assert "http://127.0.0.1:8000" in text
    assert "Node: node-01" in text


def test_subtitle_disconnected_control_plane() -> None:
    sub = format_connection_subtitle(
        {
            "gateway_url": "http://127.0.0.1:8080",
            "gateway_connected": True,
            "control_plane_url": "http://127.0.0.1:8000",
            "control_plane_connected": False,
        }
    )
    assert "Control plane DISCONNECTED" in sub
