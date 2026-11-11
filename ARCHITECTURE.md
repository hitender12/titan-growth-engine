# TITAN Architecture

## Overview

TITAN is an analyst and decision-support system, not an autonomous ad bot.
Data flows one way — sources → canonical metrics → deterministic analytics
→ evidence-backed experiment cards — and stops at human approval. There is
no path from a recommendation to an external action in this codebase.

```
CSV import ──► canonical schema ──► in-memory metric store
                                        │
                     ┌──────────────────┼──────────────────┐
                     ▼                  ▼                  ▼
              analytics.py        analyst.py         experiments.py
           (trends, WoW,      (typed read-only    (cards from
            funnel,            tools + plain-       measured
            anomalies)         English questions)   evidence)
                     │                  │                  │
                     └──────────────────┴──────────────────┘
                                        ▼
                                  audit.py (append-only trail)
```

## Modules

| Module | Responsibility |
|---|---|
| `titan/schema.py` | Canonical `MetricObservation` + approved metric registry. Unknown metrics are validation errors, never guessed. |
| `titan/workspace.py` | Workspaces/projects. `get_project` is the single tenancy choke point; raises `TenantError` on cross-workspace access. |
| `titan/store.py` | Tenant-scoped in-memory store. Every read/write goes through the workspace manager. |
| `titan/importer.py` | CSV → canonical schema with per-row validation. Bad rows collected as errors; valid rows still import. `dim_*` columns become dimensions. |
| `titan/analytics.py` | Deterministic functions only: daily series, week-over-week, funnel drop-off, robust-z anomalies. No LLM arithmetic anywhere. |
| `titan/analyst.py` | Typed read-only tools (`total`, `top_declining_dimensions`, `detect_anomalies`, `funnel`, `week_over_week`) plus a deterministic rule-based question parser. Every answer carries evidence (source file, rows, query) or says "not enough data". |
| `titan/experiments.py` | Experiment cards generated only from measured evidence (an anomaly or a WoW decline), with confidence derived from evidence strength. Backlog tracks status/owner/result. |
| `titan/audit.py` | Append-only audit log: actor, action, object, trace id, timestamp. |
| `titan/eval_questions.py` | 20-question eval set with expected status and answer content. |

## Key design decisions

1. **Deterministic analytics, no LLM math.** All numbers come from
   `analytics.py`. The analyst quotes tool outputs; it cannot invent a
   figure. If an LLM is added later, it would only draft prose around
   tool results.
2. **Seasonality-aware anomalies.** Robust z-score (median/MAD) against
   the same weekday in the previous four weeks, so weekend dips don't
   fire. The MAD is floored at 5% of the baseline median — with only 2–4
   baseline points, a near-constant baseline otherwise yields absurd
   z-scores (we measured 34+ before the floor; after it, only the real
   injected drops fire, z ≈ −3.1 to −3.6).
3. **Tenant isolation at one choke point.** `WorkspaceManager.get_project`
   is called on every store read/write, so isolation can't be bypassed by
   a new caller forgetting a check.
4. **Reject, don't guess.** Unmapped metrics and unparseable rows are
   errors, surfaced to the user — never silently coerced.
5. **Read-only by design.** No module can perform an external action.
   Experiment cards carry a status field; approval is a human decision
   recorded in the backlog and the audit trail.

## Data model

- `workspace`: owner, plan, settings.
- `project`: website/domain, timezone, currency.
- `metric_observation`: project, source, metric name, dimensions, value,
  unit, time window, currency, timezone, attribution window, source file
  and row, fetched timestamp.
- `insight` (answer): question, summary, evidence references, confidence.
- `experiment`: hypothesis, target, baseline, treatment, owner, status, result.
- `audit_event`: actor, action, object, timestamp, trace id.

## What is not built yet (and why)

- **Web UI / API / Postgres** (Next.js + FastAPI + Supabase in the spec):
  the in-memory store proves the workflow first. The package boundaries
  (`store`, `analyst`, `experiments`) map directly onto future services.
- **Real OAuth connectors**: CSV import is the one read-only connector.
  Each future connector must map into the canonical schema and reject
  unmapped metrics the same way.
- **Rust `titan-metrics`**: only after benchmarks show the Python worker
  is the bottleneck, with a reproducible comparison on the same dataset.
  Never claim a speedup without that benchmark.
- **Write actions** (budget changes, publishing): explicitly out of scope
  until the read-only workflow is proven; they need approval flows, least
  privilege OAuth scopes, and envelope encryption for credentials.

## Threat model (summary)

- Cross-tenant leakage: mitigated by the single tenancy choke point and
  covered by integration tests (read and write).
- Silent data corruption: mitigated by strict import validation.
- Hallucinated recommendations: mitigated by evidence-linked answers and
  "not enough data" refusals; cards are generated only from measured
  evidence.
- Credential exposure: no credentials are stored in this repo; future
  connectors must use a secrets manager or envelope encryption, never
  plain text.
