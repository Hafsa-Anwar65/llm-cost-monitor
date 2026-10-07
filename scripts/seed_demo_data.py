#!/usr/bin/env python
"""Fill the database with realistic SYNTHETIC traffic so the dashboard has something to show.

No API keys needed. Costs are computed from pricing.json, so the numbers are internally
consistent, but they are not real usage: don't screenshot these for a post without saying so.

    python scripts/seed_demo_data.py              # ~3,000 requests over 14 days
    python scripts/seed_demo_data.py --clear      # wipe existing rows first
    python scripts/seed_demo_data.py --days 30 --n 8000 --seed 7
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from proxy.db import Database  # noqa: E402
from proxy.pricing import PricingTable  # noqa: E402

USERS = {"alice": 0.32, "bob": 0.24, "carol": 0.18, "dave": 0.14, "eve": 0.08, "ci-bot": 0.04}
# feature -> (weight, mean input tokens, mean output tokens, model tier, stream probability)
FEATURES = {
    "chat-assistant": (0.46, 900, 320, "mid", 0.9),
    "doc-summarizer": (0.18, 7500, 650, "mid+big", 0.2),
    "code-review": (0.16, 3200, 1100, "big", 0.6),
    "classifier": (0.20, 280, 18, "cheap", 0.0),
}


def pick(weighted: dict, rng: random.Random):
    return rng.choices(list(weighted), weights=list(weighted.values()))[0]


def tiers(table: PricingTable) -> dict[str, list[str]]:
    models = sorted(
        (m for m in table.models() if "latest" not in m),
        key=lambda m: table.lookup(m)["input"],
    )
    # Keep the demo readable: six models in total (two cheap, two mid-range, two premium).
    n = len(models)
    mid_start = max(0, n // 2 - 1)
    cheap, mid, big = models[:2], models[mid_start: mid_start + 2], models[-2:]
    return {"cheap": cheap, "mid": mid, "big": big, "mid+big": mid + big}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.getenv("DB_PATH", "data/monitor.db"))
    ap.add_argument("--pricing", default=os.getenv("PRICING_PATH", "pricing.json"))
    ap.add_argument("--n", type=int, default=3000, help="number of requests")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--clear", action="store_true", help="delete existing rows first")
    ap.add_argument("--no-spike", action="store_true", help="skip the cost spike on day -2")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    table = PricingTable(args.pricing)
    if not table.models():
        sys.exit(f"No models found in {args.pricing}")
    tier = tiers(table)
    db = Database(args.db)
    if args.clear:
        db.clear_requests()

    now = datetime.now(timezone.utc)
    rows = []
    for _ in range(args.n):
        # Busier on weekdays and during working hours, gently growing over the period.
        while True:
            age = rng.random() ** 0.9 * args.days  # more recent traffic is slightly denser
            ts = now - timedelta(days=age)
            hour_weight = 0.25 + 0.75 * math.exp(-((ts.hour - 13) ** 2) / 40)
            weekday_weight = 0.45 if ts.weekday() >= 5 else 1.0
            if rng.random() < hour_weight * weekday_weight:
                break

        feature = pick({k: v[0] for k, v in FEATURES.items()}, rng)
        _, in_mean, out_mean, tier_name, p_stream = FEATURES[feature]
        user = pick(USERS, rng)

        # A runaway summarizer job two days ago: the kind of thing a cost monitor should catch.
        if not args.no_spike and 1.0 <= age <= 2.0 and feature == "doc-summarizer" and rng.random() < 0.7:
            in_mean *= 4.5

        model = rng.choice(tier[tier_name])
        provider = "openai" if model.startswith("gpt") else "anthropic"
        in_tok = max(5, int(rng.lognormvariate(math.log(in_mean), 0.55)))
        out_tok = max(1, int(rng.lognormvariate(math.log(out_mean), 0.5)))
        cache_read = int(in_tok * rng.uniform(0.3, 0.8)) if rng.random() < 0.25 else 0
        in_tok -= cache_read
        cache_write = int(in_tok * 0.3) if provider == "anthropic" and rng.random() < 0.05 else 0

        streamed = rng.random() < p_stream
        failed = rng.random() < 0.025
        status = rng.choice([429, 500, 529, 529]) if failed else 200
        if failed:
            in_tok = out_tok = cache_read = cache_write = 0
            latency = int(rng.uniform(80, 900))
            ttft = None
        else:
            base = 280 + out_tok * rng.uniform(5, 12) * (1.5 if tier_name == "big" else 1.0)
            latency = int(base * rng.lognormvariate(0, 0.25))
            if rng.random() < 0.015:  # occasional slow tail
                latency *= rng.randint(3, 6)
            ttft = int(min(latency * 0.9, rng.uniform(180, 700) * (1.6 if tier_name == "big" else 1.0))) if streamed else None

        cost, priced = table.cost(model, in_tok, out_tok, cache_read, cache_write)
        rows.append({
            "ts": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "provider": provider,
            "endpoint": "/v1/messages" if provider == "anthropic" else "/v1/chat/completions",
            "model": model,
            "user_tag": user,
            "feature_tag": feature,
            "streamed": int(streamed),
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cache_read_tokens": cache_read,
            "cache_write_tokens": cache_write,
            "cost_usd": cost,
            "priced": int(priced),
            "latency_ms": latency,
            "ttft_ms": ttft,
            "status_code": status,
            "error": {429: "rate limited", 500: "internal error", 529: "overloaded"}.get(status) if failed else None,
        })

    rows.sort(key=lambda r: r["ts"])
    db.insert_many(rows)
    total = sum(r["cost_usd"] for r in rows)
    print(f"Inserted {len(rows):,} synthetic requests into {args.db} (total ${total:,.2f}).")
    print("Open the dashboard:  http://localhost:8000/dashboard  (start the proxy first: uvicorn proxy.main:app)")


if __name__ == "__main__":
    main()
