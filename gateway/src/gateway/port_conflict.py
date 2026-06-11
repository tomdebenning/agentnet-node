"""Detect port conflicts and optionally stop the process using the port."""

from __future__ import annotations

import contextlib
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


class PortInUseError(RuntimeError):
    """Raised when the listen port is occupied and cannot be freed."""


def port_is_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if something accepts TCP connections on the port."""
    check_host = "127.0.0.1" if host in ("0.0.0.0", "::", "[::]") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        try:
            return sock.connect_ex((check_host, port)) == 0
        except OSError:
            return False


def listener_pids(port: int) -> list[int]:
    """Return PIDs listening on the given TCP port (best effort)."""
    pids: set[int] = set()

    try:
        output = subprocess.check_output(
            ["fuser", "-n", "tcp", str(port)],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        for token in output.split():
            if token.isdigit():
                pids.add(int(token))
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    if not pids:
        try:
            output = subprocess.check_output(
                ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                stderr=subprocess.DEVNULL,
                text=True,
            )
            for line in output.splitlines():
                line = line.strip()
                if line.isdigit():
                    pids.add(int(line))
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass

    if not pids:
        try:
            output = subprocess.check_output(
                ["ss", "-ltnp", f"sport = :{port}"],
                stderr=subprocess.DEVNULL,
                text=True,
            )
            for line in output.splitlines():
                if "pid=" not in line:
                    continue
                for fragment in line.split("pid=")[1:]:
                    digits = ""
                    for char in fragment:
                        if char.isdigit():
                            digits += char
                        else:
                            break
                    if digits:
                        pids.add(int(digits))
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass

    return sorted(pids)


def process_description(pid: int) -> str:
    proc_cmd = Path(f"/proc/{pid}/cmdline")
    try:
        cmdline = proc_cmd.read_bytes().replace(b"\0", b" ").decode().strip()
        if cmdline:
            return f"pid {pid}: {cmdline}"
    except OSError:
        pass
    return f"pid {pid}"


def _wait_for_port_free(port: int, host: str, timeout_seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not port_is_in_use(port, host):
            return True
        time.sleep(0.1)
    return not port_is_in_use(port, host)


def kill_processes(pids: list[int], *, wait_seconds: float = 5.0) -> None:
    """Terminate processes, escalating to SIGKILL if needed."""
    alive = [pid for pid in pids if pid != os.getpid()]
    if not alive:
        return

    for pid in alive:
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGTERM)

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        alive = [pid for pid in alive if _process_exists(pid)]
        if not alive:
            return
        time.sleep(0.1)

    for pid in alive:
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def prompt_shutdown_running_gateway(
    port: int,
    pids: list[int],
    *,
    input_fn=input,
) -> bool:
    print(f"\nPort {port} is already in use.")
    if pids:
        print("Process(es) listening on that port:")
        for pid in pids:
            print(f"  {process_description(pid)}")
    else:
        print("Could not determine which process is using the port.")
    answer = input_fn("Shut down the running gateway? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def ensure_port_available(
    host: str,
    port: int,
    *,
    interactive: bool | None = None,
    input_fn=input,
) -> None:
    """Prompt to stop an existing listener, or exit when the port stays busy."""
    if not port_is_in_use(port, host):
        return

    is_interactive = sys.stdin.isatty() if interactive is None else interactive
    if not is_interactive:
        raise PortInUseError(
            f"Port {port} is already in use. Stop the existing gateway or choose another port."
        )

    pids = listener_pids(port)
    if not prompt_shutdown_running_gateway(port, pids, input_fn=input_fn):
        raise PortInUseError(f"Port {port} is already in use. Startup cancelled.")

    if pids:
        kill_processes(pids)
    elif not _wait_for_port_free(port, host, timeout_seconds=0.5):
        raise PortInUseError(
            f"Port {port} is in use but no listener PID was found. Stop it manually and retry."
        )

    if not _wait_for_port_free(port, host):
        raise PortInUseError(f"Port {port} is still in use after shutdown attempt.")

    print(f"Stopped previous gateway on port {port}.")
