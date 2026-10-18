"""Accuracy checks and downloadable reports.

`accuracy()` answers one question: *can you trust the numbers on the dashboard?*
It looks at the same rows the dashboard shows and checks that usage was captured,
every model has a price, stored costs still match pricing.json, and latency was recorded.

`markdown_report()` and `requests_csv()` turn a dashboard payload into files you can
download, share or attach to a ticket.
"""

from __future__ import annotations

import csv
import io
import time
from typing import Iterable

from .pricing import PricingTable

# A stored cost "matches" a recomputed one when it is within this many dollars or this share.
COST_ABS_TOLERANCE = 0.000_001
COST_REL_TOLERANCE = 0.005
PRICING_STALE_DAYS = 90

POINTS = {"ok": 1.0, "warn": 0.5, "fail": 0.0}


def _pct(part: int, whole: int) -> float:
    return part / whole if whole else 1.0


def _fmt_pct(x: float) -> str:
    if 0 < x < 0.001:
        return "<0.1%"
    return f"{x * 100:.1f}%".replace(".0%", "%")


def _status(rate: float, ok: float, warn: float) -> str:
    return "ok" if rate >= ok else "warn" if rate >= warn else "fail"


def _check(cid: str, label: str, status: str, value: str, detail: str) -> dict:
    return {"id": cid, "label": label, "status": status, "value": value, "detail": detail}


