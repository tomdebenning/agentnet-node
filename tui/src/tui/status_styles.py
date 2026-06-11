"""Status colors and Rich markup for the TUI (mirrors web statusBadges)."""

from __future__ import annotations


def badge_class_for_state(state: str | None) -> str:
    s = (state or "unknown").lower()
    if s in {
        "running",
        "completed",
        "interactive_idle",
        "ok",
        "success",
        "spawnable",
        "ready",
        "connected",
    }:
        return "state-ready"
    if s in {"pending", "stopped", "not_spawnable", "needs_review", "disconnected"}:
        return "state-review"
    if s in {"error", "failed", "fail"}:
        return "state-error"
    if s in {"interactive_busy", "working", "attention"}:
        return "state-attention"
    return "state-info"


def state_emoji(state: str | None) -> str:
    s = (state or "unknown").lower()
    if s in {"running", "completed", "interactive_idle", "ok", "success", "spawnable", "ready", "connected"}:
        return "✅"
    if s in {"pending", "stopped", "not_spawnable", "needs_review", "disconnected"}:
        return "🟠"
    if s in {"error", "failed", "fail"}:
        return "🔴"
    if s in {"interactive_busy", "working", "attention"}:
        return "🟡"
    return "ℹ️"


def format_state_badge(state: str | None) -> str:
    cls = badge_class_for_state(state)
    label = state or "unknown"
    return f"[{cls}]{state_emoji(state)} {label}[/]"


def format_review_badge(reviewed: bool) -> str:
    if reviewed:
        return "[state-ready]✅ Reviewed[/]"
    return "[state-review]🟠 Needs review[/]"


def format_spawnable_badge(spawnable: bool) -> str:
    if spawnable:
        return "[state-ready]✅ Spawnable[/]"
    return "[state-review]🟠 Needs review[/]"


def format_ready_banner(*, persona_reviewed: bool, skills_reviewed: bool, spawnable: bool | None = None) -> str:
    ready = spawnable if spawnable is not None else (persona_reviewed and skills_reviewed)
    if ready:
        return "[state-ready]✅ Definition is spawnable — persona and skills reviewed.[/]"
    parts = ["[state-review]🟠 Review required before spawning."]
    if not persona_reviewed:
        parts.append(" Persona not reviewed.")
    if not skills_reviewed:
        parts.append(" Skills not reviewed.")
    parts.append("[/]")
    return "".join(parts)


def preview_lines(text: str, limit: int = 4) -> str:
    lines = text.split("\n")[:limit]
    body = "\n".join(lines) if lines else "(empty)"
    return body
