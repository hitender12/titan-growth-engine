"""Canonical metric schema for TITAN.

Every observation imported into TITAN is normalized into this schema:
source, timestamp, currency, timezone and attribution window are always
recorded. Metrics that are not in the approved registry are rejected at
import time rather than silently guessed (see importer.py).
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict

# Approved metrics. Anything else is a validation error at import.
APPROVED_METRICS = {"impressions", "clicks", "sessions", "conversions", "spend", "revenue"}

DEFAULT_UNIT = {
    "impressions": "count",
    "clicks": "count",
    "sessions": "count",
    "conversions": "count",
    "spend": "USD",
    "revenue": "USD",
}

DEFAULT_ATTRIBUTION_WINDOW = "7d_click"


class ValidationError(Exception):
    """A single row (or the file header) failed schema validation."""

    def __init__(self, row: int, message: str):
        self.row = row
        self.message = message
        super().__init__(f"row {row}: {message}")


_id_counter = itertools.count(1)


@dataclass
class MetricObservation:
    """One normalized metric observation in the canonical schema."""

    workspace_id: str
    project_id: str
    source: str
    metric: str
    value: float
    timestamp: datetime
    dimensions: Dict[str, str] = field(default_factory=dict)
    unit: str = "count"
    currency: str = "USD"
    timezone: str = "UTC"
    attribution_window: str = DEFAULT_ATTRIBUTION_WINDOW
    source_file: str = ""
    source_row: int = 0
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: str = field(default_factory=lambda: f"obs_{next(_id_counter)}")

    def dimension_key(self):
        """Stable, hashable identity of this observation's dimensions."""
        return tuple(sorted(self.dimensions.items()))

    def ref(self) -> str:
        """Short evidence reference used by the analyst and experiment cards."""
        dims = ",".join(f"{k}={v}" for k, v in sorted(self.dimensions.items()))
        return f"{self.source_file}:{self.source_row} [{self.source} {self.metric} {dims} {self.timestamp.date()}={self.value}]"
