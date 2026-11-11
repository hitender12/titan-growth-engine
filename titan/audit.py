"""Append-only audit trail.

Every import, question and experiment-card creation is recorded with an
actor, an action, the affected object and a trace id, so any
recommendation can be traced back to the data behind it.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List


@dataclass
class AuditEvent:
    actor: str
    action: str
    object_type: str
    object_id: str
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    detail: str = ""


class AuditLog:
    """In-memory, append-only log. Events are never mutated or deleted."""

    def __init__(self):
        self.events: List[AuditEvent] = []

    def record(
        self, actor: str, action: str, object_type: str, object_id: str, detail: str = ""
    ) -> AuditEvent:
        ev = AuditEvent(
            actor=actor, action=action, object_type=object_type, object_id=object_id, detail=detail
        )
        self.events.append(ev)
        return ev

    def for_object(self, object_type: str, object_id: str) -> List[AuditEvent]:
        return [e for e in self.events if e.object_type == object_type and e.object_id == object_id]

    def all(self) -> List[AuditEvent]:
        return list(self.events)
