"""Gateway entrypoint."""

from __future__ import annotations

import argparse

import structlog
import uvicorn

from gateway.app import create_app
from gateway.config import load_config, resolve_config_path


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

    uvicorn.run(
        app,
        host=config.server.host,
        port=config.server.port,
        log_level=config.logging.level.lower(),
    )


if __name__ == "__main__":
    main()
