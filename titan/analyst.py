"""Evidence-grounded analyst: typed read-only tools + plain-English questions.

Design rules (from the spec):
- All arithmetic happens in analytics.py, never in prose and never in
  an LLM. The tools below are typed, read-only, and scoped to one
  workspace + project + date range.
- Every factual claim in an answer points to evidence (source file, rows,
  and the query that produced it).
- When there is no evidence, the answer says "not enough data" instead
  of guessing.

The question interface is a deterministic rule-based parser over the
approved tools. It is deliberately not an LLM: with a fixed metric
registry and a fixed tool set, a parser is auditable and cannot invent
numbers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Optional

from . import analytics

METRIC_WORDS = {
    "click": "clicks", "clicks": "clicks",
    "conversion": "conversions", "conversions": "conversions",
    "session": "sessions", "sessions": "sessions",
    "impression": "impressions", "impressions": "impressions",
    "spend": "spend", "revenue": "revenue",
}

SOURCES = {"organic", "paid", "social", "email", "direct", "referral"}

FUNNEL_STAGES = [
    ("Impressions", "impressions"),
    ("Clicks", "clicks"),
    ("Sessions", "sessions"),
    ("Conversions", "conversions"),
]


@dataclass
class Evidence:
    tool: str
    params: dict
    summary: str
    source_refs: List[str] = field(default_factory=list)


@dataclass
class Answer:
    question: str
    status: str  # "answered" | "not_enough_data" | "cannot_answer"
    text: str
    evidence: List[Evidence] = field(default_factory=list)
    confidence: float = 0.0


def _refs(observations, limit=3):
    """Short source references for a set of observations."""
    refs = []
    for o in observations[:limit]:
        refs.append(o.ref())
    if len(observations) > limit:
        refs.append(f"... plus {len(observations) - limit} more rows from {observations[0].source_file}")
    return refs


def _metric_in(question: str) -> Optional[str]:
    for word, metric in METRIC_WORDS.items():
        if re.search(rf"\b{word}\b", question):
            return metric
    return None


def _source_in(question: str) -> Optional[str]:
    for s in SOURCES:
        if re.search(rf"\b{s}\b", question):
            return s
    return None


# ---------------------------------------------------------------- typed tools

def tool_total(store, workspace_id, project_id, metric, source=None, start=None, end=None):
    rows = store.query(workspace_id, project_id, metric=metric, source=source, start=start, end=end)
    total = sum(o.value for o in rows)
    ev = Evidence(
        tool="total",
        params={"metric": metric, "source": source, "start": str(start), "end": str(end)},
        summary=f"{total:,.0f} {metric} over {len(rows)} observations",
        source_refs=_refs(rows),
    )
    return total, ev


def tool_top_declining(store, workspace_id, project_id, metric, source=None, end=None, limit=5):
    rows = store.query(workspace_id, project_id, metric=metric, source=source)
    ranked = analytics.top_declining_dimensions(rows, metric, source, end=end, limit=limit)
    ev = Evidence(
        tool="top_declining_dimensions",
        params={"metric": metric, "source": source, "limit": limit},
        summary=", ".join(f"{d}: {c['delta_pct']:.1f}% WoW" for d, c in ranked) or "no dimensions",
        source_refs=_refs(rows),
    )
    return ranked, ev


def tool_anomalies(store, workspace_id, project_id, metric, source=None):
    rows = store.query(workspace_id, project_id, metric=metric, source=source)
    found = analytics.detect_anomalies(rows, metric, source)
    ev = Evidence(
        tool="detect_anomalies",
        params={"metric": metric, "source": source},
        summary=f"{len(found)} anomalies" if found else "no anomalies",
        source_refs=_refs(rows),
    )
    return found, ev


def tool_funnel(store, workspace_id, project_id, source=None, start=None, end=None):
    rows = store.query(workspace_id, project_id, source=source, start=start, end=end)
    stages = analytics.funnel(rows, FUNNEL_STAGES, source=source, start=start, end=end)
    ev = Evidence(
        tool="funnel",
        params={"source": source, "start": str(start), "end": str(end)},
        summary=" > ".join(f"{s['stage']} {s['total']:,.0f}" for s in stages),
        source_refs=_refs(rows),
    )
    return stages, ev


def tool_wow(store, workspace_id, project_id, metric, source=None, end=None):
    rows = store.query(workspace_id, project_id, metric=metric, source=source)
    comp = analytics.wow_comparison(rows, metric, source, end=end)
    ev = Evidence(
        tool="week_over_week",
        params={"metric": metric, "source": source},
        summary=f"current {comp['current']:,.0f} vs previous {comp['previous']:,.0f}",
        source_refs=_refs(rows),
    )
    return comp, ev


# ---------------------------------------------------------------- question interface

SUPPORTED_QUESTIONS = (
    "which landing pages lost <metric> last week",
    "what anomalies / anything unusual happened",
    "how many <metric> did we get (optionally: from <source>)",
    "show the funnel / where do we lose people",
    "how did <metric> change week over week",
    "which landing pages get the most <metric>",
)


def ask(store, workspace_id, project_id, question: str, actor: str = "analyst", audit=None) -> Answer:
    """Answer a plain-English question with evidence, or refuse honestly."""
    q = question.lower().strip()
    metric = _metric_in(q)
    source = _source_in(q)
    end = store.latest_date(workspace_id, project_id)

    def _log(answer):
        if audit is not None:
            audit.record(actor, "ask_question", "project", project_id,
                         detail=f"{question!r} -> {answer.status}")
        return answer

    # --- anomalies ------------------------------------------------------
    if re.search(r"\b(anomal\w*|unusual|wrong|spikes?|outlier)\b", q):
        m = metric or "clicks"
        found, ev = tool_anomalies(store, workspace_id, project_id, m, source)
        if not found:
            return _log(Answer(question, "not_enough_data",
                               f"Not enough data: no anomalies detected for {m}"
                               + (f" from {source}" if source else "")
                               + " in the available history.",
                               evidence=[ev], confidence=0.0))
        lines = [
            f"{a.dimensions.get('landing_page', '?')} on {a.day}: "
            f"{a.value:,.0f} vs a same-weekday baseline of {a.baseline_median:,.0f} "
            f"(robust z {a.robust_z}, {a.severity})"
            for a in found[:5]
        ]
        return _log(Answer(
            question, "answered",
            f"Found {len(found)} anomal{'y' if len(found) == 1 else 'ies'} in {m}"
            + (f" from {source}" if source else "") + ":\n- " + "\n- ".join(lines),
            evidence=[ev], confidence=0.85))

    # --- funnel ---------------------------------------------------------
    if "funnel" in q or "lose people" in q or "drop-off" in q or "dropoff" in q:
        stages, ev = tool_funnel(store, workspace_id, project_id, source)
        parts = []
        for s in stages:
            drop = (f", {s['dropoff_from_previous_pct']:.1f}% drop-off from previous stage"
                    if s["dropoff_from_previous_pct"] is not None else "")
            parts.append(f"{s['stage']}: {s['total']:,.0f}{drop}")
        return _log(Answer(
            question, "answered",
            "Funnel (all time" + (f", {source}" if source else "") + "):\n- " + "\n- ".join(parts),
            evidence=[ev], confidence=0.9))

    # --- declining landing pages ----------------------------------------
    if re.search(r"\b(lost|declin|down|fell|drop|dropped|losing)\b", q) and "landing" in q:
        m = metric or "clicks"
        ranked, ev = tool_top_declining(store, workspace_id, project_id, m, source, end=end)
        if not ranked:
            return _log(Answer(question, "not_enough_data",
                               f"Not enough data: no landing pages with {m} history"
                               + (f" from {source}" if source else "")
                               + " to compare week over week.",
                               evidence=[ev], confidence=0.0))
        lines = [
            f"{d}: {c['current']:,.0f} vs {c['previous']:,.0f} last week "
            f"({c['delta_pct']:.1f}%)"
            for d, c in ranked
        ]
        return _log(Answer(
            question, "answered",
            f"Landing pages that lost {m} the most week over week"
            + (f" ({source})" if source else "") + ":\n- " + "\n- ".join(lines),
            evidence=[ev], confidence=0.85))

    # --- top landing pages ----------------------------------------------
    if "landing" in q and re.search(r"\b(most|top|best|highest)\b", q):
        m = metric or "clicks"
        rows = store.query(workspace_id, project_id, metric=m, source=source)
        ranked = analytics.top_dimensions_by_total(rows, m, source)
        if not ranked:
            return _log(Answer(question, "not_enough_data",
                               f"Not enough data: no {m} recorded"
                               + (f" from {source}" if source else "") + ".",
                               evidence=[], confidence=0.0))
        ev = Evidence("top_dimensions_by_total", {"metric": m, "source": source},
                      ", ".join(f"{d}: {v:,.0f}" for d, v in ranked), _refs(rows))
        lines = [f"{d}: {v:,.0f}" for d, v in ranked]
        return _log(Answer(
            question, "answered",
            f"Top landing pages by {m}" + (f" ({source})" if source else "") + ":\n- " + "\n- ".join(lines),
            evidence=[ev], confidence=0.9))

    # --- week over week ---------------------------------------------------
    if re.search(r"week over week|vs last week|compared to last week|compared with last week", q):
        m = metric or "clicks"
        comp, ev = tool_wow(store, workspace_id, project_id, m, source, end=end)
        if comp["status"] == "no_data" or comp["delta_pct"] is None:
            return _log(Answer(question, "not_enough_data",
                               f"Not enough data: cannot compare {m} week over week"
                               + (f" from {source}" if source else "")
                               + " — less than two weeks of history.",
                               evidence=[ev], confidence=0.0))
        direction = "up" if comp["delta_pct"] >= 0 else "down"
        return _log(Answer(
            question, "answered",
            f"{m}" + (f" ({source})" if source else "") +
            f" is {direction} {abs(comp['delta_pct']):.1f}% week over week "
            f"({comp['current']:,.0f} vs {comp['previous']:,.0f}).",
            evidence=[ev], confidence=0.9))

    # --- totals -----------------------------------------------------------
    if re.search(r"\b(how many|total|how much)\b", q):
        m = metric or "clicks"
        total, ev = tool_total(store, workspace_id, project_id, m, source)
        if total == 0:
            return _log(Answer(question, "not_enough_data",
                               f"Not enough data: no {m} recorded"
                               + (f" from {source}" if source else "") + ".",
                               evidence=[ev], confidence=0.0))
        return _log(Answer(
            question, "answered",
            f"Total {m}" + (f" from {source}" if source else "") + f": {total:,.0f}.",
            evidence=[ev], confidence=0.9))

    # --- cannot answer ----------------------------------------------------
    return _log(Answer(
        question, "cannot_answer",
        "I cannot answer that from the approved metrics. I can answer:\n- "
        + "\n- ".join(SUPPORTED_QUESTIONS),
        evidence=[], confidence=0.0))
