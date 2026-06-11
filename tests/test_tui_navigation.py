"""TUI panel navigation and recovery from a lost MainScreen."""

from __future__ import annotations

import asyncio

from tui.app import NodeTuiApp
from tui.fleet_screens import MainScreen


async def _run_navigation_scenario() -> None:
    app = NodeTuiApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, MainScreen)
        assert len(app.screen.query_one("#fleet-list").children) >= 1

        await pilot.press("b")
        await pilot.pause()
        assert app.screen.query_one("#main-switcher").current == "bullpen"
        assert len(app.screen.query_one("#definition-list").children) >= 1

        await pilot.press("f")
        await pilot.pause()
        assert app.screen.query_one("#main-switcher").current == "running"

        # Simulate the old bug that popped MainScreen off the stack.
        app.pop_screen()
        assert not isinstance(app.screen, MainScreen)

        app.action_show_running()
        await pilot.pause()
        assert isinstance(app.screen, MainScreen)
        assert app.screen.query_one("#main-switcher").current == "running"


def test_tui_panel_navigation_and_recovery() -> None:
    asyncio.run(_run_navigation_scenario())
