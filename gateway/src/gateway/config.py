"""Gateway configuration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings


class NodeSection(BaseModel):
    id: str
    descriptive_info: dict[str, Any] = Field(default_factory=dict)


class ServerSection(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8080


class ControlPlaneSection(BaseModel):
    url: str
    request_timeout_seconds: float = 10.0
    max_retries: int = 3
    retry_backoff_base_seconds: float = 1.0


class HeartbeatSection(BaseModel):
    interval_seconds: float = 30.0


class BraveSearchSection(BaseModel):
    api_key: str = ""


class LoggingSection(BaseModel):
    level: str = "INFO"
    format: str = "console"


class SpawnDefaultsSection(BaseModel):
    """Default model/puller/LLM options for spawn UX and API fallbacks."""

    model: str = "llama3.1:8b"
    target_puller: str = "puller-01"
    temperature: float = 0.7
    num_ctx: int = 8192


class GatewayConfig(BaseModel):
    node: NodeSection
    server: ServerSection = Field(default_factory=ServerSection)
    agents_root: str = "./agents"
    definitions_root: str | None = None
    database: str = "./gateway.db"
    templates_root: str | None = None
    spawn_defaults: SpawnDefaultsSection = Field(default_factory=SpawnDefaultsSection)
    control_plane: ControlPlaneSection
    heartbeat: HeartbeatSection = Field(default_factory=HeartbeatSection)
    brave_search: BraveSearchSection = Field(default_factory=BraveSearchSection)
    logging: LoggingSection = Field(default_factory=LoggingSection)

    @model_validator(mode="after")
    def _normalize_roots(self) -> GatewayConfig:
        if not self.definitions_root:
            self.definitions_root = self.templates_root or "./definitions"
        return self

    @property
    def agents_root_path(self) -> Path:
        return Path(self.agents_root).expanduser().resolve()

    @property
    def definitions_root_path(self) -> Path:
        root = self.definitions_root or "./definitions"
        return Path(root).expanduser().resolve()

    @property
    def database_path(self) -> Path:
        return Path(self.database).expanduser().resolve()

    @property
    def brave_api_key(self) -> str:
        return os.environ.get("BRAVE_SEARCH_API_KEY", "").strip() or self.brave_search.api_key.strip()


def resolve_config_path(explicit: Path | str | None = None) -> Path:
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("AGENTNET_NODE_CONFIG", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path("config.yaml").resolve()


def load_config(path: Path | str | None = None) -> GatewayConfig:
    config_path = resolve_config_path(path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return GatewayConfig.model_validate(raw)
