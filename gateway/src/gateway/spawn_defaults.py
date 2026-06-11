"""Resolve spawn and run defaults from gateway config."""

from __future__ import annotations

from typing import Any

from gateway.config import GatewayConfig, SpawnDefaultsSection


def spawn_defaults_section(config: GatewayConfig) -> SpawnDefaultsSection:
    return config.spawn_defaults


def resolved_instance_config(
    config: GatewayConfig,
    *,
    model: str | None = None,
    target_puller: str | None = None,
    temperature: float | None = None,
    num_ctx: int | None = None,
) -> dict[str, Any]:
    defaults = spawn_defaults_section(config)
    return {
        "model": model if model is not None else defaults.model,
        "target_puller": target_puller if target_puller is not None else defaults.target_puller,
        "temperature": temperature if temperature is not None else defaults.temperature,
        "num_ctx": num_ctx if num_ctx is not None else defaults.num_ctx,
    }


def explicit_run_options(
    *,
    temperature: float | None = None,
    num_ctx: int | None = None,
) -> dict[str, Any]:
    options: dict[str, Any] = {}
    if temperature is not None:
        options["temperature"] = temperature
    if num_ctx is not None:
        options["num_ctx"] = num_ctx
    return options


def run_options_for_spawn(
    config: GatewayConfig,
    *,
    temperature: float | None = None,
    num_ctx: int | None = None,
) -> dict[str, Any]:
    resolved = resolved_instance_config(
        config,
        temperature=temperature,
        num_ctx=num_ctx,
    )
    return {
        "temperature": resolved["temperature"],
        "num_ctx": resolved["num_ctx"],
    }