def accuracy(rows: Iterable, pricing: PricingTable | None) -> dict:
    """Data-quality checks over request rows (sqlite3.Row or dict)."""
    rows = list(rows)
    total = len(rows)
    ok_rows = [r for r in rows if (r["status_code"] or 0) < 400]

    def tokens(r) -> int:
        return sum((r[k] or 0) for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"))

    checks: list[dict] = []

    # 1. Usage captured: a successful call with zero tokens means the provider's usage was not found.
    missing = [r for r in ok_rows if tokens(r) == 0]
    rate = _pct(len(ok_rows) - len(missing), len(ok_rows))
    checks.append(_check(
        "usage", "Token usage captured", _status(rate, 1.0, 0.95), _fmt_pct(rate),
        "Every successful request reported its token usage." if not missing else
        f"{len(missing):,} successful requests came back without token usage, so their cost is unknown. "
        "For OpenAI streams keep INJECT_OPENAI_USAGE=1.",
    ))

    # 2. Priced: tokens were used but the model has no entry in pricing.json.
    with_tokens = [r for r in rows if tokens(r) > 0]
    unpriced = [r for r in with_tokens if r["priced"] == 0]
    unpriced_models = sorted({r["model"] or "unknown" for r in unpriced})
    rate = _pct(len(with_tokens) - len(unpriced), len(with_tokens))
    checks.append(_check(
        "priced", "Every model has a price", _status(rate, 1.0, 0.95), _fmt_pct(rate),
        "All requests used a model listed in pricing.json." if not unpriced else
        f"{len(unpriced):,} requests count as $0 because these models have no price: {', '.join(unpriced_models)}.",
    ))

    # 3. Cost reconciliation: recompute each stored cost with today's pricing.json.
    drift_rows = 0
    drift_usd = 0.0
    verified = 0
    if pricing is not None:
        for r in with_tokens:
            if r["priced"] == 0:
                continue
            expected, priced_now = pricing.cost(
                r["model"], r["input_tokens"] or 0, r["output_tokens"] or 0,
                r["cache_read_tokens"] or 0, r["cache_write_tokens"] or 0,
            )
            if not priced_now:
                continue
            verified += 1
            stored = r["cost_usd"] or 0.0
            diff = stored - expected
            if abs(diff) > max(COST_ABS_TOLERANCE, COST_REL_TOLERANCE * abs(expected)):
                drift_rows += 1
                drift_usd += diff
    if pricing is None or verified == 0:
        checks.append(_check("reconcile", "Costs match pricing.json", "na", "n/a", "No priced requests to verify yet."))
    else:
        rate = _pct(verified - drift_rows, verified)
        checks.append(_check(
            "reconcile", "Costs match pricing.json", "ok" if drift_rows == 0 else "warn", _fmt_pct(rate),
            f"All {verified:,} stored costs were recomputed from token counts and match the current prices." if not drift_rows else
            f"{drift_rows:,} of {verified:,} stored costs differ from today's prices by ${abs(drift_usd):,.4f} in total "
            f"({'higher' if drift_usd > 0 else 'lower'} than now). Costs are fixed at request time, so this usually "
            "means pricing.json was edited after those requests.",
        ))

    # 4. Latency recorded on successful calls.
    no_latency = [r for r in ok_rows if r["latency_ms"] is None]
    rate = _pct(len(ok_rows) - len(no_latency), len(ok_rows))
    checks.append(_check(
        "latency", "Latency recorded", _status(rate, 1.0, 0.95), _fmt_pct(rate),
        "Every successful request has a measured response time." if not no_latency else
        f"{len(no_latency):,} successful requests have no response time.",
    ))

    # 5. Time-to-first-token on successful streams.
    streams = [r for r in ok_rows if r["streamed"]]
    if not streams:
        checks.append(_check("ttft", "First-token time on streams", "na", "n/a", "No streamed requests in this range."))
    else:
        no_ttft = [r for r in streams if r["ttft_ms"] is None]
        rate = _pct(len(streams) - len(no_ttft), len(streams))
        checks.append(_check(
            "ttft", "First-token time on streams", _status(rate, 0.98, 0.9), _fmt_pct(rate),
            f"Measured on all {len(streams):,} successful streams." if not no_ttft else
            f"{len(no_ttft):,} of {len(streams):,} streams ended without a content token (often tool-only or empty replies).",
        ))

    # 6. Attribution: can spend be traced back to a feature?
    tagged = sum(1 for r in rows if r["feature_tag"])
    rate = _pct(tagged, total)
    checks.append(_check(
        "attribution", "Spend traced to a feature", "ok" if rate >= 0.9 else "warn", _fmt_pct(rate),
        "Requests carry an X-Feature-Tag header, so spend can be traced to a feature." if rate >= 0.9 else
        f"{total - tagged:,} requests have no X-Feature-Tag header, so their spend can't be traced to a feature.",
    ))

    # 7. Pricing freshness: prices change, and stale prices make every cost wrong.
    age_days = None
    if pricing is not None and pricing.path is not None:
        try:
            age_days = int((time.time() - pricing.path.stat().st_mtime) // 86400)
        except OSError:
            age_days = None
    if age_days is None:
        checks.append(_check("pricing_age", "Prices up to date", "na", "n/a", "pricing.json was not found."))
    else:
        checks.append(_check(
            "pricing_age", "Prices up to date", "ok" if age_days <= PRICING_STALE_DAYS else "warn",
            f"{age_days} days old",
            "pricing.json was updated recently." if age_days <= PRICING_STALE_DAYS else
            f"pricing.json was last changed {age_days} days ago. Check each provider's pricing page.",
        ))

    scored = [c for c in checks if c["status"] in POINTS]
    score = round(100 * sum(POINTS[c["status"]] for c in scored) / len(scored)) if scored else 100
    return {
        "score": score,
        "grade": "High" if score >= 90 else "Medium" if score >= 70 else "Low",
        "checks": checks,
        "requests_checked": total,
    }


# ---------------------------------------------------------------------------
# downloadable files
# ---------------------------------------------------------------------------
RANGE_LABEL = {"24h": "last 24 hours", "7d": "last 7 days", "30d": "last 30 days", "all": "all time"}
STATUS_LABEL = {"ok": "Pass", "warn": "Check", "fail": "Fail", "na": "n/a"}


def _money(x: float) -> str:
    return f"${x:,.4f}" if abs(x) < 1 else f"${x:,.2f}"


def _ms(x: float | None) -> str:
    if x is None:
        return "n/a"
    return f"{x:,.0f} ms" if x < 1000 else f"{x / 1000:,.1f} s"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    def esc(cell: str) -> str:
        return str(cell).replace("|", "\\|")

    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(" --- " for _ in headers) + "|"]
    lines += ["| " + " | ".join(esc(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def markdown_report(data: dict, filters: dict[str, list[str]]) -> str:
    s = data["summary"]
    acc = data["accuracy"]
    active = [f"{k}: {', '.join(v)}" for k, v in filters.items() if v]

    out = [
        "# LLM Cost & Latency Report",
        "",
        f"- **Period:** {RANGE_LABEL.get(data['range'], data['range'])} (times in {data['tz']})",
        f"- **Generated:** {data['generated_at']} UTC",
        f"- **Filters:** {'; '.join(active) if active else 'none'}",
        f"- **Data accuracy:** {acc['score']}/100 ({acc['grade']})",
        "",
        "## Summary",
        "",
        _table(["Metric", "Value"], [
            ["Total spend", _money(s["cost"])],
            ["Previous period", _money(s["prev_cost"]) if s["prev_cost"] is not None else "n/a"],
            ["Requests", f"{s['requests']:,}"],
            ["Input tokens", f"{s['input_tokens']:,}"],
            ["Output tokens", f"{s['output_tokens']:,}"],
            ["Cached tokens", f"{s['cache_tokens']:,}"],
            ["Median latency (p50)", _ms(s["p50"])],
            ["Latency p95", _ms(s["p95"])],
            ["Latency p99", _ms(s["p99"])],
            ["First token, median", _ms(s["ttft_p50"])],
            ["Failed requests", _fmt_pct(s["error_rate"])],
        ]),
        "",
        "## Accuracy checks",
        "",
        _table(["Check", "Result", "Value", "Details"],
               [[c["label"], STATUS_LABEL[c["status"]], c["value"], c["detail"]] for c in acc["checks"]]),
        "",
        "## By model",
        "",
        _table(["Model", "Requests", "Cost", "Share", "p50", "p95", "Failed"], [
            [m["model"], f"{m['requests']:,}", _money(m["cost"]),
             _fmt_pct(m["cost"] / s["cost"]) if s["cost"] else "0%",
             _ms(m["p50"]), _ms(m["p95"]), _fmt_pct(m["error_rate"])]
            for m in data["by_model"]
        ]),
        "",
        "## By feature",
        "",
        _table(["Feature", "Requests", "Cost"],
               [[f["name"], f"{f['requests']:,}", _money(f["cost"])] for f in data["by_feature"]]),
        "",
        "## By user",
        "",
        _table(["User", "Requests", "Cost"],
               [[u["name"], f"{u['requests']:,}", _money(u["cost"])] for u in data["by_user"]]),
        "",
        "## Costliest requests",
        "",
        _table(["Time", "Model", "Feature", "Tokens in / out", "Latency", "Cost"], [
            [r["ts"], r["model"], r["feature"] or "-",
             f"{(r['input_tokens'] or 0) + (r['cache_read_tokens'] or 0):,} / {r['output_tokens'] or 0:,}",
             _ms(r["latency_ms"]), _money(r["cost"])]
            for r in data["top_requests"][:10]
        ]),
        "",
        "_Generated by LLM Cost & Latency Monitor. Costs are computed from provider-reported token "
        "counts and the prices in pricing.json at the time of each request._",
        "",
    ]
    return "\n".join(out)


CSV_COLUMNS = [
    "id", "ts", "provider", "model", "user_tag", "feature_tag", "streamed", "input_tokens",
    "output_tokens", "cache_read_tokens", "cache_write_tokens", "cost_usd", "priced",
    "latency_ms", "ttft_ms", "status_code", "error",
]


def requests_csv(rows: Iterable, local_ts) -> str:
    """Every request in the range, one row each. `local_ts` maps a UTC ts to the viewer's time."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["id", "time_local"] + CSV_COLUMNS[2:])
    for r in rows:
        w.writerow([r["id"], local_ts(r["ts"])] + [r[c] if r[c] is not None else "" for c in CSV_COLUMNS[2:]])
    return buf.getvalue()
