"""Gateway entrypoint."""

from __future__ import annotations

import argparse
import sys

import structlog
import uvicorn

from gateway.app import create_app
from gateway.config import load_config, resolve_config_path
from gateway.port_conflict import PortInUseError, ensure_port_available
from gateway.urls import print_startup_banner


def main() -> None:
    parser = argparse.ArgumentParser(description="Agentnet node gateway")
    parser.add_argument("--config", type=str, default=None, help="Path to config.yaml")
    args = parser.parse_args()

    config_path = resolve_config_path(args.config)
    config = load_config(config_path)
    app = create_app(config)

    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(),
        ]
    )

    print_startup_banner(config)

    try:
        ensure_port_available(config.server.host, config.server.port)
    except PortInUseError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    uvicorn.run(
        app,
        host=config.server.host,
        port=config.server.port,
        log_level=config.logging.level.lower(),
    )


if __name__ == "__main__":
    main()
