"""Tests for TITAN core: tenancy, validation, anomalies, analyst evidence,
experiment cards, funnel/WoW math, audit trail, read-only behaviour, and
the 20-question evaluation set.
"""
import pathlib
import unittest
from datetime import datetime, timedelta

from titan import (
    WorkspaceManager, MetricStore, MetricObservation, TenantError,
    import_csv, ValidationError, ask, detect_anomalies, funnel,
    wow_comparison, generate_from_anomaly, ExperimentBacklog,
    generate_from_decline, AuditLog,
)
from titan.analytics import top_declining_dimensions
from titan.eval_questions import EVAL_QUESTIONS

ROOT = pathlib.Path(__file__).parent.parent
SAMPLE_CSV = (ROOT / "sample-data" / "sample_metrics.csv").read_text()


def _setup():
    """Fresh manager/store with the sample dataset imported."""
    manager = WorkspaceManager()
    store = MetricStore(manager)
    ws = manager.create_workspace("Test Agency", owner="tester@example.com")
    project = manager.create_project(ws.id, "test.example.com")
    result = import_csv(store, ws.id, project.id, SAMPLE_CSV, source_file="sample_metrics.csv")
    assert result.imported > 0, "sample CSV failed to import"
    assert not result.errors, f"sample CSV had errors: {result.errors[:3]}"
    return manager, store, ws, project


def _obs(ws, prj, metric, value, day, source="organic", dims=None):
    return MetricObservation(
        workspace_id=ws, project_id=prj, source=source, metric=metric,
        value=value, timestamp=datetime(2026, 11, 1) + timedelta(days=day),
        dimensions=dims or {"landing_page": "/pricing"},
    )


class TestTenantIsolation(unittest.TestCase):
    def test_cross_workspace_read_is_denied(self):
        manager = WorkspaceManager()
        store = MetricStore(manager)
        ws_a = manager.create_workspace("A", owner="a@example.com")
        ws_b = manager.create_workspace("B", owner="b@example.com")
        prj_a = manager.create_project(ws_a.id, "a.example.com")
        store.add(_obs(ws_a.id, prj_a.id, "clicks", 10, 0))
        with self.assertRaises(TenantError):
            store.query(ws_b.id, prj_a.id)
        with self.assertRaises(TenantError):
            store.count(ws_b.id, prj_a.id)

    def test_cross_workspace_write_is_denied(self):
        manager = WorkspaceManager()
        store = MetricStore(manager)
        ws_a = manager.create_workspace("A", owner="a@example.com")
        ws_b = manager.create_workspace("B", owner="b@example.com")
        prj_a = manager.create_project(ws_a.id, "a.example.com")
        # Observation claims ws_b but the project belongs to ws_a.
        with self.assertRaises(TenantError):
            store.add(_obs(ws_b.id, prj_a.id, "clicks", 10, 0))

    def test_same_workspace_can_read(self):
        manager, store, ws, prj = _setup()
        self.assertGreater(store.count(ws.id, prj.id), 0)


class TestCsvValidation(unittest.TestCase):
    def _csv(self, header, rows):
        return header + "\n" + "\n".join(rows) + "\n"

    def test_missing_required_column_fails_file(self):
        manager = WorkspaceManager()
        store = MetricStore(manager)
        ws = manager.create_workspace("A", owner="a@example.com")
        prj = manager.create_project(ws.id, "a.example.com")
        with self.assertRaises(ValidationError):
            import_csv(store, ws.id, prj.id,
                       self._csv("timestamp,metric,value", ["2026-11-01,clicks,5"]))

    def test_unmapped_metric_rejected(self):
        manager = WorkspaceManager()
        store = MetricStore(manager)
        ws = manager.create_workspace("A", owner="a@example.com")
        prj = manager.create_project(ws.id, "a.example.com")
        res = import_csv(store, ws.id, prj.id, self._csv(
            "timestamp,metric,value,source",
            ["2026-11-01,clicks,5,organic",
             "2026-11-01,vibes,5,organic",
             "2026-11-01,clicks,7,organic"]))
        self.assertEqual(res.imported, 2)
        self.assertEqual(len(res.errors), 1)
        self.assertIn("unmapped metric", res.errors[0].message)

    def test_bad_timestamp_and_negative_value(self):
        manager = WorkspaceManager()
        store = MetricStore(manager)
        ws = manager.create_workspace("A", owner="a@example.com")
        prj = manager.create_project(ws.id, "a.example.com")
        res = import_csv(store, ws.id, prj.id, self._csv(
            "timestamp,metric,value,source",
            ["not-a-date,clicks,5,organic",
             "2026-11-01,clicks,-3,organic",
             "2026-11-01,clicks,abc,organic",
             "2026-11-01,clicks,4,organic"]))
        self.assertEqual(res.imported, 1)
        self.assertEqual(len(res.errors), 3)

    def test_dim_columns_become_dimensions(self):
        manager = WorkspaceManager()
        store = MetricStore(manager)
        ws = manager.create_workspace("A", owner="a@example.com")
        prj = manager.create_project(ws.id, "a.example.com")
        res = import_csv(store, ws.id, prj.id, self._csv(
            "timestamp,metric,value,source,landing_page,dim_campaign",
            ["2026-11-01,clicks,5,organic,/home,spring-sale"]))
        self.assertEqual(res.imported, 1)
        obs = res.observations[0]
        self.assertEqual(obs.dimensions["landing_page"], "/home")
        self.assertEqual(obs.dimensions["campaign"], "spring-sale")


