"""CSV import with schema validation into the canonical metric schema.

Required columns: timestamp, metric, value, source.
Optional columns: landing_page, unit, currency, timezone,
attribution_window, and any column named dim_<name> (becomes a dimension).

Rules:
- Unknown metrics are rejected, never silently mapped.
- Bad rows are collected as errors; valid rows are still imported.
- A missing required column fails the whole file.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime
from typing import List

from .schema import APPROVED_METRICS, DEFAULT_UNIT, MetricObservation, ValidationError

REQUIRED_COLUMNS = {"timestamp", "metric", "value", "source"}


@dataclass
class ImportResult:
    imported: int = 0
    errors: List[ValidationError] = field(default_factory=list)
    observations: list = field(default_factory=list)


def _parse_timestamp(raw: str, row_no: int) -> datetime:
    raw = (raw or "").strip()
    if not raw:
        raise ValidationError(row_no, "timestamp must not be empty")
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        raise ValidationError(row_no, f"unparseable timestamp {raw!r}")


def import_csv(
    store,
    workspace_id: str,
    project_id: str,
    text: str,
    source_file: str = "upload.csv",
    currency: str = "USD",
    timezone: str = "UTC",
    actor: str = "importer",
    audit=None,
) -> ImportResult:
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValidationError(0, "empty CSV: no header row")
    header = {h.strip() for h in reader.fieldnames if h}
    missing = REQUIRED_COLUMNS - header
    if missing:
        raise ValidationError(0, f"missing required columns: {sorted(missing)}")

    result = ImportResult()
    for i, row in enumerate(reader, start=2):
        try:
            metric = (row.get("metric") or "").strip().lower()
            if metric not in APPROVED_METRICS:
                raise ValidationError(
                    i, f"unmapped metric {metric!r}; approved: {sorted(APPROVED_METRICS)}"
                )
            value_raw = (row.get("value") or "").strip()
            try:
                value = float(value_raw)
            except ValueError:
                raise ValidationError(i, f"value {value_raw!r} is not a number")
            if value < 0:
                raise ValidationError(i, "value must not be negative")
            ts = _parse_timestamp(row.get("timestamp") or "", i)
            source = (row.get("source") or "").strip().lower()
            if not source:
                raise ValidationError(i, "source must not be empty")

            dims = {}
            if (row.get("landing_page") or "").strip():
                dims["landing_page"] = row["landing_page"].strip()
            for k, v in row.items():
                if k and k.startswith("dim_") and (v or "").strip():
                    dims[k[4:]] = v.strip()

            unit = (row.get("unit") or "").strip() or DEFAULT_UNIT[metric]
            obs = MetricObservation(
                workspace_id=workspace_id,
                project_id=project_id,
                source=source,
                metric=metric,
                value=value,
                timestamp=ts,
                dimensions=dims,
                unit=unit,
                currency=(row.get("currency") or "").strip() or currency,
                timezone=(row.get("timezone") or "").strip() or timezone,
                attribution_window=(row.get("attribution_window") or "").strip() or "7d_click",
                source_file=source_file,
                source_row=i,
            )
            store.add(obs)  # raises TenantError on cross-tenant writes
            result.observations.append(obs)
            result.imported += 1
        except ValidationError as e:
            result.errors.append(e)

    if audit is not None:
        audit.record(
            actor,
            "csv_import",
            "project",
            project_id,
            detail=f"{source_file}: {result.imported} imported, {len(result.errors)} errors",
        )
    return result
