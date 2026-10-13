"""Fail fast when a spawn targets a puller that cannot run the model."""

from __future__ import annotations

from typing import Any


class PullerUnavailable(Exception):
    """The target puller is missing, stale, or does not list the requested model."""


def check_puller_liveness(
    pullers: list[dict[str, Any]],
    *,
    target_puller: str,
    model: str,
) -> None:
    """Raise PullerUnavailable unless an active puller record can run ``model``.

    ``pullers`` is the JSON body of ``GET /pullers?active_only=true``. A puller
    that the control plane left out of that list is treated as missing or stale.
    A record that is present but marked stale, or that does not advertise the
    model, is its own error so the spawn does not wait out the response timeout.
    """
    matches = [
        item for item in pullers if str(item.get("puller_name") or "") == target_puller
    ]
    if not matches:
        raise PullerUnavailable(
            f"target puller {target_puller!r} is missing or stale "
            "(not listed by GET /pullers?active_only=true)"
        )
    record = matches[0]
    if record.get("is_stale") is True:
        raise PullerUnavailable(f"target puller {target_puller!r} is stale")
    models = record.get("supported_models") or []
    if not isinstance(models, list) or model not in models:
        listed = (
            ", ".join(str(item) for item in models)
            if isinstance(models, list) and models
            else "(none)"
        )
        raise PullerUnavailable(
            f"target puller {target_puller!r} does not list model {model!r} "
            f"(supported: {listed})"
        )
