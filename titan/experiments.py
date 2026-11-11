"""Experiment cards: hypothesis, evidence, expected outcome, measurement plan.

A card is only generated from measured evidence (an anomaly or a
week-over-week decline). Every card links its evidence references, so a
human reviewer can check the data before approving anything. Cards never
trigger external actions; status changes are human decisions.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import List


@dataclass
class ExperimentCard:
    title: str
    hypothesis: str
    target_metric: str
    baseline: float
    treatment: str
    evidence_refs: List[str]
    expected_outcome: str
    confidence: float  # 0.0 - 1.0, derived from evidence strength
    effort: str  # "S" | "M" | "L"
    risk: str  # "low" | "medium" | "high"
    measurement_plan: str
    status: str = "draft"  # draft | proposed | approved | running | done
    owner: str = "unassigned"
    result: str = ""
    id: str = field(default_factory=lambda: f"exp_{uuid.uuid4().hex[:8]}")


def _confidence_from_z(z: float) -> float:
    """Map anomaly strength to a confidence in [0.5, 0.9]."""
    return round(min(0.9, 0.5 + min(0.4, abs(z) * 0.05)), 2)


def generate_from_anomaly(anomaly, owner: str = "growth") -> ExperimentCard:
    page = anomaly.dimensions.get("landing_page", "the affected page")
    if anomaly.robust_z < 0:
        direction = "drop"
        hypothesis = (
            f"The drop in {anomaly.metric} on {page} on {anomaly.day} "
            f"({anomaly.value:,.0f} vs a same-weekday baseline of "
            f"{anomaly.baseline_median:,.0f}) is caused by a change on that page, "
            f"and fixing it will recover the metric toward baseline."
        )
        treatment = (
            f"Audit {page} for recent changes (copy, layout, tracking, offers), "
            f"fix the most likely cause, then monitor daily {anomaly.metric}."
        )
        expected_outcome = (
            f"Recover {anomaly.metric} on {page} to within 10% of the baseline "
            f"median ({anomaly.baseline_median:,.0f}) within 14 days."
        )
        measurement_plan = (
            f"Track daily {anomaly.metric} for {page} for 14 days against the "
            f"same-weekday baseline. Success: value within 10% of baseline on "
            f"at least 5 of the last 7 days. Owner records the result here."
        )
    else:
        direction = "spike"
        hypothesis = (
            f"The spike in {anomaly.metric} on {page} on {anomaly.day} "
            f"({anomaly.value:,.0f} vs a same-weekday baseline of "
            f"{anomaly.baseline_median:,.0f}) was driven by an identifiable change "
            f"(campaign, referrer, content or external mention), and replicating "
            f"that driver will sustain the lift."
        )
        treatment = (
            f"Identify what drove the spike on {page} (campaign, referrer, content "
            f"change, external mention), then replicate the driver on this page "
            f"or a comparable one."
        )
        expected_outcome = (
            f"Sustain {anomaly.metric} on {page} above the baseline median "
            f"({anomaly.baseline_median:,.0f}) on at least 5 of the next 7 days, "
            f"or reproduce the lift on a comparable page."
        )
        measurement_plan = (
            f"Track daily {anomaly.metric} for {page} for 14 days against the "
            f"same-weekday baseline. Success: value above baseline on at least "
            f"5 of the last 7 days, with the driver documented. Owner records "
            f"the result here."
        )
    return ExperimentCard(
        title=f"Investigate {direction} in {anomaly.metric} on {page}",
        hypothesis=hypothesis,
        target_metric=anomaly.metric,
        baseline=anomaly.baseline_median,
        treatment=treatment,
        evidence_refs=[
            f"anomaly {anomaly.metric} {page} {anomaly.day} robust_z={anomaly.robust_z}",
            f"baseline same-weekday values: {anomaly.evidence.get('baseline_same_weekday')}",
        ],
        expected_outcome=expected_outcome,
        confidence=_confidence_from_z(anomaly.robust_z),
        effort="M",
        risk="low",
        measurement_plan=measurement_plan,
        owner=owner,
    )


def generate_from_decline(dimension: str, comparison: dict, owner: str = "growth") -> ExperimentCard:
    metric = comparison["metric"]
    delta = comparison["delta_pct"]
    return ExperimentCard(
        title=f"Recover {metric} on {dimension} ({delta:.1f}% WoW)",
        hypothesis=(
            f"{dimension} lost {metric} week over week "
            f"({comparison['current']:,.0f} vs {comparison['previous']:,.0f}, {delta:.1f}%). "
            f"A targeted improvement to the page will recover at least half the loss."
        ),
        target_metric=metric,
        baseline=comparison["previous"],
        treatment=(
            f"Test one change on {dimension}: clearer headline and call to action "
            f"above the fold, then compare {metric} week over week."
        ),
        evidence_refs=[
            f"week-over-week {metric} {dimension}: "
            f"{comparison['current']:,.0f} vs {comparison['previous']:,.0f} ({delta:.1f}%) "
            f"window {comparison['window'][0]}..{comparison['window'][1]}",
        ],
        expected_outcome=(
            f"Recover at least 50% of the {abs(delta):.1f}% {metric} loss on "
            f"{dimension} within 2 weeks."
        ),
        confidence=round(min(0.85, 0.5 + min(0.35, abs(delta) / 200)), 2),
        effort="S",
        risk="low",
        measurement_plan=(
            f"Run the treatment for 14 days. Compare {metric} on {dimension} "
            f"week over week against the pre-change baseline of "
            f"{comparison['previous']:,.0f}. Record the result on this card."
        ),
        owner=owner,
    )


class ExperimentBacklog:
    """Status, owner and result tracking for experiment cards."""

    def __init__(self):
        self.cards = {}

    def add(self, card: ExperimentCard) -> ExperimentCard:
        self.cards[card.id] = card
        return card

    def list(self, status=None):
        cards = list(self.cards.values())
        if status is not None:
            cards = [c for c in cards if c.status == status]
        return sorted(cards, key=lambda c: c.confidence, reverse=True)

    def get(self, card_id: str) -> ExperimentCard:
        return self.cards[card_id]

    def set_status(self, card_id: str, status: str) -> ExperimentCard:
        card = self.cards[card_id]
        card.status = status
        return card

    def record_result(self, card_id: str, result: str) -> ExperimentCard:
        card = self.cards[card_id]
        card.result = result
        card.status = "done"
        return card