class TestAnomalyDetection(unittest.TestCase):
    def test_injected_drop_is_flagged(self):
        manager = WorkspaceManager()
        store = MetricStore(manager)
        ws = manager.create_workspace("A", owner="a@example.com")
        prj = manager.create_project(ws.id, "a.example.com")
        # Five Mondays: four normal (~100), one collapsed (20).
        for week, value in enumerate([100, 102, 98, 101, 20]):
            store.add(_obs(ws.id, prj.id, "clicks", value, week * 7, dims={"landing_page": "/pricing"}))
        rows = store.query(ws.id, prj.id, metric="clicks")
        found = detect_anomalies(rows, "clicks")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].dimensions["landing_page"], "/pricing")
        self.assertLess(found[0].robust_z, -3.0)
        self.assertEqual(found[0].severity, "high")

    def test_stable_series_has_no_anomalies(self):
        manager = WorkspaceManager()
        store = MetricStore(manager)
        ws = manager.create_workspace("A", owner="a@example.com")
        prj = manager.create_project(ws.id, "a.example.com")
        for week in range(5):
            store.add(_obs(ws.id, prj.id, "clicks", 100 + week, week * 7,
                           dims={"landing_page": "/home"}))
        rows = store.query(ws.id, prj.id, metric="clicks")
        self.assertEqual(detect_anomalies(rows, "clicks"), [])

    def test_sample_data_pricing_anomaly(self):
        _, store, ws, prj = _setup()
        rows = store.query(ws.id, prj.id, metric="clicks", source="organic")
        found = detect_anomalies(rows, "clicks", source="organic")
        pages = {a.dimensions["landing_page"] for a in found}
        self.assertIn("/pricing", pages)
        worst = max(found, key=lambda a: abs(a.robust_z))
        self.assertEqual(worst.dimensions["landing_page"], "/pricing")


class TestAnalytics(unittest.TestCase):
    def test_wow_math(self):
        manager = WorkspaceManager()
        store = MetricStore(manager)
        ws = manager.create_workspace("A", owner="a@example.com")
        prj = manager.create_project(ws.id, "a.example.com")
        for day in range(14):
            store.add(_obs(ws.id, prj.id, "clicks", 10 if day < 7 else 20, day))
        rows = store.query(ws.id, prj.id, metric="clicks")
        comp = wow_comparison(rows, "clicks", end=datetime(2026, 11, 14).date())
        self.assertEqual(comp["current"], 140.0)
        self.assertEqual(comp["previous"], 70.0)
        self.assertAlmostEqual(comp["delta_pct"], 100.0)

    def test_funnel_dropoff_ordering(self):
        _, store, ws, prj = _setup()
        rows = store.query(ws.id, prj.id)
        stages = funnel(rows, [("Impressions", "impressions"), ("Clicks", "clicks"),
                               ("Sessions", "sessions"), ("Conversions", "conversions")])
        totals = [s["total"] for s in stages]
        self.assertEqual(totals, sorted(totals, reverse=True))
        for s in stages[1:]:
            self.assertGreaterEqual(s["dropoff_from_previous_pct"], 0.0)
            self.assertLessEqual(s["dropoff_from_previous_pct"], 100.0)


