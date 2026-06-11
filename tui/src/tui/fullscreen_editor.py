"""Full-screen markdown editor for persona/skills."""

from __future__ import annotations

from typing import Literal

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static, TextArea

from tui.status_styles import format_review_badge

EditorMode = Literal["review", "template", "spawn", "instance"]
EditorAction = str  # close | save_template | save_template_close | save_instance | save_instance_close | mark_reviewed


class FullScreenEditorScreen(Screen):
    """Dismiss with (content, action)."""

    BINDINGS = [("escape", "close", "Cancel")]

    def __init__(
        self,
        title: str,
        filename: str,
        content: str,
        *,
        mode: EditorMode = "template",
        has_template: bool = False,
        reviewed: bool = False,
        subtitle: str = "",
        show_review_badge: bool = False,
        show_revert: bool = False,
    ) -> None:
        super().__init__()
        self._title = title
        self._filename = filename
        self._content = content
        self._mode = mode
        self._has_template = has_template
        self._reviewed = reviewed
        self._subtitle = subtitle or self._default_subtitle()
        self._show_review_badge = show_review_badge
        self._show_revert = show_revert

    def _default_subtitle(self) -> str:
        if self._mode == "instance":
            return "Save to this instance only, or update the definition for future spawns."
        if self._mode == "spawn":
            return (
                "Cancel keeps edits as a one-time override for this spawn. "
                "Save to definition updates future spawns."
            )
        if self._mode == "review":
            return "Review the file, then mark reviewed or cancel."
        return "Save changes to the definition."

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="editor-header")
        yield TextArea(self._content, id="editor-body", language="markdown")
        with Horizontal(id="editor-footer"):
            yield Static("", id="review-badge")
            with Vertical(id="editor-actions"):
                yield Button("← Cancel (Esc)", id="close-btn")
                if self._mode == "review":
                    yield Button("✓ Mark reviewed & close", id="review-btn", variant="primary")
                if self._mode in {"template", "spawn"}:
                    yield Button("💾 Save to definition", id="save-template-btn", variant="primary")
                    yield Button("💾 Save to definition & close", id="save-template-close-btn")
                if self._mode == "template":
                    yield Button("✓ Mark reviewed & close", id="review-btn")
                if self._show_revert:
                    yield Button("↩ Revert to definition", id="revert-btn")
                if self._mode == "instance":
                    yield Button("💾 Save to this instance", id="save-instance-btn", variant="primary")
                    yield Button("💾 Save to this instance & close", id="save-instance-close-btn")
                    if self._has_template:
                        yield Button(
                            "💾 Save to definition (future spawns)",
                            id="save-template-btn",
                        )
                        yield Button(
                            "💾 Save to definition & close",
                            id="save-template-close-btn",
                        )
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_header()

    def _refresh_header(self) -> None:
        self.query_one("#editor-header", Static).update(
            f"[bold]{self._title}[/]\n{self._subtitle}\n[state-info]{self._filename}[/]"
        )
        badge = self.query_one("#review-badge", Static)
        if self._show_review_badge:
            badge.update(format_review_badge(self._reviewed))
        else:
            badge.update("")

    def _content_value(self) -> str:
        return self.query_one("#editor-body", TextArea).text

    def _finish(self, action: EditorAction) -> None:
        self.dismiss((self._content_value(), action))

    def action_close(self) -> None:
        self._finish("close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "close-btn":
            self._finish("close")
        elif button_id == "save-template-btn":
            self._finish("save_template")
        elif button_id == "save-template-close-btn":
            self._finish("save_template_close")
        elif button_id == "save-instance-btn":
            self._finish("save_instance")
        elif button_id == "save-instance-close-btn":
            self._finish("save_instance_close")
        elif button_id == "review-btn":
            self._finish("mark_reviewed")
        elif button_id == "revert-btn":
            self._finish("revert")
