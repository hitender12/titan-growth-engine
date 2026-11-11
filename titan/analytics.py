"""Deterministic analytics: trends, week-over-week, funnels, anomalies.

All calculations are plain deterministic functions over stored
observations. No LLM ever does arithmetic here; the analyst (analyst.py)
only calls these functions and quotes their outputs.

Anomaly detection uses robust z-scores (median / MAD) against a
seasonality-aware baseline: the same weekday in the previous four weeks.
That keeps ordinary weekly patterns (e.g. weekend dips) from firing.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional


@dataclass
class Anomaly:
    metric: str
    source: str
    dimensions: dict
    day: date
    value: float
    baseline_median: float
    robust_z: float
    severity: str  # "medium" | "high"
    evidence: dict = field(default_factory=dict)


def _day(ts) -> date:
    return ts.date()


def daily_series(observations, metric=None, source=None, dimensions=None):
    """Aggregate observations into a sorted [(date, total)] series."""
    totals = {}
    for o in observations:
        if metric is not None and o.metric != metric:
            continue
        if source is not None and o.source != source:
            continue
        if dimensions and not all(o.dimensions.get(k) == v for k, v in dimensions.items()):
            continue
        d = _day(o.timestamp)
        totals[d] = totals.get(d, 0.0) + o.value
    return sorted(totals.items())


def _sum_range(series, start, end):
    return sum(v for d, v in series if start <= d <= end)


def wow_comparison(observations, metric, source=None, dimensions=None, end=None):
    """Compare the last 7 days against the previous 7 days."""
    series = daily_series(observations, metric, source, dimensions)
    if not series:
        return {
            "metric": metric,
            "source": source,
            "dimensions": dimensions or {},
            "current": 0.0,
            "previous": 0.0,
            "delta_pct": None,
            "status": "no_data",
        }
    last_day = end or series[-1][0]
    cur_start = last_day - timedelta(days=6)
    prev_end = cur_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=6)
    current = _sum_range(series, cur_start, last_day)
    previous = _sum_range(series, prev_start, prev_end)
    delta = None if previous == 0 else (current - previous) / previous * 100.0
    return {
        "metric": metric,
        "source": source,
        "dimensions": dimensions or {},
        "current": current,
        "previous": previous,
        "delta_pct": delta,
        "status": "ok",
        "window": (str(cur_start), str(last_day)),
        "previous_window": (str(prev_start), str(prev_end)),
    }


def top_declining_dimensions(observations, metric, source=None, dimension_key="landing_page",
                             end=None, limit=5):
    """Rank dimension values by week-over-week change, worst first."""
    dims = set()
    for o in observations:
        if o.metric == metric and (source is None or o.source == source) \
                and dimension_key in o.dimensions:
            dims.add(o.dimensions[dimension_key])
    ranked = []
    for d in sorted(dims):
        comp = wow_comparison(observations, metric, source, {dimension_key: d}, end=end)
        if comp["status"] != "ok" or comp["delta_pct"] is None:
            continue
        ranked.append((d, comp))
    ranked.sort(key=lambda x: x[1]["delta_pct"])
    return ranked[:limit]


def top_dimensions_by_total(observations, metric, source=None, dimension_key="landing_page",
                            start=None, end=None, limit=5):
    """Rank dimension values by total in a window, largest first."""
    totals = {}
    for o in observations:
        if o.metric != metric:
            continue
        if source is not None and o.source != source:
            continue
        if dimension_key not in o.dimensions:
            continue
        if start is not None and o.timestamp.date() < start:
            continue
        if end is not None and o.timestamp.date() > end:
            continue
        totals[o.dimensions[dimension_key]] = totals.get(o.dimensions[dimension_key], 0.0) + o.value
    return sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:limit]


def funnel(observations, stages, source=None, start=None, end=None):
    """Compute stage totals and drop-off rates.

    stages: list of (label, metric). Drop-off is measured against the
    previous stage, so stages must be ordered from widest to narrowest.
    """
    out = []
    prev = None
    for label, metric in stages:
        rows = [
            o for o in observations
            if o.metric == metric
            and (source is None or o.source == source)
            and (start is None or o.timestamp.date() >= start)
            and (end is None or o.timestamp.date() <= end)
        ]
        total = sum(o.value for o in rows)
        drop = None
        if prev is not None and prev > 0:
            drop = (prev - total) / prev * 100.0
        out.append({
            "stage": label,
            "metric": metric,
            "total": total,
            "dropoff_from_previous_pct": drop,
        })
        prev = total
    return out


def detect_anomalies(observations, metric, source=None, dimension_key="landing_page",
                     z_threshold=3.0, min_history_weeks=2):
    """Robust-z anomalies vs the same weekday in the previous four weeks.

    A day is anomalous when its robust z-score (0.6745 * (x - median) / MAD)
    against the same-weekday baseline reaches the threshold. The MAD is
    floored at 5% of the baseline median: with only two to four baseline
    points, a nearly constant baseline would otherwise produce absurd
    z-scores (e.g. 30+) from ordinary noise.
    """
    dims = set()
    for o in observations:
        if o.metric == metric and (source is None or o.source == source) \
                and dimension_key in o.dimensions:
            dims.add(o.dimensions[dimension_key])

    anomalies = []
    for d in sorted(dims):
        series = dict(daily_series(observations, metric, source, {dimension_key: d}))
        for day in sorted(series):
            baseline = [
                series[day - timedelta(weeks=w)]
                for w in range(1, 5)
                if (day - timedelta(weeks=w)) in series
            ]
            if len(baseline) < min_history_weeks:
                continue
            med = statistics.median(baseline)
            mad = statistics.median([abs(x - med) for x in baseline])
            value = series[day]
            spread = mad
            if med > 0:
                spread = max(mad, 0.05 * med)  # floor: see docstring
            if spread > 0:
                z = 0.6745 * (value - med) / spread
            elif value == med:
                z = 0.0
            else:
                z = 10.0 if value > 0 else 0.0
            if abs(z) >= z_threshold:
                anomalies.append(Anomaly(
                    metric=metric,
                    source=source,
                    dimensions={dimension_key: d},
                    day=day,
                    value=value,
                    baseline_median=med,
                    robust_z=round(z, 2),
                    severity="high" if abs(z) >= 5 else "medium",
                    evidence={
                        "baseline_same_weekday": baseline,
                        "baseline_weeks": len(baseline),
                    },
                ))
    anomalies.sort(key=lambda a: abs(a.robust_z), reverse=True)
    return anomalies
