# THIS FILE MUST BE KEPT IN SYNC WITH:
#   control-plane/src/control_plane/schemas.py
#   task-puller/src/task_puller/schemas.py
#   dagent-one/src/agent/schemas.py
#   agentnet-node/src/gateway/schemas.py
# All four files must remain byte-identical (including ActivityKind / ActivityEvent).
# Any change here requires synchronized changes in the other three repos.

from __future__ import annotations

import json
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ToolCall(BaseModel):
    """A tool call emitted by the LLM (Ollama native tool-calling format)."""

    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    type: Literal["function"] = "function"
    function: dict[str, Any] = Field(default_factory=dict)  # {"name": str, "arguments": ...}

    @field_validator("function", mode="before")
    @classmethod
    def _coerce_tool_function(cls, v: object) -> object:
        """Omitting or null `function` is common in the wild; some stacks send JSON text."""
        if v is None:
            return {}
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                return {}
            try:
                parsed = json.loads(stripped)
            except ValueError:
                return {}
            if isinstance(parsed, dict):
                return parsed
            return {}
        return {}


class Message(BaseModel):
    """A single message in an Ollama chat completion request/response."""

    model_config = ConfigDict(extra="ignore")

    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None  # for role="tool"
    name: str | None = None  # for role="tool", the tool name

    @field_validator("content", mode="before")
    @classmethod
    def _coerce_null_content(cls, value: object) -> object:
        """Ollama uses null content when the turn is tool_calls-only; accept that on the wire."""
        if value is None:
            return ""
        return value


class ToolDefinition(BaseModel):
    """A tool exposed to the LLM (Ollama native tool-calling format)."""

    model_config = ConfigDict(extra="ignore")

    type: Literal["function"] = "function"
    function: dict[str, Any]  # {"name": str, "description": str, "parameters": JSON schema}


class Task(BaseModel):
    """Submitted by an agent, routed to a task puller."""

    model_config = ConfigDict(extra="ignore")

    agent_id: str
    conversation_id: str
    round: int
    target_puller: str
    model: str
    messages: list[Message]
    tools: list[ToolDefinition] | None = None
    options: dict[str, Any] | None = None  # temperature, num_ctx, etc.
    submitted_at: str  # ISO 8601 UTC


class Response(BaseModel):
    """Returned by a task puller, routed to the originating agent."""

    model_config = ConfigDict(extra="ignore")

    agent_id: str
    conversation_id: str
    round: int
    puller_name: str
    message: Message | None = None  # the assistant's reply; None on error
    error: str | None = None
    completed_at: str  # ISO 8601 UTC

    @field_validator("error", mode="before")
    @classmethod
    def _coerce_error_detail(cls, v: object) -> object:
        """Some runtimes POST structured errors; agents expect a plain string."""
        if v is None or isinstance(v, str):
            return v
        if isinstance(v, dict):
            for key in ("message", "detail", "error"):
                inner = v.get(key)
                if isinstance(inner, str) and inner.strip():
                    return inner
            return json.dumps(v, sort_keys=True, separators=(",", ":"))
        if isinstance(v, (list, tuple)):
            return json.dumps(v, separators=(",", ":"))
        return str(v)


class PullerHeartbeat(BaseModel):
    model_config = ConfigDict(extra="ignore")

    puller_name: str
    status: Literal["idle", "busy", "starting", "error"]
    supported_models: list[str]  # union of config-advertised and live Ollama /api/tags
    descriptive_info: dict[str, Any] = Field(default_factory=dict)


class AgentHeartbeat(BaseModel):
    model_config = ConfigDict(extra="ignore")

    agent_id: str
    status: Literal["idle", "working", "waiting_for_llm", "error"]
    descriptive_info: dict[str, Any] = Field(default_factory=dict)


class PullerRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    puller_name: str
    status: str
    supported_models: list[str]
    descriptive_info: dict[str, Any]
    last_heartbeat_at: str  # ISO 8601 UTC
    first_seen_at: str


class AgentRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    agent_id: str
    status: str
    descriptive_info: dict[str, Any]
    last_heartbeat_at: str
    first_seen_at: str


class NodeHeartbeat(BaseModel):
    model_config = ConfigDict(extra="ignore")

    node_id: str
    status: Literal["idle", "busy", "starting", "error"]
    agent_count: int = 0
    running_agent_count: int = 0
    descriptive_info: dict[str, Any] = Field(default_factory=dict)


class NodeRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    node_id: str
    status: str
    agent_count: int
    running_agent_count: int
    descriptive_info: dict[str, Any]
    last_heartbeat_at: str
    first_seen_at: str


ActivityKind = Literal[
    "task_submitted",
    "task_fetched",
    "response_submitted",
    "response_fetched",
    "puller_heartbeat",
    "agent_heartbeat",
    "node_heartbeat",
    "queue_purged",
    "registry_removed",
]

ACTIVITY_KIND_VALUES: frozenset[str] = frozenset(get_args(ActivityKind))


class ActivityEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_id: int
    timestamp: str  # ISO 8601 UTC
    kind: ActivityKind
    actor: str | None = None  # who initiated (e.g., agent_id for task_submitted, puller_name for task_fetched)
    target: str | None = None  # the entity being acted on (e.g., target_puller for task_submitted)
    details: dict[str, Any] = Field(default_factory=dict)  # small contextual fields; NEVER message contents