class TestAnalyst(unittest.TestCase):
    def test_declining_pages_question_returns_evidence(self):
        _, store, ws, prj = _setup()
        ans = ask(store, ws.id, prj.id, "Which landing pages lost organic clicks last week?")
        self.assertEqual(ans.status, "answered")
        self.assertIn("/pricing", ans.text)
        self.assertTrue(ans.evidence)
        self.assertTrue(all(e.source_refs for e in ans.evidence))
        self.assertGreater(ans.confidence, 0.5)

    def test_missing_metric_says_not_enough_data(self):
        _, store, ws, prj = _setup()
        ans = ask(store, ws.id, prj.id, "Which landing pages lost revenue last week?")
        self.assertEqual(ans.status, "not_enough_data")
        self.assertIn("Not enough data", ans.text)

    def test_unanswerable_question_refuses(self):
        _, store, ws, prj = _setup()
        ans = ask(store, ws.id, prj.id, "What should our brand voice be?")
        self.assertEqual(ans.status, "cannot_answer")

    def test_analyst_is_read_only(self):
        _, store, ws, prj = _setup()
        before = store.count(ws.id, prj.id)
        for q in ("Which landing pages lost organic clicks last week?",
                  "Show the funnel", "How many clicks did we get?"):
            ask(store, ws.id, prj.id, q)
        self.assertEqual(store.count(ws.id, prj.id), before)

    def test_eval_set_20_questions(self):
        _, store, ws, prj = _setup()
        self.assertEqual(len(EVAL_QUESTIONS), 20)
        failures = []
        for item in EVAL_QUESTIONS:
            ans = ask(store, ws.id, prj.id, item["question"])
            if ans.status != item["expect_status"]:
                failures.append(f"{item['question']!r}: status {ans.status}, "
                                f"expected {item['expect_status']}")
            elif item["expect_contains"] not in ans.text:
                failures.append(f"{item['question']!r}: text missing "
                                f"{item['expect_contains']!r}\n{text(ans)}")
        self.assertEqual(failures, [])


def text(ans):
    return ans.text[:400]


class TestExperiments(unittest.TestCase):
    def test_card_links_evidence(self):
        _, store, ws, prj = _setup()
        rows = store.query(ws.id, prj.id, metric="clicks", source="organic")
        found = detect_anomalies(rows, "clicks", source="organic")
        self.assertTrue(found)
        card = generate_from_anomaly(found[0], owner="growth")
        self.assertTrue(card.evidence_refs)
        self.assertIn("/pricing", card.hypothesis)
        self.assertIn(str(found[0].robust_z), card.evidence_refs[0])
        self.assertGreaterEqual(card.confidence, 0.5)
        self.assertEqual(card.status, "draft")

    def test_backlog_status_and_result(self):
        _, store, ws, prj = _setup()
        rows = store.query(ws.id, prj.id, metric="clicks", source="organic")
        ranked = top_declining_dimensions(rows, "clicks", source="organic")
        self.assertTrue(ranked)
        d, comp = ranked[0]
        backlog = ExperimentBacklog()
        card = backlog.add(generate_from_decline(d, comp, owner="growth"))
        self.assertEqual(card.status, "draft")
        backlog.set_status(card.id, "approved")
        self.assertEqual(backlog.get(card.id).status, "approved")
        backlog.record_result(card.id, "Recovered 60% of the loss in 2 weeks.")
        self.assertEqual(backlog.get(card.id).status, "done")
        self.assertIn("60%", backlog.get(card.id).result)


class TestAuditTrail(unittest.TestCase):
    def test_import_and_questions_are_audited(self):
        manager = WorkspaceManager()
        store = MetricStore(manager)
        audit = AuditLog()
        ws = manager.create_workspace("A", owner="a@example.com")
        prj = manager.create_project(ws.id, "a.example.com")
        import_csv(store, ws.id, prj.id, SAMPLE_CSV, source_file="sample_metrics.csv",
                   audit=audit)
        ask(store, ws.id, prj.id, "Show the funnel", audit=audit)
        kinds = [e.action for e in audit.all()]
        self.assertIn("csv_import", kinds)
        self.assertIn("ask_question", kinds)
        for e in audit.all():
            self.assertTrue(e.trace_id)


if __name__ == "__main__":
    unittest.main()
