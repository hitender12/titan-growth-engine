"""Demo: the full TITAN workflow on the synthetic sample workspace.

1. Create a workspace and project.
2. Import the sample CSV (synthetic, labelled as such).
3. Show trends, week-over-week, funnel drop-off and anomalies.
4. Ask plain-English questions and get evidence-backed answers.
5. Generate experiment cards from the evidence.
6. Show the audit trail.

Run:  python3 demo.py
"""
import pathlib

from titan import (
    WorkspaceManager, MetricStore, import_csv, ask,
    wow_comparison, funnel, detect_anomalies, AuditLog,
    generate_from_anomaly, generate_from_decline, ExperimentBacklog,
)
from titan.analytics import top_declining_dimensions

ROOT = pathlib.Path(__file__).parent


def main():
    print("=" * 72)
    print("TITAN — AI Growth Intelligence Engine (demo, synthetic data)")
    print("=" * 72)

    manager = WorkspaceManager()
    store = MetricStore(manager)
    audit = AuditLog()
    backlog = ExperimentBacklog()

    ws = manager.create_workspace("Acme Growth", owner="demo@example.com")
    project = manager.create_project(ws.id, "acme.example.com", timezone="UTC", currency="USD")
    print(f"\nWorkspace: {ws.name} ({ws.id})  |  Project: {project.domain} ({project.id})")

    # 2. Import ----------------------------------------------------------
    text = (ROOT / "sample-data" / "sample_metrics.csv").read_text()
    result = import_csv(store, ws.id, project.id, text,
                        source_file="sample_metrics.csv", audit=audit)
    print(f"\n[import] {result.imported} rows imported, {len(result.errors)} errors")
    for e in result.errors[:3]:
        print(f"  error: {e}")

    # 3. Analytics -------------------------------------------------------
    rows = store.query(ws.id, project.id)
    comp = wow_comparison(rows, "clicks")
    print(f"\n[week-over-week] clicks: {comp['current']:,.0f} vs {comp['previous']:,.0f} "
          f"({comp['delta_pct']:.1f}%)")
    print("\n[declining landing pages — organic clicks]")
    for d, c in top_declining_dimensions(rows, "clicks", source="organic"):
        print(f"  {d}: {c['current']:,.0f} vs {c['previous']:,.0f} ({c['delta_pct']:.1f}%)")
    print("\n[anomalies — clicks]")
    anomalies = detect_anomalies(rows, "clicks")
    for a in anomalies[:5]:
        print(f"  {a.dimensions.get('landing_page')} {a.day}: {a.value:,.0f} "
              f"vs baseline {a.baseline_median:,.0f} (robust z {a.robust_z}, {a.severity})")
    print("\n[funnel]")
    for s in funnel(rows, [("Impressions", "impressions"), ("Clicks", "clicks"),
                           ("Sessions", "sessions"), ("Conversions", "conversions")]):
        drop = f" — {s['dropoff_from_previous_pct']:.1f}% drop-off" \
            if s["dropoff_from_previous_pct"] is not None else ""
        print(f"  {s['stage']}: {s['total']:,.0f}{drop}")

    # 4. Questions --------------------------------------------------------
    print("\n[analyst]")
    for q in (
        "Which landing pages lost organic clicks last week?",
        "What anomalies happened?",
        "Show the funnel",
    ):
        ans = ask(store, ws.id, project.id, q, audit=audit)
        print(f"\n  Q: {q}\n  A [{ans.status}, confidence {ans.confidence}]: {ans.text}")
        for ev in ans.evidence:
            print(f"    evidence ({ev.tool}): {ev.summary}")

    # 5. Experiment cards --------------------------------------------------
    print("\n[experiment backlog]")
    drops = [a for a in anomalies if a.robust_z < 0]
    card_anomaly = drops[0] if drops else (anomalies[0] if anomalies else None)
    if card_anomaly:
        card = generate_from_anomaly(card_anomaly, owner="growth")
        backlog.add(card)
        audit.record("analyst", "create_experiment", "experiment", card.id,
                     detail=f"from anomaly {card_anomaly.dimensions} {card_anomaly.day}")
        print(f"  - {card.title}\n    hypothesis: {card.hypothesis}\n"
              f"    expected: {card.expected_outcome}\n"
              f"    confidence {card.confidence}, effort {card.effort}, risk {card.risk}, "
              f"status {card.status}")
    declining = top_declining_dimensions(rows, "clicks", source="organic")
    if declining:
        d, c = declining[0]
        card = generate_from_decline(d, c, owner="growth")
        backlog.add(card)
        print(f"  - {card.title}\n    hypothesis: {card.hypothesis}\n"
              f"    expected: {card.expected_outcome}\n"
              f"    confidence {card.confidence}, effort {card.effort}, risk {card.risk}, "
              f"status {card.status}")

    # 6. Audit trail --------------------------------------------------------
    print("\n[audit trail]")
    for ev in audit.all():
        print(f"  {ev.timestamp.strftime('%H:%M:%S')} {ev.actor} {ev.action} "
              f"{ev.object_type}:{ev.object_id} — {ev.detail} (trace {ev.trace_id})")

    print("\nDemo complete. Nothing here changed any external system: "
          "TITAN is read-only by design.")


if __name__ == "__main__":
    main()
