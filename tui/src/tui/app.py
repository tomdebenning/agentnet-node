"""Textual admin UI."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, ListItem, ListView, Static, TextArea

from tui.api_client import ApiClient
from tui.connection_status import format_connection_status
from tui.list_helpers import clear_list_view
from tui.status_styles import format_state_badge


class AgentListScreen(Screen):
    BINDINGS = [("c", "create", "Create"), ("r", "refresh", "Refresh"), ("q", "quit", "Quit")]

    def __init__(self) -> None:
        super().__init__()
        self._agents: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="connection-status")
        yield Static("Agents", id="title")
        yield ListView(id="agent-list")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_connection()
        self.refresh_list()

    def refresh_connection(self) -> None:
        app: NodeTuiApp = self.app  # type: ignore[assignment]
        info = app.api_client.connectivity()
        app.update_connection_subtitle(info)
        panel = self.query_one("#connection-status", Static)
        panel.update(format_connection_status(info))

    def refresh_list(self) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        list_view = self.query_one("#agent-list", ListView)
        clear_list_view(list_view)
        self._agents = []

        info = client.connectivity()
        self.app.update_connection_subtitle(info)  # type: ignore[attr-defined]
        self.query_one("#connection-status", Static).update(format_connection_status(info))

        if not info.get("gateway_connected"):
            self.notify(
                f"Cannot reach gateway at {info['gateway_url']}: {info.get('gateway_error')}",
                severity="error",
            )
            return

        try:
            agents = client.list_instances()
        except Exception as exc:
            self.notify(f"Failed to load agents: {exc}", severity="error")
            return
        self._agents = agents
        for agent in agents:
            state = agent.get("process_state")
            label = f"{agent['instance_id']}  {format_state_badge(state)}"
            list_view.append(ListItem(Label(label)))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if not self._agents:
            return
        index = event.index
        if index < 0 or index >= len(self._agents):
            return
        agent_id = self._agents[index]["instance_id"]
        self.app.push_screen(AgentDetailScreen(agent_id))

    def action_refresh(self) -> None:
        self.refresh_list()

    def action_create(self) -> None:
        self.app.push_screen(CreateAgentScreen())

    def action_quit(self) -> None:
        self.app.exit()


class CreateAgentScreen(Screen):
    BINDINGS = [("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(
            Label("Agent ID"),
            Input(id="agent-id"),
            Label("Target puller"),
            Input(id="target-puller", value="puller-01"),
            Label("Model"),
            Input(id="model", value="llama3.1:8b"),
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
        }
        try:
            client.create_agent(payload)
            self.notify(f"Created {agent_id}")
            self.app.pop_screen()
            list_screen = self.app.screen
            if isinstance(list_screen, AgentListScreen):
                list_screen.refresh_list()
        except Exception as exc:
            self.notify(f"Create failed: {exc}", severity="error")

    def action_back(self) -> None:
        self.app.pop_screen()


class AgentDetailScreen(Screen):
    BINDINGS = [
        ("escape", "back", "Back"),
        ("s", "start", "Start"),
        ("x", "stop", "Stop"),
        ("d", "delete", "Delete"),
    ]

    _BROWSE_KINDS = frozenset({"conversations", "workspace", "databases"})

    def __init__(self, agent_id: str) -> None:
        super().__init__()
        self.agent_id = agent_id
        self._current_kind = "config"
        self._process_state = "stopped"
        self._workspace_path = "."
        self._browse_items: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(f"Agent: {self.agent_id}", id="detail-title")
        yield Static("", id="detail-status")
        yield Static("Files", id="files-label")
        yield Horizontal(
            Button("Config", id="tab-config"),
            Button("Persona", id="tab-persona"),
            Button("Skills", id="tab-skills"),
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
            Button("Delete", id="delete-btn", variant="error"),
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#browse-list").display = False
        self.query_one("#browse-hint").display = False
        self.load_agent()
        self.load_file("config")

    def load_agent(self) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            info = client.get_instance(self.agent_id)
        except Exception as exc:
            self.notify(str(exc), severity="error")
            return
        self.query_one("#detail-status", Static).update(
            f"State: {format_state_badge(info['process_state'])}  PID: {info.get('pid') or '-'}"
        )
        self._process_state = info["process_state"]

    def _is_running(self) -> bool:
        return getattr(self, "_process_state", "stopped") == "running"

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
            data = client.read_file(self.agent_id, kind)
            self.query_one("#editor", TextArea).text = data["raw"]
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
            conversations = client.list_conversations(self.agent_id)
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
        self.query_one("#browse-hint", Static).update(
            f"Workspace: {self._workspace_path}"
        )
        self.query_one("#editor", TextArea).text = ""
        if self._workspace_path not in (".", ""):
            self._browse_items.append({"kind": "ws", "path": ".."})
            list_view.append(ListItem(Label(".. (parent)")))
        try:
            payload = client.list_workspace(self.agent_id, self._workspace_path)
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
            databases = client.list_databases(self.agent_id)
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
        if not self._is_browse_mode():
            return
        if not self._browse_items:
            return
        index = event.index
        if index < 0 or index >= len(self._browse_items):
            return
        selected = self._browse_items[index]
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        editor = self.query_one("#editor", TextArea)

        if selected["kind"] == "conv":
            try:
                data = client.get_conversation(self.agent_id, selected["id"])
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
                client.list_workspace(self.agent_id, path)
                self._workspace_path = path
                self._load_workspace_list()
            except Exception:
                try:
                    file_data = client.read_workspace_file(self.agent_id, path)
                    editor.text = file_data["content"]
                except Exception as exc:
                    self.notify(str(exc), severity="error")
            return

        if selected["kind"] == "db":
            try:
                info = client.get_database(self.agent_id, selected["name"])
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

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "tab-config":
            self.load_file("config")
        elif button_id == "tab-persona":
            self.load_file("persona")
        elif button_id == "tab-skills":
            self.load_file("skills")
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
        elif button_id == "delete-btn":
            self.action_delete()

    def save_file(self) -> None:
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
            client.stop_agent(self.agent_id)
            self.load_agent()
        except Exception as exc:
            self.notify(f"Stop failed: {exc}", severity="error")
            return
        self._write_file()

    def _write_file(self) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        content = self.query_one("#editor", TextArea).text
        try:
            client.write_file(self.agent_id, self._current_kind, content)
            self.notify("Saved")
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def action_start(self) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            client.start_agent(self.agent_id)
            self.load_agent()
            self.notify("Started")
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def action_stop(self) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            client.stop_agent(self.agent_id)
            self.load_agent()
            self.notify("Stopped")
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def action_delete(self) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            client.delete_agent(self.agent_id)
            self.notify("Deleted")
            self.app.pop_screen()
            screen = self.app.screen
            if isinstance(screen, AgentListScreen):
                screen.refresh_list()
            from tui.fleet_screens import MainScreen

            if isinstance(screen, MainScreen):
                screen.refresh_all()
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def action_back(self) -> None:
        self.app.pop_screen()


class NodeTuiApp(App):
    TITLE = "Agentnet Node"
    CSS_PATH = "theme.tcss"
    BINDINGS = [
        ("f", "show_running", "Running"),
        ("b", "show_bullpen", "Definitions"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, api_url: str = "http://127.0.0.1:8080") -> None:
        super().__init__()
        self.api_client = ApiClient(api_url)
        self.sub_title = "Checking connections…"

    def update_connection_subtitle(self, info: dict) -> None:
        from tui.connection_status import format_connection_subtitle

        self.sub_title = format_connection_subtitle(info)

    def _main_screen(self) -> MainScreen | None:
        from tui.fleet_screens import MainScreen

        for screen in reversed(self.screen_stack):
            if isinstance(screen, MainScreen):
                return screen
        return None

    def _go_main_panel(self, panel: str) -> None:
        from tui.fleet_screens import MainScreen

        # Close overlay screens; never pop MainScreen itself.
        while len(self.screen_stack) > 1 and not isinstance(self.screen, MainScreen):
            self.pop_screen()

        if not isinstance(self.screen, MainScreen):
            # MainScreen was removed (e.g. old f/b bug) — mount a fresh shell.
            self.push_screen(MainScreen(initial_panel=panel))
            return

        main = self.screen
        if panel == "running":
            main.action_show_running()
        else:
            main.action_show_bullpen()

    def action_show_running(self) -> None:
        self._go_main_panel("running")

    def action_show_bullpen(self) -> None:
        self._go_main_panel("bullpen")

    def action_quit(self) -> None:
        self.exit()

    def on_unmount(self) -> None:
        self.api_client.close()

    def on_mount(self) -> None:
        from tui.fleet_screens import MainScreen

        self.push_screen(MainScreen())
        self.set_interval(15.0, self._poll_connection)

    def _poll_connection(self) -> None:
        from tui.connection_status import refresh_connection_panel

        refresh_connection_panel(self, self.screen)
