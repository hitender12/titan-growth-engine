"""Generate the synthetic sample dataset (clearly labelled synthetic).

42 days ending 2026-11-11, five landing pages, four sources, realistic
funnel ratios (impressions > clicks > sessions > conversions) with weekly
seasonality (weekends run at ~60%) and a slight upward trend.

Injected anomalies (the demo and eval set rely on these):
- /pricing organic clicks drop to ~30% of normal for the last 7 days.
- /signup conversions drop to ~30% of normal for the last 7 days.

Deterministic: seeded RNG, so the file is reproducible.
Run:  python3 tools/gen_sample.py
"""
import csv
import random
from datetime import date, timedelta

SEED = 42
END = date(2026, 11, 11)
DAYS = 42
PAGES = ["/home", "/pricing", "/features", "/blog", "/signup"]
SOURCES = ["organic", "paid", "social", "email"]

# Base daily impressions per page/source (before seasonality/noise).
BASE = {
    ("/home", "organic"): 2400, ("/home", "paid"): 1800, ("/home", "social"): 900, ("/home", "email"): 500,
    ("/pricing", "organic"): 1500, ("/pricing", "paid"): 1200, ("/pricing", "social"): 500, ("/pricing", "email"): 300,
    ("/features", "organic"): 1100, ("/features", "paid"): 700, ("/features", "social"): 400, ("/features", "email"): 200,
    ("/blog", "organic"): 2000, ("/blog", "paid"): 400, ("/blog", "social"): 800, ("/blog", "email"): 150,
    ("/signup", "organic"): 600, ("/signup", "paid"): 900, ("/signup", "social"): 300, ("/signup", "email"): 400,
}

CTR = {"organic": 0.06, "paid": 0.09, "social": 0.04, "email": 0.12}
SESSION_RATE = 0.85          # sessions per click
CONV_RATE = {"/signup": 0.10, "/pricing": 0.05, "/home": 0.02, "/features": 0.03, "/blog": 0.01}
CPC = {"paid": 1.40}         # spend per paid click (USD)


def gen(path):
    rng = random.Random(SEED)
    rows = []
    start = END - timedelta(days=DAYS - 1)
    for i in range(DAYS):
        day = start + timedelta(days=i)
        weekend = 0.6 if day.weekday() >= 5 else 1.0
        trend = 1.0 + 0.004 * i  # slow growth
        last_week = i >= DAYS - 7
        for page in PAGES:
            for source in SOURCES:
                impressions = int(BASE[(page, source)] * weekend * trend * rng.uniform(0.9, 1.1))
                clicks = int(impressions * CTR[source] * rng.uniform(0.9, 1.1))
                sessions = int(clicks * SESSION_RATE * rng.uniform(0.9, 1.05))
                conversions = int(sessions * CONV_RATE[page] * rng.uniform(0.8, 1.2))
                if last_week and page == "/pricing" and source == "organic":
                    clicks = int(clicks * 0.30)
                    sessions = int(sessions * 0.30)
                    conversions = int(conversions * 0.30)
                if last_week and page == "/signup":
                    conversions = int(conversions * 0.30)
                for metric, value in (
                    ("impressions", impressions),
                    ("clicks", clicks),
                    ("sessions", sessions),
                    ("conversions", conversions),
                ):
                    rows.append({
                        "timestamp": day.isoformat(),
                        "source": source,
                        "metric": metric,
                        "landing_page": page,
                        "value": value,
                        "unit": "count",
                        "currency": "USD",
                        "timezone": "UTC",
                        "attribution_window": "7d_click",
                    })
                if source == "paid":
                    rows.append({
                        "timestamp": day.isoformat(),
                        "source": source,
                        "metric": "spend",
                        "landing_page": page,
                        "value": round(clicks * CPC["paid"] * rng.uniform(0.95, 1.05), 2),
                        "unit": "USD",
                        "currency": "USD",
                        "timezone": "UTC",
                        "attribution_window": "7d_click",
                    })
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "timestamp", "source", "metric", "landing_page", "value",
            "unit", "currency", "timezone", "attribution_window",
        ])
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {path}")


if __name__ == "__main__":
    gen("sample-data/sample_metrics.csv")
