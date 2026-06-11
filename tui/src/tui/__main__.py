"""TUI entrypoint."""

from __future__ import annotations

import argparse

from tui.app import NodeTuiApp


def main() -> None:
    parser = argparse.ArgumentParser(description="Agentnet node TUI")
    parser.add_argument("--api-url", default="http://127.0.0.1:8080")
    args = parser.parse_args()
    NodeTuiApp(api_url=args.api_url).run()


if __name__ == "__main__":
    main()
