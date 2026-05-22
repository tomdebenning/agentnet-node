"""Textual admin UI."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, ListItem, ListView, Static, TextArea

from tui.api_client import ApiClient
from tui.connection_status import format_connection_status


class AgentListScreen(Screen):
    BINDINGS = [("c", "create", "Create"), ("r", "refresh", "Refresh"), ("q", "quit", "Quit")]

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
        list_view.clear()

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
            agents = client.list_agents()
        except Exception as exc:
            self.notify(f"Failed to load agents: {exc}", severity="error")
            return
        for agent in agents:
            label = f"{agent['agent_id']}  [{agent['process_state']}]"
            list_view.append(ListItem(Label(label), id=f"agent-{agent['agent_id']}"))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id.startswith("agent-"):
            agent_id = item_id.removeprefix("agent-")
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

    def __init__(self, agent_id: str) -> None:
        super().__init__()
        self.agent_id = agent_id
        self._current_kind = "config"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(f"Agent: {self.agent_id}", id="detail-title")
        yield Static("", id="detail-status")
        yield Horizontal(
            Button("Config", id="tab-config"),
            Button("Persona", id="tab-persona"),
            Button("Memory", id="tab-memory"),
        )
        yield TextArea("", id="editor", language="markdown")
        yield Horizontal(
            Button("Save", id="save-btn", variant="primary"),
            Button("Start", id="start-btn"),
            Button("Stop", id="stop-btn"),
            Button("Delete", id="delete-btn", variant="error"),
        )
        yield Footer()

    def on_mount(self) -> None:
        self.load_agent()
        self.load_file("config")

    def load_agent(self) -> None:
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            info = client.get_agent(self.agent_id)
        except Exception as exc:
            self.notify(str(exc), severity="error")
            return
        self.query_one("#detail-status", Static).update(
            f"State: {info['process_state']}  PID: {info.get('pid') or '-'}"
        )

    def load_file(self, kind: str) -> None:
        self._current_kind = kind
        client: ApiClient = self.app.api_client  # type: ignore[attr-defined]
        try:
            data = client.read_file(self.agent_id, kind)
            self.query_one("#editor", TextArea).text = data["raw"]
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "tab-config":
            self.load_file("config")
        elif button_id == "tab-persona":
            self.load_file("persona")
        elif button_id == "tab-memory":
            self.load_file("memory")
        elif button_id == "save-btn":
            self.save_file()
        elif button_id == "start-btn":
            self.action_start()
        elif button_id == "stop-btn":
            self.action_stop()
        elif button_id == "delete-btn":
            self.action_delete()

    def save_file(self) -> None:
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
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def action_back(self) -> None:
        self.app.pop_screen()


class NodeTuiApp(App):
    TITLE = "Agentnet Node"
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, api_url: str = "http://127.0.0.1:8080") -> None:
        super().__init__()
        self.api_client = ApiClient(api_url)
        self.sub_title = "Checking connections…"

    def update_connection_subtitle(self, info: dict) -> None:
        from tui.connection_status import format_connection_subtitle

        self.sub_title = format_connection_subtitle(info)

    def on_unmount(self) -> None:
        self.api_client.close()

    def on_mount(self) -> None:
        self.push_screen(AgentListScreen())
        self.set_interval(15.0, self._poll_connection)

    def _poll_connection(self) -> None:
        screen = self.screen
        if isinstance(screen, AgentListScreen):
            screen.refresh_connection()
