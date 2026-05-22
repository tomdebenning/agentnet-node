"""Slim agent entrypoint."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from node_agent.agent_runner import resolve_gateway_url, run_agent


def main() -> None:
    parser = argparse.ArgumentParser(description="Agentnet slim agent")
    parser.add_argument("--agent-dir", type=str, required=True)
    parser.add_argument("--gateway-url", type=str, default=None)
    args = parser.parse_args()

    asyncio.run(run_agent(Path(args.agent_dir), resolve_gateway_url(args.gateway_url)))


if __name__ == "__main__":
    main()
