"""Helpers for repopulating Textual ListView widgets safely."""

from __future__ import annotations

from textual.widgets import ListView


def clear_list_view(list_view: ListView) -> None:
    """Remove all list items so IDs can be reused on the next refresh."""
    list_view.remove_children()
