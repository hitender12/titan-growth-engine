# TITAN — AI Growth Intelligence Engine

> TITAN turns connected marketing metrics into traceable growth experiments. Every recommendation links back to the data behind it; external actions remain under human control.

TITAN is an analyst and decision-support system for small agencies and growth teams. It turns messy marketing data into evidence-backed experiments: connect a source, see what changed, ask a question in plain English, and get a prioritized experiment card with the data behind it.

**Read-only by design.** TITAN never changes ads, budgets, or publishes anything. A human approves every external action.

## Quickstart

```bash
python3 demo.py            # full workflow on the synthetic sample workspace
python3 -m unittest discover -s tests   # 20 tests, including the 20-question eval set
```

No dependencies beyond Python 3.10+ standard library.

## What works (MVP core)

- **Workspaces and projects** with tenant isolation — one workspace can never read or write another's metrics (tested).
- **CSV import** with schema validation into a canonical metric schema (source, timestamp, currency, timezone, attribution window). Unknown metrics are rejected, never silently mapped. Bad rows are collected as errors; valid rows still import.
- **Normalized metrics store** with time-series trends, week-over-week comparison, and funnel drop-off.
- **Anomaly detection** with robust z-scores (median/MAD) against a seasonality-aware baseline — the same weekday in the previous four weeks, with the MAD floored at 5% of the baseline median so near-constant baselines don't produce absurd scores.
- **Plain-English analyst**: typed, read-only query tools over approved metrics. Answers cite their evidence (source file, rows, query). When evidence is missing it says "not enough data" instead of guessing. All arithmetic is deterministic; no LLM does math.
- **Experiment cards**: hypothesis, evidence references, expected outcome, confidence, effort, risk, measurement plan, status/owner/result. Generated only from measured evidence.
- **Audit trail**: every import, question, and card creation is recorded with actor, action, object, and trace id.
- **Evaluation set**: 20 test questions with expected outcomes in `titan/eval_questions.py`, all passing.

## Sample data

`sample-data/sample_metrics.csv` — 3,570 rows, 42 days of **synthetic** data (clearly labelled), five landing pages × four sources. Two injected anomalies for the demo and eval: `/pricing` organic clicks collapse in the last week, and `/signup` conversions drop in the last week. Regenerate with `python3 tools/gen_sample.py` (seeded, reproducible).

## Example

```
Q: Which landing pages lost organic clicks last week?
A: /pricing: 198 vs 637 last week (-68.9%)
   /home: 993 vs 1,026 last week (-3.2%)
   ...with source references for every number.
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md). Package layout:

```
titan/               # core package: workspace, store, schema, importer,
                     # analytics, analyst, experiments, audit, eval_questions
sample-data/         # synthetic fixtures only
tools/               # sample-data generator
tests/               # test_titan.py (20 tests)
demo.py              # end-to-end demo
```

## Honest status

This repo is the **Python MVP core** from the spec: the workspace, ingestion, analytics, analyst, experiment backlog, and audit trail all run and are tested. What is **not** built yet (all documented as next steps in `ARCHITECTURE.md`):

- No web UI (Next.js dashboard), no FastAPI service, no PostgreSQL — the store is in-memory.
- No real OAuth connectors (Google Search Console etc.) — CSV import is the one read-only connector.
- No Rust `titan-metrics` module — add it only after benchmarks show Python is the bottleneck, with a reproducible comparison.
- No LLM in the loop — the analyst is a deterministic rule-based parser over typed tools. That is a deliberate choice for auditability; an LLM would only draft prose around tool outputs, never compute.
- No write actions of any kind.

## Evaluation plan

- 20-question eval set with expected status and evidence (`titan/eval_questions.py`).
- Tenant-isolation integration test (cross-workspace read and write both denied).
- Anomaly precision on the injected anomalies in the sample data.
- Ingestion throughput / aggregation latency benchmarks (to be added with the Rust module comparison).

## License

MIT — see [LICENSE](LICENSE).
