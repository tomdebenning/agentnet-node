"""Port conflict handling tests."""

from __future__ import annotations

import pytest

from gateway.port_conflict import (
    PortInUseError,
    ensure_port_available,
    port_is_in_use,
    process_description,
    prompt_shutdown_running_gateway,
)


def test_port_is_in_use_false(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSocket:
        def __enter__(self) -> FakeSocket:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def settimeout(self, _value: float) -> None:
            return None

        def connect_ex(self, _addr: tuple[str, int]) -> int:
            return 1

    monkeypatch.setattr("gateway.port_conflict.socket.socket", lambda *a, **k: FakeSocket())
    assert port_is_in_use(8080) is False


def test_port_is_in_use_true(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSocket:
        def __enter__(self) -> FakeSocket:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def settimeout(self, _value: float) -> None:
            return None

        def connect_ex(self, _addr: tuple[str, int]) -> int:
            return 0

    monkeypatch.setattr("gateway.port_conflict.socket.socket", lambda *a, **k: FakeSocket())
    assert port_is_in_use(8080) is True


def test_prompt_shutdown_accepts_yes() -> None:
    assert prompt_shutdown_running_gateway(8080, [123], input_fn=lambda _prompt: "yes") is True


def test_prompt_shutdown_rejects_no() -> None:
    assert prompt_shutdown_running_gateway(8080, [123], input_fn=lambda _prompt: "n") is False


def test_ensure_port_available_no_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gateway.port_conflict.port_is_in_use", lambda port, host="127.0.0.1": False)
    ensure_port_available("127.0.0.1", 8080, interactive=True)


def test_ensure_port_available_non_interactive_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gateway.port_conflict.port_is_in_use", lambda port, host="127.0.0.1": True)
    with pytest.raises(PortInUseError, match="already in use"):
        ensure_port_available("127.0.0.1", 8080, interactive=False)


def test_ensure_port_available_kills_on_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gateway.port_conflict.port_is_in_use", lambda port, host="127.0.0.1": True)
    monkeypatch.setattr("gateway.port_conflict.listener_pids", lambda port: [4242])
    monkeypatch.setattr(
        "gateway.port_conflict.prompt_shutdown_running_gateway",
        lambda port, pids, input_fn=input: True,
    )
    killed: list[int] = []
    monkeypatch.setattr("gateway.port_conflict.kill_processes", lambda pids: killed.extend(pids))
    monkeypatch.setattr("gateway.port_conflict._wait_for_port_free", lambda port, host, timeout_seconds=5.0: True)

    ensure_port_available("127.0.0.1", 8080, interactive=True)
    assert killed == [4242]


def test_ensure_port_available_cancelled_on_no(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gateway.port_conflict.port_is_in_use", lambda port, host="127.0.0.1": True)
    monkeypatch.setattr("gateway.port_conflict.listener_pids", lambda port: [4242])
    monkeypatch.setattr(
        "gateway.port_conflict.prompt_shutdown_running_gateway",
        lambda port, pids, input_fn=input: False,
    )
    with pytest.raises(PortInUseError, match="cancelled"):
        ensure_port_available("127.0.0.1", 8080, interactive=True)


def test_process_description_fallback() -> None:
    assert process_description(999999999) == "pid 999999999"
