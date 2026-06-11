"""In-memory completion events for autonomous instances."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class CompletionEvent:
    instance_id: str
    definition_id: str | None
    completed_at: str
    success: bool
    error: str | None = None
    mode: str = "autonomous"


class CompletionLog:
    def __init__(self, max_events: int = 200) -> None:
        self._events: deque[CompletionEvent] = deque(maxlen=max_events)

    def record(
        self,
        *,
        instance_id: str,
        definition_id: str | None,
        success: bool,
        error: str | None = None,
        mode: str = "autonomous",
    ) -> CompletionEvent:
        event = CompletionEvent(
            instance_id=instance_id,
            definition_id=definition_id,
            completed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            success=success,
            error=error,
            mode=mode,
        )
        self._events.appendleft(event)
        return event

    def recent(self, limit: int = 50) -> list[CompletionEvent]:
        return list(list(self._events)[:limit])
