"""Fleet, template, and interactive TUI screens."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Checkbox, ContentSwitcher, Footer, Header, Input, Label, ListItem, ListView, Static, TextArea

from tui.api_client import ApiClient
from tui.connection_status import format_connection_status, format_gateway_unreachable_hint, refresh_connection_panel
from tui.fullscreen_editor import FullScreenEditorScreen
from tui.list_helpers import clear_list_view
from tui.status_styles import (
    format_ready_banner,
    format_review_badge,
    format_spawnable_badge,
    format_state_badge,
)


SAVE_INSTANCE_ACTIONS = frozenset({"save_instance", "save_instance_close"})


class RunningPanel(Vertical):
    """Running agents / fleet instances."""

    def compose(self) -> ComposeResult:
        yield Static("🏃 Running", id="running-title")
        yield Static("Instances (↑↓ · Enter detail · x stop · i chat)", id="fleet-section-label")
        yield ListView(id="fleet-list")
        yield Static("Recent completions", id="completions-title")
        yield ListView(id="completions-list")


class BullPenPanel(Vertical):
    """Agent definition library."""

    def compose(self) -> ComposeResult:
        yield Static("📋 Definitions", id="bullpen-title")
        yield Static(
            "[state-info]Definitions (↑↓ navigate · Enter open · s spawn · c create)[/]",
            id="bullpen-hint",
        )
        yield ListView(id="definition-list")


class MainScreen(Screen):
    """Primary shell: Running fleet view and agent definitions."""

    BINDINGS = [
        ("f", "show_running", "Running"),
        ("b", "show_bullpen", "Definitions"),
        ("n", "new_agent", "New instance"),
        ("c", "create_definition", "Create definition"),
        ("r", "refresh", "Refresh"),
        ("x", "stop_selected_instance", "Stop"),
        ("i", "open_selected_chat", "Chat"),
        ("s", "spawn_selected_definition", "Spawn"),
    ]

    def __init__(self, *, initial_panel: str = "running") -> None:
        super().__init__()
        self._initial_panel = initial_panel
        self._instances: list[dict] = []
        self._definitions: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="connection-status")
        yield Static("", id="main-nav-hint")
        with ContentSwitcher(initial="running", id="main-switcher"):
            yield RunningPanel(id="running")
            yield BullPenPanel(id="bullpen")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(5.0, self.refresh_all)
        if self._initial_panel == "bullpen":
            self.action_show_bullpen()
        else:
            self.action_show_running()
        self.refresh_all()
        self.call_after_refresh(
            self._focus_definition_list if self._initial_panel == "bullpen" else self._focus_fleet_list
        )

    def _update_nav_hint(self) -> None:
        panel = self._switcher.current
        if panel == "running":
            text = (
                "[state-ready]Running[/] — fleet & instances  ·  "
                "[state-info]f[/] Running  ·  [state-info]b[/] Definitions  ·  "
                "[state-info]x[/] stop  ·  [state-info]i[/] chat"
            )
        else:
            text = (
                "[state-ready]Definitions[/] — agent definitions  ·  "
                "[state-info]f[/] Running  ·  [state-info]b[/] Definitions  ·  "
                "[state-info]s[/] spawn"
            )
        self.query_one("#main-nav-hint", Static).update(text)

    def action_show_running(self) -> None:
        self._switcher.current = "running"
        self._update_nav_hint()
        self.call_after_refresh(self._focus_fleet_list)

    def action_show_bullpen(self) -> None:
        self._switcher.current = "bullpen"
        self._update_nav_hint()
        self.call_after_refresh(self._focus_definition_list)

    def _focus_fleet_list(self) -> None:
        try:
            self.query_one("#fleet-list", ListView).focus()
        except Exception:
            pass

    def _focus_definition_list(self) -> None:
        try:
            self.query_one("#definition-list", ListView).focus()
        except Exception:
            pass

    @property
    def _switcher(self) -> ContentSwitcher:
        return self.query_one("#main-switcher", ContentSwitcher)

    def action_new_agent(self) -> None:
        self.app.push_screen(SpawnDefinitionPickerScreen())

    def action_create_definition(self) -> None:
        self.action_show_bullpen()
        self.app.push_screen(CreateDefinitionScreen())

    def action_refresh(self) -> None:
        self.refresh_all()

    def _selected_fleet_index(self) -> int | None:
        if self._switcher.current != "running" or not self._instances:
            return None
        fleet = self.query_one("#fleet-list", ListView)
        index = fleet.index
        if index is None or index < 0 or index >= len(self._instances):
            return None
        return index

    def _selected_definition_index(self) -> int | None:
        if self._switcher.current != "bullpen" or not self._definitions:
            return None
        list_view = self.query_one("#definition-list", ListView)
        index = list_view.index
        if index is None or index < 0 or index >= len(self._definitions):
            return None
        return index

    def action_stop_selected_instance(self) -> None:
        index = self._selected_fleet_index()
        if index is None:
            self.notify("Select an instance in Running first", severity="warning")
            return
        instance_id = self._instances[index]["instance_id"]
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            client.stop_instance(instance_id)
            self.notify(f"Stopped {instance_id}")
            self.refresh_all()
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def action_open_selected_chat(self) -> None:
        index = self._selected_fleet_index()
        if index is None:
            self.notify("Select an instance in Running first", severity="warning")
            return
        item = self._instances[index]
        if item.get("mode") != "interactive":
            self.notify("That instance is not interactive", severity="warning")
            return
        self.app.push_screen(InteractiveScreen(item["instance_id"]))

    def action_spawn_selected_definition(self) -> None:
        index = self._selected_definition_index()
        if index is None:
            self.notify("Select a definition first", severity="warning")
            return
        item = self._definitions[index]
        if not item.get("spawnable"):
            self.notify("Review persona and skills before spawning", severity="warning")
            return
        self.app.push_screen(SpawnInstanceScreen(item["definition_id"]))

    def refresh_all(self) -> None:
        info = refresh_connection_panel(self.app, self)
        self._refresh_running(info)
        self._refresh_bullpen(info)

    def _refresh_running(self, info: dict | None = None) -> None:
        if info is None:
            info = refresh_connection_panel(self.app, self)
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        fleet = self.query_one("#fleet-list", ListView)
        completions = self.query_one("#completions-list", ListView)
        clear_list_view(fleet)
        clear_list_view(completions)
        self._instances = []

        if not info.get("gateway_connected"):
            fleet.append(ListItem(Label(format_gateway_unreachable_hint(info))))
            completions.append(ListItem(Label("[state-info](unavailable — gateway down)[/]")))
            return

        try:
            instances = client.list_instances()
        except Exception as exc:
            self.notify(f"Fleet load failed: {exc}", severity="error")
            fleet.append(ListItem(Label(f"[state-error]Failed to load instances[/]\n[state-info]{exc}[/]")))
            instances = []

        if not instances:
            fleet.append(
                ListItem(Label("[state-info](no instances — b definitions · n new instance)[/]"))
            )
        else:
            self._instances = instances
            for item in instances:
                state = item.get("instance_status") or item.get("process_state")
                definition = item.get("definition_id") or "—"
                mode = item.get("mode") or "?"
                label = (
                    f"{item['instance_id']}  "
                    f"[state-info]{definition} · {mode}[/] "
                    f"{format_state_badge(state)}"
                )
                fleet.append(ListItem(Label(label)))

        try:
            events = client.recent_completions()
        except Exception:
            events = []
        if not events:
            completions.append(ListItem(Label("[state-info](none yet)[/]")))
        for event in events:
            badge = "[state-ready]✅ ok[/]" if event.get("success") else "[state-error]🔴 fail[/]"
            label = f"{badge}  {event['instance_id']}  {event.get('completed_at', '')[:19]}"
            completions.append(ListItem(Label(label)))

    def _refresh_bullpen(self, info: dict | None = None) -> None:
        if info is None:
            info = refresh_connection_panel(self.app, self)
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        list_view = self.query_one("#definition-list", ListView)
        clear_list_view(list_view)
        self._definitions = []

        if not info.get("gateway_connected"):
            list_view.append(ListItem(Label(format_gateway_unreachable_hint(info))))
            return

        try:
            templates = client.list_definitions()
        except Exception as exc:
            list_view.append(
                ListItem(Label(f"[state-error]Failed to load definitions[/]\n[state-info]{exc}[/]"))
            )
            self.notify(str(exc), severity="error")
            return

        if not templates:
            list_view.append(ListItem(Label("[state-info](no definitions — press c to create)[/]")))
            return

        self._definitions = templates
        for item in templates:
            badge = format_spawnable_badge(bool(item.get("spawnable")))
            spawn_hint = "  [state-info]· s spawn[/]" if item.get("spawnable") else ""
            name = item.get("persona_name")
            name_hint = f"  [state-info]{name}[/]" if name and name != item["definition_id"] else ""
            list_view.append(
                ListItem(Label(f"{item['definition_id']}{name_hint}  {badge}{spawn_hint}"))
            )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        list_id = event.list_view.id
        if list_id == "fleet-list":
            if not self._instances:
                return
            index = event.index
            if index < 0 or index >= len(self._instances):
                return
            instance_id = self._instances[index]["instance_id"]
            self.app.push_screen(InstanceDetailScreen(instance_id))
            return

        if list_id == "definition-list":
            if not self._definitions:
                return
            index = event.index
            if index < 0 or index >= len(self._definitions):
                return
            definition_id = self._definitions[index]["definition_id"]
            self.app.push_screen(DefinitionDetailScreen(definition_id))


# Backward-compatible aliases
FleetScreen = MainScreen
TemplateListScreen = MainScreen


class CreateDefinitionScreen(Screen):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self) -> None:
        super().__init__()
        from shared.markdown_io import default_persona_markdown, default_skills_markdown

        self._persona_md = default_persona_markdown("Agent", "helpful assistant")
        self._skills_md = default_skills_markdown()
        self._uses_memory = True
        self._persona_reviewed = False
        self._skills_reviewed = False

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="create-definition-body"):
            yield Static("➕ Create agent definition", id="title")
            yield Static("", id="ready-banner")
            yield Label("Definition ID")
            yield Input(id="definition-id")
            yield Label("Persona name")
            yield Input(id="persona-name", value="Agent")
            yield Label("Persona role")
            yield Input(id="persona-role", value="helpful assistant")
            yield Button("Apply to persona editor", id="apply-persona-btn")
            yield Static("Persona (persona.md)", classes="review-label")
            with VerticalScroll(classes="review-preview-scroll"):
                yield Static("", id="persona-card", classes="review-card pending")
            yield Button("🔍 Review persona full screen", id="open-persona-btn")
            yield Static("Skills (skills.md)", classes="review-label")
            with VerticalScroll(classes="review-preview-scroll"):
                yield Static("", id="skills-card", classes="review-card pending")
            yield Button("🔍 Review skills full screen", id="open-skills-btn")
            yield Checkbox("This agent needs persistent memory", id="uses-memory-checkbox", value=True)
        with Horizontal(id="create-definition-footer"):
            yield Button("Create spawnable definition", id="create-btn", variant="primary")
            yield Button("Cancel", id="cancel-btn")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_review_ui()

    def _refresh_review_ui(self) -> None:
        ready = self._persona_reviewed and self._skills_reviewed
        banner = self.query_one("#ready-banner", Static)
        banner.update(
            format_ready_banner(
                persona_reviewed=self._persona_reviewed,
                skills_reviewed=self._skills_reviewed,
            )
        )
        banner.remove_class("ready", "pending")
        banner.add_class("ready" if ready else "pending")

        persona_card = self.query_one("#persona-card", Static)
        persona_card.update(
            f"{format_review_badge(self._persona_reviewed)}\n\n{self._persona_md or '(empty)'}"
        )
        persona_card.remove_class("done", "pending")
        persona_card.add_class("done" if self._persona_reviewed else "pending")

        skills_card = self.query_one("#skills-card", Static)
        skills_card.update(
            f"{format_review_badge(self._skills_reviewed)}\n\n{self._skills_md or '(empty)'}"
        )
        skills_card.remove_class("done", "pending")
        skills_card.add_class("done" if self._skills_reviewed else "pending")

        create_btn = self.query_one("#create-btn", Button)
        create_btn.disabled = not ready
        create_btn.label = "✅ Create spawnable definition" if ready else "🟠 Review persona & skills first"

    def _apply_persona_defaults(self) -> None:
        from shared.markdown_io import default_persona_markdown

        name = self.query_one("#persona-name", Input).value.strip() or "Agent"
        role = self.query_one("#persona-role", Input).value.strip() or "helpful assistant"
        self._persona_md = default_persona_markdown(name, role)
        self._persona_reviewed = False
        self._refresh_review_ui()
        self.notify("Applied persona name/role to editor")

    def _open_persona_editor(self) -> None:
        self.app.push_screen(
            FullScreenEditorScreen(
                "Persona (persona.md)",
                "persona.md",
                self._persona_md,
                mode="review",
                reviewed=self._persona_reviewed,
                subtitle="Review who this agent is before creating the definition.",
                show_review_badge=True,
            ),
            self._on_persona_editor_done,
        )

    def _open_skills_editor(self) -> None:
        self.app.push_screen(
            FullScreenEditorScreen(
                "Skills (skills.md)",
                "skills.md",
                self._skills_md,
                mode="review",
                reviewed=self._skills_reviewed,
                subtitle="Review what this agent can do before creating the definition.",
                show_review_badge=True,
            ),
            self._on_skills_editor_done,
        )

    def _on_persona_editor_done(self, result: tuple[str, str] | None) -> None:
        if result is None:
            return
        content, action = result
        self._persona_md = content
        if action != "mark_reviewed":
            self._persona_reviewed = False
        else:
            self._persona_reviewed = True
        self._refresh_review_ui()

    def _on_skills_editor_done(self, result: tuple[str, str] | None) -> None:
        if result is None:
            return
        content, action = result
        self._skills_md = content
        if action != "mark_reviewed":
            self._skills_reviewed = False
        else:
            self._skills_reviewed = True
        self._refresh_review_ui()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.action_back()
            return
        if event.button.id == "apply-persona-btn":
            self._apply_persona_defaults()
            return
        if event.button.id == "open-persona-btn":
            self._open_persona_editor()
            return
        if event.button.id == "open-skills-btn":
            self._open_skills_editor()
            return
        if event.button.id != "create-btn":
            return
        if not (self._persona_reviewed and self._skills_reviewed):
            self.notify("Review persona and skills first", severity="warning")
            return
        definition_id = self.query_one("#definition-id", Input).value.strip()
        if not definition_id:
            self.notify("Definition ID required", severity="warning")
            return
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        persona_name = self.query_one("#persona-name", Input).value.strip() or None
        persona_role = self.query_one("#persona-role", Input).value.strip() or "helpful assistant"
        payload = {
            "definition_id": definition_id,
            "persona_name": persona_name,
            "persona_role": persona_role,
            "persona_content": self._persona_md,
            "skills_content": self._skills_md,
            "uses_memory": self.query_one("#uses-memory-checkbox", Checkbox).value,
            "persona_reviewed": True,
            "skills_reviewed": True,
        }
        try:
            client.create_definition(payload)
            self.notify(f"Created definition {definition_id}")
            self.app.pop_screen()
            self.app.push_screen(SpawnInstanceScreen(definition_id))
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def action_back(self) -> None:
        self.app.pop_screen()


class DefinitionDetailScreen(Screen):
    BINDINGS = [("escape", "back", "Back"), ("s", "spawn", "Spawn")]

    def __init__(self, definition_id: str) -> None:
        super().__init__()
        self.definition_id = definition_id
        self._persona_md = ""
        self._skills_md = ""
        self._memory_md = ""
        self._uses_memory = True
        self._persona_reviewed = False
        self._skills_reviewed = False
        self._spawnable = False

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="definition-detail-body"):
            yield Static(f"Definition: {self.definition_id}", id="detail-title")
            yield Static("", id="ready-banner")
            yield Static("Persona (persona.md)", classes="review-label")
            with VerticalScroll(classes="review-preview-scroll"):
                yield Static("", id="persona-card", classes="review-card pending")
            yield Button("📝 Open persona full screen", id="open-persona-btn")
            yield Static("Skills (skills.md)", classes="review-label")
            with VerticalScroll(classes="review-preview-scroll"):
                yield Static("", id="skills-card", classes="review-card pending")
            yield Button("📝 Open skills full screen", id="open-skills-btn")
            yield Checkbox("This agent needs persistent memory", id="uses-memory-checkbox", value=True)
            yield Static("Memory (memory.md)", id="memory-label", classes="review-label")
            with VerticalScroll(classes="review-preview-scroll"):
                yield Static("", id="memory-card", classes="review-card")
            yield Button("📝 Open memory full screen", id="open-memory-btn")
        yield Horizontal(
            Button("🚀 Spawn instance", id="spawn-btn", variant="primary"),
            Button("Delete definition", id="delete-btn", variant="error"),
            Button("Back", id="back-btn"),
            id="definition-detail-footer",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.load_definition()

    def _refresh_review_ui(self) -> None:
        ready = self._spawnable
        banner = self.query_one("#ready-banner", Static)
        banner.update(
            format_ready_banner(
                persona_reviewed=self._persona_reviewed,
                skills_reviewed=self._skills_reviewed,
                spawnable=self._spawnable,
            )
        )
        banner.remove_class("ready", "pending")
        banner.add_class("ready" if ready else "pending")

        persona_card = self.query_one("#persona-card", Static)
        persona_card.update(
            f"{format_review_badge(self._persona_reviewed)}\n\n{self._persona_md or '(empty)'}"
        )
        persona_card.remove_class("done", "pending")
        persona_card.add_class("done" if self._persona_reviewed else "pending")

        skills_card = self.query_one("#skills-card", Static)
        skills_card.update(
            f"{format_review_badge(self._skills_reviewed)}\n\n{self._skills_md or '(empty)'}"
        )
        skills_card.remove_class("done", "pending")
        skills_card.add_class("done" if self._skills_reviewed else "pending")

        memory_label = self.query_one("#memory-label", Static)
        memory_card = self.query_one("#memory-card", Static)
        memory_btn = self.query_one("#open-memory-btn", Button)
        uses_memory_checkbox = self.query_one("#uses-memory-checkbox", Checkbox)
        uses_memory_checkbox.value = self._uses_memory
        show_memory = self._uses_memory
        memory_label.display = show_memory
        memory_card.display = show_memory
        memory_btn.display = show_memory
        if show_memory:
            memory_card.update(self._memory_md or "(empty)")

        spawn_btn = self.query_one("#spawn-btn", Button)
        spawn_btn.disabled = not self._spawnable
        spawn_btn.label = "🚀 Spawn instance" if self._spawnable else "🟠 Spawn locked"

    def load_definition(self) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            data = client.get_definition(self.definition_id)
        except Exception as exc:
            self.notify(str(exc), severity="error")
            return
        self._persona_md = data.get("persona_raw", "")
        self._skills_md = data.get("skills_raw", "")
        self._memory_md = data.get("memory_raw", "")
        self._uses_memory = bool(data.get("uses_memory", True))
        self._persona_reviewed = bool(data.get("persona_reviewed"))
        self._skills_reviewed = bool(data.get("skills_reviewed"))
        self._spawnable = bool(data.get("spawnable"))
        self._refresh_review_ui()

    def _open_memory_editor(self) -> None:
        self.app.push_screen(
            FullScreenEditorScreen(
                "Memory (memory.md)",
                "memory.md",
                self._memory_md,
                mode="definition",
                subtitle="Seed long-term context copied to each spawned instance.",
            ),
            self._on_memory_editor_done,
        )

    def _open_persona_editor(self) -> None:
        self.app.push_screen(
            FullScreenEditorScreen(
                "Persona (persona.md)",
                "persona.md",
                self._persona_md,
                mode="definition",
                reviewed=self._persona_reviewed,
                show_review_badge=True,
            ),
            self._on_persona_editor_done,
        )

    def _open_skills_editor(self) -> None:
        self.app.push_screen(
            FullScreenEditorScreen(
                "Skills (skills.md)",
                "skills.md",
                self._skills_md,
                mode="definition",
                reviewed=self._skills_reviewed,
                show_review_badge=True,
            ),
            self._on_skills_editor_done,
        )

    def _apply_review_result(self, result: dict) -> None:
        self._persona_reviewed = bool(result.get("persona_reviewed"))
        self._skills_reviewed = bool(result.get("skills_reviewed"))
        self._spawnable = bool(result.get("spawnable"))
        self._refresh_review_ui()

    def _save_persona(self, mark_reviewed: bool = False) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            data = client.write_definition_persona(
                self.definition_id, self._persona_md, mark_reviewed=mark_reviewed
            )
            self._apply_review_result(data)
            self.notify("💾 Persona saved to definition" + (" and reviewed" if mark_reviewed else ""))
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def _save_skills(self, mark_reviewed: bool = False) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            data = client.write_definition_skills(
                self.definition_id, self._skills_md, mark_reviewed=mark_reviewed
            )
            self._apply_review_result(data)
            self.notify("💾 Skills saved to definition" + (" and reviewed" if mark_reviewed else ""))
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def _save_memory(self) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            data = client.write_definition_memory(self.definition_id, self._memory_md)
            self._memory_md = data.get("memory", {}).get("raw", self._memory_md)
            self.notify("💾 Memory saved to definition")
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def _set_uses_memory(self, uses_memory: bool) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            data = client.set_definition_uses_memory(self.definition_id, uses_memory)
            self._uses_memory = bool(data.get("uses_memory"))
            self._memory_md = data.get("memory_raw", "")
            self._persona_reviewed = bool(data.get("persona_reviewed"))
            self._skills_reviewed = bool(data.get("skills_reviewed"))
            self._spawnable = bool(data.get("spawnable"))
            self._refresh_review_ui()
            if uses_memory:
                self.notify("✅ Memory enabled for this definition")
            else:
                self.notify("Memory disabled for this definition")
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def _on_memory_editor_done(self, result: tuple[str, str] | None) -> None:
        if result is None:
            return
        content, action = result
        self._memory_md = content
        if action == "close":
            return
        if action in ("save_definition", "save_definition_close"):
            self._save_memory()

    def _on_persona_editor_done(self, result: tuple[str, str] | None) -> None:
        if result is None:
            return
        content, action = result
        self._persona_md = content
        if action == "close":
            return
        if action == "mark_reviewed":
            self._save_persona(mark_reviewed=True)
        elif action in ("save_definition", "save_definition_close"):
            self._save_persona(mark_reviewed=False)

    def _on_skills_editor_done(self, result: tuple[str, str] | None) -> None:
        if result is None:
            return
        content, action = result
        self._skills_md = content
        if action == "close":
            return
        if action == "mark_reviewed":
            self._save_skills(mark_reviewed=True)
        elif action in ("save_definition", "save_definition_close"):
            self._save_skills(mark_reviewed=False)

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id != "uses-memory-checkbox":
            return
        if event.value == self._uses_memory:
            return
        self._set_uses_memory(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.action_back()
            return
        if event.button.id == "open-persona-btn":
            self._open_persona_editor()
            return
        if event.button.id == "open-skills-btn":
            self._open_skills_editor()
            return
        if event.button.id == "open-memory-btn":
            self._open_memory_editor()
            return
        if event.button.id == "delete-btn":
            self._delete_definition()
            return
        if event.button.id == "spawn-btn":
            self.action_spawn()

    def action_spawn(self) -> None:
        if not self._spawnable:
            self.notify("Review persona and skills before spawning", severity="warning")
            return
        self.app.push_screen(SpawnInstanceScreen(self.definition_id))

    def _delete_definition(self) -> None:
        from tui.confirm_modal import ConfirmModal

        self.app.push_screen(
            ConfirmModal(f'Delete definition "{self.definition_id}"? This cannot be undone.'),
            self._on_delete_confirmed,
        )

    def _on_delete_confirmed(self, confirmed: bool | None) -> None:
        if not confirmed:
            return
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            client.delete_definition(self.definition_id)
            self.notify(f"Deleted definition {self.definition_id}")
            self.app.pop_screen()
            screen = self.app.screen
            if isinstance(screen, MainScreen):
                screen.refresh_all()
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def action_back(self) -> None:
        self.app.pop_screen()


class SpawnInstanceScreen(Screen):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, definition_id: str) -> None:
        super().__init__()
        self.definition_id = definition_id
        self._definition_persona = ""
        self._definition_skills = ""
        self._persona_md = ""
        self._skills_md = ""
        self._persona_reviewed = False
        self._skills_reviewed = False
        self._spawnable = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(f"Spawn: {self.definition_id}", id="title")
        yield Static("", id="ready-banner")
        yield Horizontal(
            VerticalScroll(
                Static("📄 Definition", id="template-panel-title"),
                Static(
                    "[state-info]Persona and skills from the definition library.[/]",
                    id="template-meta",
                ),
                Static(
                    "Open persona/skills full screen. Save to definition updates future spawns.",
                    id="persona-hint",
                ),
                Static("", id="persona-override-hint"),
                VerticalScroll(
                    Static("", id="persona-card", classes="review-card pending"),
                    classes="review-preview-scroll",
                ),
                Button("📝 Open persona full screen", id="open-persona-btn"),
                Static("", id="skills-override-hint"),
                VerticalScroll(
                    Static("", id="skills-card", classes="review-card pending"),
                    classes="review-preview-scroll",
                ),
                Button("📝 Open skills full screen", id="open-skills-btn"),
                id="template-panel",
            ),
            Vertical(
                Static("🤖 Instance configuration", id="instance-panel-title"),
                Static(
                    "[state-info]Model, puller, and base name are required at spawn.[/]",
                    id="spawn-config-hint",
                ),
                Label("Base name"),
                Input(id="base-name"),
                Label("Target puller"),
                Input(id="target-puller", placeholder="loading defaults…"),
                Label("Model"),
                Input(id="model", placeholder="loading defaults…"),
                Label("Temperature"),
                Input(id="temperature", placeholder="loading defaults…"),
                Label("Context (num_ctx)"),
                Input(id="num-ctx", placeholder="loading defaults…"),
                Label("Mode (autonomous | interactive)"),
                Input(id="mode", value="autonomous"),
                Label("Resume paused run? (yes/no)"),
                Input(id="resume", value="no"),
                Label("Goal"),
                TextArea("", id="goal-body"),
                Horizontal(
                    Button("🚀 Spawn", id="spawn-btn", variant="primary"),
                    Button("Cancel", id="cancel-btn"),
                ),
                id="instance-panel",
            ),
            id="spawn-split",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._apply_spawn_defaults()
        self.load_definition()

    def _apply_spawn_defaults(self) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            defaults = client.spawn_defaults()
        except Exception:
            return
        self.query_one("#target-puller", Input).value = str(defaults.get("target_puller", "puller-01"))
        self.query_one("#model", Input).value = str(defaults.get("model", "llama3.1:8b"))
        self.query_one("#temperature", Input).value = str(defaults.get("temperature", 0.7))
        self.query_one("#num-ctx", Input).value = str(defaults.get("num_ctx", 8192))

    def _refresh_review_ui(self) -> None:
        banner = self.query_one("#ready-banner", Static)
        banner.update(
            format_ready_banner(
                persona_reviewed=self._persona_reviewed,
                skills_reviewed=self._skills_reviewed,
                spawnable=self._spawnable,
            )
        )
        banner.remove_class("ready", "pending")
        banner.add_class("ready" if self._spawnable else "pending")

        persona_card = self.query_one("#persona-card", Static)
        persona_card.update(
            f"Persona  {format_review_badge(self._persona_reviewed)}\n\n{self._persona_md or '(empty)'}"
        )
        persona_card.remove_class("done", "pending")
        persona_card.add_class("done" if self._persona_reviewed else "pending")

        skills_card = self.query_one("#skills-card", Static)
        skills_card.update(
            f"Skills  {format_review_badge(self._skills_reviewed)}\n\n{self._skills_md or '(empty)'}"
        )
        skills_card.remove_class("done", "pending")
        skills_card.add_class("done" if self._skills_reviewed else "pending")

        spawn_btn = self.query_one("#spawn-btn", Button)
        spawn_btn.disabled = not self._spawnable
        spawn_btn.label = "🚀 Spawn" if self._spawnable else "🟠 Review definition first"

        mode_input = self.query_one("#mode", Input)
        resume_input = self.query_one("#resume", Input)
        base_input = self.query_one("#base-name", Input)
        puller_input = self.query_one("#target-puller", Input)
        model_input = self.query_one("#model", Input)
        task_body = self.query_one("#goal-body", TextArea)
        for widget in (mode_input, resume_input, base_input, puller_input, model_input, task_body):
            widget.disabled = not self._spawnable

    def load_definition(self) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            data = client.get_definition(self.definition_id)
        except Exception as exc:
            self.notify(str(exc), severity="error")
            return
        self._definition_persona = data.get("persona_raw", "")
        self._definition_skills = data.get("skills_raw", "")
        self._persona_md = self._definition_persona
        self._skills_md = self._definition_skills
        self._persona_reviewed = bool(data.get("persona_reviewed"))
        self._skills_reviewed = bool(data.get("skills_reviewed"))
        self._spawnable = bool(data.get("spawnable"))
        base_default = self.definition_id
        self.query_one("#base-name", Input).value = base_default
        self._update_override_hints()
        self._refresh_review_ui()

    def _update_override_hints(self) -> None:
        persona_hint = self.query_one("#persona-override-hint", Static)
        skills_hint = self.query_one("#skills-override-hint", Static)
        if self._persona_md != self._definition_persona:
            persona_hint.update("🟠 Instance-only persona override (definition unchanged)")
        else:
            persona_hint.update("")
        if self._skills_md != self._definition_skills:
            skills_hint.update("🟠 Instance-only skills override (definition unchanged)")
        else:
            skills_hint.update("")

    def _apply_review_result(self, result: dict) -> None:
        self._persona_reviewed = bool(result.get("persona_reviewed"))
        self._skills_reviewed = bool(result.get("skills_reviewed"))
        self._spawnable = bool(result.get("spawnable"))
        self._refresh_review_ui()

    def _save_persona_to_definition(self, mark_reviewed: bool = False) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            data = client.write_definition_persona(
                self.definition_id, self._persona_md, mark_reviewed=mark_reviewed
            )
            self._definition_persona = self._persona_md
            self._apply_review_result(data)
            self._update_override_hints()
            self.notify("💾 Persona saved to definition" + (" and reviewed" if mark_reviewed else ""))
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def _save_skills_to_definition(self, mark_reviewed: bool = False) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            data = client.write_definition_skills(
                self.definition_id, self._skills_md, mark_reviewed=mark_reviewed
            )
            self._definition_skills = self._skills_md
            self._apply_review_result(data)
            self._update_override_hints()
            self.notify("💾 Skills saved to definition" + (" and reviewed" if mark_reviewed else ""))
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def _open_persona_editor(self) -> None:
        self.app.push_screen(
            FullScreenEditorScreen(
                "Persona (persona.md)",
                "persona.md",
                self._persona_md,
                mode="spawn",
                reviewed=self._persona_reviewed,
                show_review_badge=True,
                show_revert=True,
            ),
            self._on_persona_editor_done,
        )

    def _open_skills_editor(self) -> None:
        self.app.push_screen(
            FullScreenEditorScreen(
                "Skills (skills.md)",
                "skills.md",
                self._skills_md,
                mode="spawn",
                reviewed=self._skills_reviewed,
                show_review_badge=True,
                show_revert=True,
            ),
            self._on_skills_editor_done,
        )

    def _on_persona_editor_done(self, result: tuple[str, str] | None) -> None:
        if result is None:
            return
        content, action = result
        if action == "revert":
            self._persona_md = self._definition_persona
        else:
            self._persona_md = content
        self._update_override_hints()
        if action == "close":
            self._refresh_review_ui()
            return
        if action in ("save_definition", "save_definition_close"):
            self._save_persona_to_definition()
        self._refresh_review_ui()

    def _on_skills_editor_done(self, result: tuple[str, str] | None) -> None:
        if result is None:
            return
        content, action = result
        if action == "revert":
            self._skills_md = self._definition_skills
        else:
            self._skills_md = content
        self._update_override_hints()
        if action == "close":
            self._refresh_review_ui()
            return
        if action in ("save_definition", "save_definition_close"):
            self._save_skills_to_definition()
        self._refresh_review_ui()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.action_back()
            return
        if event.button.id == "open-persona-btn":
            self._open_persona_editor()
            return
        if event.button.id == "open-skills-btn":
            self._open_skills_editor()
            return
        if event.button.id != "spawn-btn":
            return
        if not self._spawnable:
            self.notify("Review persona and skills before spawning", severity="warning")
            return
        mode = self.query_one("#mode", Input).value.strip().lower()
        if mode not in ("autonomous", "interactive"):
            self.notify("Mode must be autonomous or interactive", severity="warning")
            return
        base_name = self.query_one("#base-name", Input).value.strip()
        if not base_name:
            self.notify("Base name required", severity="warning")
            return
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            temp = float(self.query_one("#temperature", Input).value.strip())
        except ValueError:
            self.notify("Temperature must be a number", severity="warning")
            return
        try:
            num_ctx = int(self.query_one("#num-ctx", Input).value.strip())
        except ValueError:
            self.notify("num_ctx must be an integer", severity="warning")
            return
        payload = {
            "mode": mode,
            "base_name": base_name,
            "target_puller": self.query_one("#target-puller", Input).value.strip(),
            "model": self.query_one("#model", Input).value.strip(),
            "temperature": temp,
            "num_ctx": num_ctx,
            "resume": self.query_one("#resume", Input).value.strip().lower() in ("yes", "y", "true", "1"),
            "goal": self.query_one("#goal-body", TextArea).text,
            "auto_start": True,
        }
        if self._persona_md != self._definition_persona:
            payload["persona_content"] = self._persona_md
        if self._skills_md != self._definition_skills:
            payload["skills_content"] = self._skills_md
        try:
            spawned = client.spawn_instance(self.definition_id, payload)
            self.notify(f"Spawned {spawned['instance_id']}")
            self.app.pop_screen()
            if mode == "interactive":
                self.app.push_screen(InteractiveScreen(spawned["instance_id"]))
            else:
                self.app.push_screen(InstanceDetailScreen(spawned["instance_id"]))
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def action_back(self) -> None:
        self.app.pop_screen()


class InstanceDetailScreen(Screen):
    BINDINGS = [
        ("escape", "back", "Back"),
        ("s", "start", "Start"),
        ("x", "stop", "Stop"),
        ("d", "delete", "Delete"),
    ]

    _BROWSE_KINDS = frozenset({"conversations", "workspace", "databases"})
    _EDIT_KINDS = frozenset({"config", "task", "memory"})

    def __init__(self, instance_id: str) -> None:
        super().__init__()
        self.instance_id = instance_id
        self._definition_id: str | None = None
        self._mode: str | None = None
        self._process_state = "stopped"
        self._persona_md = ""
        self._skills_md = ""
        self._saved_persona_md = ""
        self._saved_skills_md = ""
        self._current_kind = "config"
        self._workspace_path = "."
        self._browse_items: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="instance-detail-body"):
            yield Static(f"Instance: {self.instance_id}", id="detail-title")
            yield Static("", id="instance-meta")
            yield Static("", id="run-summary")
            yield Static("Persona (persona.md)", classes="review-label")
            with VerticalScroll(classes="review-preview-scroll"):
                yield Static("", id="persona-card", classes="review-card pending")
            yield Button("📝 Open persona full screen", id="open-persona-btn")
            yield Static("Skills (skills.md)", classes="review-label")
            with VerticalScroll(classes="review-preview-scroll"):
                yield Static("", id="skills-card", classes="review-card pending")
            yield Button("📝 Open skills full screen", id="open-skills-btn")
            yield Static("Files", id="files-label")
            yield Horizontal(
                Button("Config", id="tab-config"),
                Button("Task", id="tab-task"),
                Button("Memory", id="tab-memory"),
            )
            yield Static("Output", id="output-label")
            yield Horizontal(
                Button("Conversations", id="tab-conversations"),
                Button("Workspace", id="tab-workspace"),
                Button("Databases", id="tab-databases"),
            )
            yield Static("", id="browse-hint")
            yield ListView(id="browse-list")
            yield TextArea("", id="editor", language="markdown")
        yield Horizontal(
            Button("Save", id="save-btn", variant="primary"),
            Button("Start", id="start-btn"),
            Button("Stop", id="stop-btn"),
            Button("Open chat", id="chat-btn"),
            Button("Delete", id="delete-btn", variant="error"),
            Button("Back", id="back-btn"),
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#browse-list").display = False
        self.query_one("#browse-hint").display = False
        self.load_instance()
        self.load_file("config")

    def load_instance(self) -> None:
        from shared.markdown_io import default_skills_markdown

        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            info = client.get_instance(self.instance_id)
        except Exception as exc:
            self.notify(str(exc), severity="error")
            return
        self._definition_id = info.get("definition_id")
        self._mode = info.get("mode")
        self._process_state = info.get("process_state", "stopped")
        self._persona_md = client.read_file_raw(self.instance_id, "persona")
        self._skills_md = client.read_file_raw(
            self.instance_id, "skills", default=default_skills_markdown()
        )
        self._saved_persona_md = self._persona_md
        self._saved_skills_md = self._skills_md
        state = info.get("instance_status") or info.get("process_state")
        template_line = f"definition: {self._definition_id}" if self._definition_id else "no definition"
        pid = info.get("pid") or "-"
        self.query_one("#instance-meta", Static).update(
            f"{format_state_badge(state)}  ·  PID: {pid}  ·  {template_line}  ·  mode: {info.get('mode', '?')}"
        )
        self._refresh_run_summary(info.get("current_run"))
        self._refresh_cards()
        self.query_one("#chat-btn", Button).display = self._mode == "interactive"

    def _refresh_run_summary(self, current_run: dict | None) -> None:
        panel = self.query_one("#run-summary", Static)
        if not current_run:
            panel.update("[state-info]Run: (none yet)[/]")
            return
        run = current_run.get("run", {})
        plan = current_run.get("plan", {})
        artifacts = current_run.get("artifacts", [])
        products = (current_run.get("products") or {}).get("product_artifact_ids", [])
        steps = plan.get("steps", [])
        step_lines = "\n".join(
            f"  · {step.get('title')} ({step.get('status')})" for step in steps
        ) or "  (no steps yet)"
        artifact_lines = "\n".join(
            f"  · {item.get('artifact_id')}: {item.get('summary')}" for item in artifacts
        ) or "  (none yet)"
        product_lines = ", ".join(products) if products else "(none yet)"
        panel.update(
            f"[state-ready]Goal[/]: {run.get('goal') or '(not set)'}\n"
            f"[state-info]Status[/]: {run.get('status')}  ·  run: {current_run.get('conversation_id')}\n"
            f"[state-ready]Plan[/]\n{step_lines}\n"
            f"[state-ready]Artifacts[/]\n{artifact_lines}\n"
            f"[state-ready]Products[/]: {product_lines}"
        )

    def _refresh_cards(self) -> None:
        persona_dirty = self._persona_md != self._saved_persona_md
        skills_dirty = self._skills_md != self._saved_skills_md
        persona_card = self.query_one("#persona-card", Static)
        persona_card.update(
            f"{'[state-attention]🟡 Unsaved[/]' if persona_dirty else '[state-ready]✅ Saved[/]'}\n\n"
            f"{self._persona_md or '(empty)'}"
        )
        skills_card = self.query_one("#skills-card", Static)
        skills_card.update(
            f"{'[state-attention]🟡 Unsaved[/]' if skills_dirty else '[state-ready]✅ Saved[/]'}\n\n"
            f"{self._skills_md or '(empty)'}"
        )

    def _is_running(self) -> bool:
        return self._process_state == "running"

    def _is_browse_mode(self) -> bool:
        return self._current_kind in self._BROWSE_KINDS

    def _set_browse_ui(self, *, browsing: bool) -> None:
        self.query_one("#browse-list").display = browsing
        self.query_one("#browse-hint").display = browsing
        self.query_one("#save-btn").display = not browsing
        editor = self.query_one("#editor", TextArea)
        editor.disabled = browsing

    def load_file(self, kind: str) -> None:
        self._current_kind = kind
        if kind in self._BROWSE_KINDS:
            self._set_browse_ui(browsing=True)
            if kind == "conversations":
                self._load_conversations_list()
            elif kind == "workspace":
                self._workspace_path = "."
                self._load_workspace_list()
            else:
                self._load_databases_list()
            return

        self._set_browse_ui(browsing=False)
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            content = client.read_file_raw(self.instance_id, kind)
            self.query_one("#editor", TextArea).text = content
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def _load_conversations_list(self) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        list_view = self.query_one("#browse-list", ListView)
        clear_list_view(list_view)
        self._browse_items = []
        self.query_one("#browse-hint", Static).update("Select a conversation")
        self.query_one("#editor", TextArea).text = ""
        try:
            conversations = client.list_conversations(self.instance_id)
        except Exception as exc:
            self.notify(str(exc), severity="error")
            return
        if not conversations:
            list_view.append(ListItem(Label("(no conversations yet)")))
            return
        for item in conversations:
            label = (
                f"{item['conversation_id']}  "
                f"({item['message_count']} msgs, {item.get('status', '?')})"
            )
            self._browse_items.append({"kind": "conv", "id": item["conversation_id"]})
            list_view.append(ListItem(Label(label)))

    def _load_workspace_list(self) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        list_view = self.query_one("#browse-list", ListView)
        clear_list_view(list_view)
        self._browse_items = []
        self.query_one("#browse-hint", Static).update(f"Workspace: {self._workspace_path}")
        self.query_one("#editor", TextArea).text = ""
        if self._workspace_path not in (".", ""):
            self._browse_items.append({"kind": "ws", "path": ".."})
            list_view.append(ListItem(Label(".. (parent)")))
        try:
            payload = client.list_workspace(self.instance_id, self._workspace_path)
        except Exception as exc:
            self.notify(str(exc), severity="error")
            return
        for entry in payload["entries"]:
            suffix = "/" if entry["is_dir"] else ""
            size = "" if entry["is_dir"] else f"  {entry.get('size', 0)}b"
            self._browse_items.append({"kind": "ws", "path": entry["path"]})
            list_view.append(ListItem(Label(f"{entry['name']}{suffix}{size}")))

    def _load_databases_list(self) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        list_view = self.query_one("#browse-list", ListView)
        clear_list_view(list_view)
        self._browse_items = []
        self.query_one("#browse-hint", Static).update("Select a database")
        self.query_one("#editor", TextArea).text = ""
        try:
            databases = client.list_databases(self.instance_id)
        except Exception as exc:
            self.notify(str(exc), severity="error")
            return
        if not databases:
            list_view.append(ListItem(Label("(no databases yet)")))
            return
        for name in databases:
            self._browse_items.append({"kind": "db", "name": name})
            list_view.append(ListItem(Label(name)))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if not self._is_browse_mode() or not self._browse_items:
            return
        index = event.index
        if index < 0 or index >= len(self._browse_items):
            return
        selected = self._browse_items[index]
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        editor = self.query_one("#editor", TextArea)

        if selected["kind"] == "conv":
            try:
                data = client.get_conversation(self.instance_id, selected["id"])
                editor.text = data["formatted"]
            except Exception as exc:
                self.notify(str(exc), severity="error")
            return

        if selected["kind"] == "ws":
            path = selected["path"]
            if path == "..":
                parent = Path(self._workspace_path)
                if parent.as_posix() in (".", ""):
                    self._workspace_path = "."
                else:
                    self._workspace_path = parent.parent.as_posix() or "."
                self._load_workspace_list()
                return
            try:
                client.list_workspace(self.instance_id, path)
                self._workspace_path = path
                self._load_workspace_list()
            except Exception:
                try:
                    file_data = client.read_workspace_file(self.instance_id, path)
                    editor.text = file_data["content"]
                except Exception as exc:
                    self.notify(str(exc), severity="error")
            return

        if selected["kind"] == "db":
            try:
                info = client.get_database(self.instance_id, selected["name"])
                editor.text = self._format_database(info)
            except Exception as exc:
                self.notify(str(exc), severity="error")

    @staticmethod
    def _format_database(info: dict) -> str:
        lines = [f"Database: {info['db_name']}", f"Path: {info.get('path', '')}", ""]
        for table in info.get("tables", []):
            lines.append(f"## Table {table['name']} ({table['row_count']} rows)")
            lines.append("Columns: " + ", ".join(table.get("columns", [])))
            lines.append("")
            for row in table.get("preview_rows", []):
                lines.append(" | ".join(str(cell) for cell in row))
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def _save_persona_instance(self) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            client.write_file(self.instance_id, "persona", self._persona_md)
            self._saved_persona_md = self._persona_md
            self._refresh_cards()
            self.notify("💾 Persona saved to instance")
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def _save_skills_instance(self) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            client.write_file(self.instance_id, "skills", self._skills_md)
            self._saved_skills_md = self._skills_md
            self._refresh_cards()
            self.notify("💾 Skills saved to instance")
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def _save_persona_definition(self) -> None:
        if not self._definition_id:
            return
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            client.write_definition_persona(self._definition_id, self._persona_md)
            self.notify(f"💾 Persona saved to definition {self._definition_id}")
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def _save_skills_definition(self) -> None:
        if not self._definition_id:
            return
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            client.write_definition_skills(self._definition_id, self._skills_md)
            self.notify(f"💾 Skills saved to definition {self._definition_id}")
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def _open_persona_editor(self) -> None:
        self.app.push_screen(
            FullScreenEditorScreen(
                "Persona (persona.md)",
                "persona.md",
                self._persona_md,
                mode="instance",
                has_definition=bool(self._definition_id),
            ),
            self._on_persona_editor_done,
        )

    def _open_skills_editor(self) -> None:
        self.app.push_screen(
            FullScreenEditorScreen(
                "Skills (skills.md)",
                "skills.md",
                self._skills_md,
                mode="instance",
                has_definition=bool(self._definition_id),
            ),
            self._on_skills_editor_done,
        )

    def _on_persona_editor_done(self, result: tuple[str, str] | None) -> None:
        if result is None:
            return
        content, action = result
        self._persona_md = content
        if action == "close":
            self._refresh_cards()
            return
        if action in SAVE_INSTANCE_ACTIONS:
            self._save_persona_instance()
        elif action in ("save_definition", "save_definition_close"):
            self._save_persona_definition()
        self._refresh_cards()

    def _on_skills_editor_done(self, result: tuple[str, str] | None) -> None:
        if result is None:
            return
        content, action = result
        self._skills_md = content
        if action == "close":
            self._refresh_cards()
            return
        if action in SAVE_INSTANCE_ACTIONS:
            self._save_skills_instance()
        elif action in ("save_definition", "save_definition_close"):
            self._save_skills_definition()
        self._refresh_cards()

    def save_file(self) -> None:
        if self._current_kind not in self._EDIT_KINDS:
            return
        if self._current_kind == "task" and self._is_running():
            from tui.confirm_modal import ConfirmModal

            self.app.push_screen(
                ConfirmModal(
                    "Agent is running. Stop it so the new task can run on next Start?"
                ),
                self._save_after_stop_confirm,
            )
            return
        self._write_file()

    def _save_after_stop_confirm(self, confirmed: bool | None) -> None:
        if not confirmed:
            self.notify("Save cancelled", severity="warning")
            return
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            client.stop_agent(self.instance_id)
            self.load_instance()
        except Exception as exc:
            self.notify(f"Stop failed: {exc}", severity="error")
            return
        self._write_file()

    def _write_file(self) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        content = self.query_one("#editor", TextArea).text
        try:
            client.write_file(self.instance_id, self._current_kind, content)
            self.notify(f"Saved {self._current_kind}")
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def action_start(self) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            client.start_agent(self.instance_id)
            self.load_instance()
            self.notify("Started")
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def action_stop(self) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            client.stop_instance(self.instance_id)
            self.load_instance()
            self.notify("Stopped")
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def action_delete(self) -> None:
        from tui.confirm_modal import ConfirmModal

        self.app.push_screen(
            ConfirmModal(f'Delete instance "{self.instance_id}"? This cannot be undone.'),
            self._on_delete_confirmed,
        )

    def _on_delete_confirmed(self, confirmed: bool | None) -> None:
        if not confirmed:
            return
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            client.delete_agent(self.instance_id)
            self.notify("Deleted")
            self.app.pop_screen()
            screen = self.app.screen
            if isinstance(screen, MainScreen):
                screen.refresh_all()
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "back-btn":
            self.action_back()
        elif button_id == "open-persona-btn":
            self._open_persona_editor()
        elif button_id == "open-skills-btn":
            self._open_skills_editor()
        elif button_id == "tab-config":
            self.load_file("config")
        elif button_id == "tab-task":
            self.load_file("task")
        elif button_id == "tab-memory":
            self.load_file("memory")
        elif button_id == "tab-conversations":
            self.load_file("conversations")
        elif button_id == "tab-workspace":
            self.load_file("workspace")
        elif button_id == "tab-databases":
            self.load_file("databases")
        elif button_id == "save-btn":
            self.save_file()
        elif button_id == "start-btn":
            self.action_start()
        elif button_id == "stop-btn":
            self.action_stop()
        elif button_id == "chat-btn":
            self.app.push_screen(InteractiveScreen(self.instance_id))
        elif button_id == "delete-btn":
            self.action_delete()

    def action_back(self) -> None:
        self.app.pop_screen()


class SpawnDefinitionPickerScreen(Screen):
    """Pick a definition from the gateway catalog before spawning."""

    BINDINGS = [
        ("escape", "back", "Back"),
        ("s", "spawn_selected", "Spawn"),
        ("v", "view_selected", "View"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._definitions: list[dict] = []
        self._detail: dict | None = None
        self._loading_detail = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("🚀 Spawn instance — choose definition", id="picker-title")
        yield Static(
            "[state-info]↑↓ select · s spawn · v full detail · escape back[/]",
            id="picker-hint",
        )
        with Horizontal(id="spawn-picker-body"):
            with Vertical(id="picker-list-panel"):
                yield Static("Definitions", classes="review-label")
                yield ListView(id="spawn-definition-list")
            with VerticalScroll(id="picker-preview-panel"):
                yield Static("Preview", classes="review-label")
                yield Static("", id="picker-preview")
        yield Horizontal(
            Button("🚀 Spawn selected", id="spawn-selected-btn", variant="primary"),
            Button("View full definition", id="view-selected-btn"),
            Button("Standalone instance", id="standalone-btn"),
            Button("Back", id="back-btn"),
            id="spawn-picker-footer",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.load_definitions()

    def load_definitions(self) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        list_view = self.query_one("#spawn-definition-list", ListView)
        clear_list_view(list_view)
        self._definitions = []
        self._detail = None
        try:
            self._definitions = client.list_definitions()
        except Exception as exc:
            self.notify(str(exc), severity="error")
            list_view.append(ListItem(Label(f"[state-error]{exc}[/]")))
            self._refresh_preview()
            return
        if not self._definitions:
            list_view.append(ListItem(Label("[state-info](no definitions — press c to create)[/]")))
            self._refresh_preview()
            return
        for item in self._definitions:
            badge = format_spawnable_badge(bool(item.get("spawnable")))
            name = item.get("persona_name")
            name_hint = f" · {name}" if name and name != item["definition_id"] else ""
            list_view.append(ListItem(Label(f"{item['definition_id']}{name_hint}  {badge}")))
        list_view.index = 0
        self.load_preview_for_selection()

    def _selected_index(self) -> int | None:
        if not self._definitions:
            return None
        list_view = self.query_one("#spawn-definition-list", ListView)
        index = list_view.index
        if index is None or index < 0 or index >= len(self._definitions):
            return None
        return index

    def _selected_definition(self) -> dict | None:
        index = self._selected_index()
        if index is None:
            return None
        return self._definitions[index]

    def load_preview_for_selection(self) -> None:
        selected = self._selected_definition()
        if selected is None:
            self._detail = None
            self._refresh_preview()
            return
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        self._loading_detail = True
        self._refresh_preview()
        try:
            self._detail = client.get_definition(selected["definition_id"])
        except Exception as exc:
            self._detail = None
            self.notify(str(exc), severity="error")
        finally:
            self._loading_detail = False
            self._refresh_preview()

    @staticmethod
    def _preview_excerpt(raw: str, max_lines: int = 8) -> str:
        import re

        body = re.sub(r"^---[\s\S]*?---\n?", "", raw or "").strip()
        lines = body.split("\n")[:max_lines]
        text = "\n".join(lines)
        if len(body.split("\n")) > max_lines:
            text += "\n…"
        return text or "(empty)"

    def _refresh_preview(self) -> None:
        preview = self.query_one("#picker-preview", Static)
        selected = self._selected_definition()
        spawn_btn = self.query_one("#spawn-selected-btn", Button)
        if selected is None:
            preview.update("[state-info]No definitions available.[/]")
            spawn_btn.disabled = True
            return
        if self._loading_detail:
            preview.update(f"[state-info]Loading {selected['definition_id']}…[/]")
            spawn_btn.disabled = True
            return
        if self._detail is None:
            preview.update("[state-error]Could not load definition preview.[/]")
            spawn_btn.disabled = True
            return
        spawnable = bool(self._detail.get("spawnable"))
        spawn_btn.disabled = not spawnable
        spawn_btn.label = "🚀 Spawn selected" if spawnable else "🟠 Review required"
        memory = "uses memory" if self._detail.get("uses_memory") else "no memory"
        persona = self._preview_excerpt(self._detail.get("persona_raw", ""))
        skills = self._preview_excerpt(self._detail.get("skills_raw", ""))
        preview.update(
            f"[bold]{selected['definition_id']}[/]\n"
            f"{format_spawnable_badge(spawnable)}  [state-info]{memory}[/]\n\n"
            f"[bold]Persona[/]\n{persona}\n\n"
            f"[bold]Skills[/]\n{skills}"
        )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != "spawn-definition-list":
            return
        self.load_preview_for_selection()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.id != "spawn-definition-list":
            return
        self.load_preview_for_selection()

    def action_spawn_selected(self) -> None:
        selected = self._selected_definition()
        if selected is None:
            self.notify("Select a definition first", severity="warning")
            return
        if not selected.get("spawnable"):
            self.notify("Review persona and skills before spawning", severity="warning")
            return
        self.app.push_screen(SpawnInstanceScreen(selected["definition_id"]))

    def action_view_selected(self) -> None:
        selected = self._selected_definition()
        if selected is None:
            self.notify("Select a definition first", severity="warning")
            return
        self.app.push_screen(DefinitionDetailScreen(selected["definition_id"]))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.action_back()
            return
        if event.button.id == "standalone-btn":
            self.app.push_screen(CreateAgentScreen())
            return
        if event.button.id == "view-selected-btn":
            self.action_view_selected()
            return
        if event.button.id == "spawn-selected-btn":
            self.action_spawn_selected()

    def action_back(self) -> None:
        self.app.pop_screen()


class CreateAgentScreen(Screen):
    BINDINGS = [("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(
            Static("➕ Create agent", id="title"),
            Static("Create a standalone instance without a definition.", id="create-hint"),
            Label("Agent ID"),
            Input(id="agent-id"),
            Label("Target puller"),
            Input(id="target-puller", value="puller-01"),
            Label("Model"),
            Input(id="model", value="llama3.1:8b"),
            Label("Persona name"),
            Input(id="persona-name"),
            Label("Persona role"),
            Input(id="persona-role", value="helpful assistant"),
            Horizontal(
                Button("Create", id="create-btn", variant="primary"),
                Button("Cancel", id="cancel-btn"),
            ),
            id="create-form",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.action_back()
            return
        if event.button.id != "create-btn":
            return
        agent_id = self.query_one("#agent-id", Input).value.strip()
        if not agent_id:
            self.notify("Agent ID required", severity="warning")
            return
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        payload = {
            "agent_id": agent_id,
            "target_puller": self.query_one("#target-puller", Input).value.strip(),
            "model": self.query_one("#model", Input).value.strip(),
            "persona_name": self.query_one("#persona-name", Input).value.strip() or None,
            "persona_role": self.query_one("#persona-role", Input).value.strip(),
        }
        try:
            client.create_agent(payload)
            self.notify(f"Created {agent_id}")
            self.app.pop_screen()
            self.app.push_screen(InstanceDetailScreen(agent_id))
        except Exception as exc:
            self.notify(f"Create failed: {exc}", severity="error")

    def action_back(self) -> None:
        self.app.pop_screen()


class InteractiveScreen(Screen):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, instance_id: str) -> None:
        super().__init__()
        self.instance_id = instance_id
        self._last_reply: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(f"Interactive: {self.instance_id}", id="title")
        yield Static("", id="interactive-status")
        yield TextArea("", id="chat-log", read_only=True)
        yield Input(placeholder="Message…", id="chat-input")
        yield Horizontal(
            Button("Send", id="send-btn", variant="primary"),
            Button("Back", id="back-btn"),
        )
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(1.5, self._poll)

    def _set_busy(self, busy: bool) -> None:
        chat_input = self.query_one("#chat-input", Input)
        send_btn = self.query_one("#send-btn", Button)
        chat_input.disabled = busy
        send_btn.disabled = busy

    def _poll(self) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            poll = client.poll_interactive(self.instance_id)
        except Exception:
            return
        state = poll.get("state", "unknown")
        busy = state == "interactive_busy"
        self._set_busy(busy)
        self.query_one("#interactive-status", Static).update(
            f"State: {format_state_badge(state)}"
        )
        reply = poll.get("last_reply")
        if reply and reply != self._last_reply:
            self._last_reply = reply
            log = self.query_one("#chat-log", TextArea)
            log.text = f"{log.text}\n[state-ready]assistant:[/] {reply}".strip() + "\n"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.action_back()
            return
        if event.button.id != "send-btn":
            return
        chat_input = self.query_one("#chat-input", Input)
        if chat_input.disabled:
            return
        message = self.query_one("#chat-input", Input).value.strip()
        if not message:
            return
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        log = self.query_one("#chat-log", TextArea)
        log.text = f"{log.text}\n[state-info]user:[/] {message}".strip() + "\n"
        self.query_one("#chat-input", Input).value = ""
        try:
            client.post_interactive_message(self.instance_id, message)
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def action_back(self) -> None:
        self.app.pop_screen()
