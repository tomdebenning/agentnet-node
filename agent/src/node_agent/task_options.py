"""LLM task options, including the opt-in grading profile.

Normal chat uses the agent temperature (default 0.7) and num_ctx. A task may
override those two keys. Callers opt into deterministic grading with
``profile="grading"`` or ``profile="deterministic"``. That profile sets
temperature 0, a fixed seed, and thinking off. It does not change the chat
default, and the profile name is not forwarded to the puller.
"""

from __future__ import annotations

from typing import Any

# Same seed on every grading task so repeated grades are reproducible.
GRADING_SEED = 42

GRADING_PROFILE_NAMES = frozenset({"grading", "deterministic"})


class UnknownTaskProfile(ValueError):
    """Raised when a caller opts into a profile this runtime does not define."""


def normalize_task_profile(profile: object | None) -> str | None:
    """Return a canonical grading profile name, or None when the caller did not opt in."""
    if profile is None:
        return None
    if not isinstance(profile, str):
        raise UnknownTaskProfile(f"unknown task profile: {profile!r}")
    text = profile.strip().lower()
    if not text:
        return None
    if text not in GRADING_PROFILE_NAMES:
        raise UnknownTaskProfile(
            f"unknown task profile: {profile!r} (expected 'grading' or 'deterministic')"
        )
    return text


def grading_task_options() -> dict[str, Any]:
    """Task options for the grading/deterministic profile."""
    return {
        "temperature": 0,
        "seed": GRADING_SEED,
        "think": False,
    }


def resolve_task_options(
    *,
    temperature: float,
    num_ctx: int,
    run_options: dict[str, Any] | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    """Merge chat defaults, task overrides, and an optional grading profile.

    Explicit ``profile`` wins over ``run_options["profile"]``. When either is
    set, temperature, seed, and thinking come from the grading profile.
    ``num_ctx`` stays on the chat/task value. Task overrides of temperature
    apply only when the caller did not opt into the profile.
    """
    options = dict(run_options or {})
    selected = profile if profile is not None else options.get("profile")
    normalized = normalize_task_profile(selected)

    merged: dict[str, Any] = {
        "temperature": temperature,
        "num_ctx": num_ctx,
    }
    for key in ("temperature", "num_ctx"):
        if key in options:
            merged[key] = options[key]

    if normalized is not None:
        merged.update(grading_task_options())
    return merged
