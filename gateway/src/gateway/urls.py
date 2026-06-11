"""Gateway listen URL helpers."""

from __future__ import annotations

import socket
import sys
from pathlib import Path

from gateway.config import GatewayConfig
from gateway.frontend_static import format_frontend_build_problem, frontend_asset_refs, validate_frontend_build


def static_dir() -> Path | None:
    repo_root = Path(__file__).resolve().parents[3]
    candidates = [
        repo_root / "web" / "dist",
        Path.cwd() / "web" / "dist",
        repo_root / "frontend" / "dist",
        Path.cwd() / "frontend" / "dist",
    ]
    for candidate in candidates:
        if (candidate / "index.html").exists():
            return candidate
    return None


def listen_hosts(bind_host: str) -> list[str]:
    if bind_host in ("0.0.0.0", "::", "[::]"):
        hosts = ["127.0.0.1"]
        try:
            hostname = socket.gethostname()
            if hostname and hostname not in hosts:
                hosts.append(hostname)
        except OSError:
            pass
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                ip = sock.getsockname()[0]
                if ip not in hosts:
                    hosts.append(ip)
        except OSError:
            pass
        return hosts
    return [bind_host]


def gateway_base_urls(config: GatewayConfig) -> list[str]:
    port = config.server.port
    hosts = listen_hosts(config.server.host)
    advertised = config.node.descriptive_info.get("host")
    if isinstance(advertised, str):
        name = advertised.strip()
        if name and name not in hosts:
            hosts.append(name)
    return [f"http://{host}:{port}" for host in hosts]


def print_startup_banner(config: GatewayConfig) -> None:
    urls = gateway_base_urls(config)
    primary = urls[0]
    static_root = static_dir()
    web_built = static_root is not None

    print()
    print("Agentnet node gateway")
    print(f"  API (JSON): {primary}/api/status")
    if len(urls) > 1:
        print("  Remote URLs:")
        for url in urls[1:]:
            print(f"    {url}/")
    if web_built and static_root is not None:
        ok, missing = validate_frontend_build(static_root)
        print(f"  Web UI:     {primary}/")
        if len(urls) > 1:
            print(f"              (remote: {urls[-1]}/)")
        if not ok:
            print()
            print(format_frontend_build_problem(static_root, missing), file=sys.stderr)
            print(
                "  The page may look blank (CSS only) until the frontend is rebuilt.",
                file=sys.stderr,
            )
            print(file=sys.stderr)
    else:
        print("  Web UI:     not built — run: cd web && npm run build")
    print()
