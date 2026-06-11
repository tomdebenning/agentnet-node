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
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume existing conversation instead of clearing history",
    )
    args = parser.parse_args()

    try:
        asyncio.run(
            run_agent(Path(args.agent_dir), resolve_gateway_url(args.gateway_url), resume=args.resume)
        )
    except SystemExit as exc:
        raise SystemExit(exc.code) from None


if __name__ == "__main__":
    main()
