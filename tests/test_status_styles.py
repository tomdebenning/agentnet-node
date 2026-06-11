"""TUI status styling tests."""

from __future__ import annotations

from tui.status_styles import badge_class_for_state, format_spawnable_badge, format_state_badge


def test_badge_class_running_is_green() -> None:
    assert badge_class_for_state("running") == "state-ready"


def test_badge_class_stopped_is_amber() -> None:
    assert badge_class_for_state("stopped") == "state-review"


def test_badge_class_error_is_red() -> None:
    assert badge_class_for_state("error") == "state-error"


def test_badge_class_busy_is_yellow() -> None:
    assert badge_class_for_state("interactive_busy") == "state-attention"


def test_format_state_badge_includes_markup() -> None:
    text = format_state_badge("running")
    assert "state-ready" in text
    assert "running" in text


def test_format_spawnable_badge() -> None:
    assert "Spawnable" in format_spawnable_badge(True)
    assert "Needs review" in format_spawnable_badge(False)
