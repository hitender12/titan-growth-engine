"""Evaluation set: 20 plain-English questions with expected outcomes.

Run against the synthetic sample dataset (sample-data/sample_metrics.csv).
Each entry states the expected answer status and a substring that must
appear in the answer text. These are the acceptance criteria for the
analyst: a question is only "answered" when the evidence supports it.
"""
from __future__ import annotations

# The sample data ends 2026-11-11. /pricing organic clicks collapse in the
# last 7 days; /signup conversions dip in the last 7 days. There are no
# revenue rows, so revenue questions must come back "not_enough_data".

EVAL_QUESTIONS = [
    {"question": "Which landing pages lost organic clicks last week?",
     "expect_status": "answered", "expect_contains": "/pricing"},
    {"question": "Which landing pages lost clicks last week?",
     "expect_status": "answered", "expect_contains": "/pricing"},
    {"question": "Which landing pages lost conversions last week?",
     "expect_status": "answered", "expect_contains": "/signup"},
    {"question": "Which landing pages lost paid clicks last week?",
     "expect_status": "answered", "expect_contains": "Landing pages"},
    {"question": "What anomalies happened?",
     "expect_status": "answered", "expect_contains": "/pricing"},
    {"question": "Is anything unusual in organic clicks?",
     "expect_status": "answered", "expect_contains": "/pricing"},
    {"question": "Anything wrong with conversions?",
     "expect_status": "answered", "expect_contains": "/signup"},
    {"question": "How many clicks did we get?",
     "expect_status": "answered", "expect_contains": "Total clicks"},
    {"question": "How many conversions did we get from organic?",
     "expect_status": "answered", "expect_contains": "Total conversions"},
    {"question": "How much spend did we get?",
     "expect_status": "answered", "expect_contains": "Total spend"},
    {"question": "How many impressions did we get from paid?",
     "expect_status": "answered", "expect_contains": "Total impressions"},
    {"question": "Show the funnel",
     "expect_status": "answered", "expect_contains": "Funnel"},
    {"question": "Where do we lose people in the funnel?",
     "expect_status": "answered", "expect_contains": "drop-off"},
    {"question": "Show the funnel for organic",
     "expect_status": "answered", "expect_contains": "Funnel"},
    {"question": "How did clicks change week over week?",
     "expect_status": "answered", "expect_contains": "week over week"},
    {"question": "How did organic conversions change week over week?",
     "expect_status": "answered", "expect_contains": "week over week"},
    {"question": "How did paid clicks change compared to last week?",
     "expect_status": "answered", "expect_contains": "week over week"},
    {"question": "Which landing pages get the most clicks?",
     "expect_status": "answered", "expect_contains": "/home"},
    {"question": "Which landing pages get the most conversions?",
     "expect_status": "answered", "expect_contains": "/signup"},
    {"question": "Which landing pages lost revenue last week?",
     "expect_status": "not_enough_data", "expect_contains": "Not enough data"},
]
