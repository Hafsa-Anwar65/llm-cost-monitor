"""JSON API behind the React dashboard.

One endpoint, `GET /api/dashboard`, returns everything the page needs for a given
time range and filter set, so the UI makes a single request per refresh.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query, Request

from fastapi.responses import Response

from . import report
from .config import Settings
from .db import Database, utc_day
from .pricing import PricingTable

router = APIRouter(prefix="/api")

WINDOWS = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30), "all": None}
MAX_NAMED_SERIES = 8  # the chart palette has 8 validated hues; the rest fold into "Other"
UNTAGGED = "(untagged)"
TS_FORMAT = "%Y-%m-%d %H:%M:%S"
COLUMNS = (
    "id, ts, provider, model, user_tag, feature_tag, streamed, input_tokens, output_tokens, "
    "cache_read_tokens, cache_write_tokens, cost_usd, priced, latency_ms, ttft_ms, status_code, error"
)


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def percentile(sorted_values: list[float], q: float) -> float | None:
    """Linear-interpolated percentile of an already sorted list (q in 0..1)."""
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = (len(sorted_values) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return float(sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo))


def _tz(name: str) -> tuple[tzinfo, str]:
    try:
        return ZoneInfo(name), name
    except (ZoneInfoNotFoundError, ValueError, KeyError, OSError):
        return timezone.utc, "UTC"  # unknown zone, or no tz database installed (Windows without tzdata)


def _to_local(ts: str, tz: tzinfo) -> datetime:
    """UTC 'YYYY-MM-DD HH:MM:SS' -> naive datetime in the viewer's timezone."""
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc).astimezone(tz).replace(tzinfo=None)


def _bucket_start(dt: datetime, unit: str) -> datetime:
    dt = dt.replace(minute=0, second=0, microsecond=0)
    if unit == "hour":
        return dt
    dt = dt.replace(hour=0)
    if unit == "week":
        dt -= timedelta(days=dt.weekday())
    return dt


def _unit(range_key: str, first_local: datetime | None, now_local: datetime) -> str:
    if range_key == "24h":
        return "hour"
    if range_key in ("7d", "30d"):
        return "day"
    span_days = (now_local - first_local).days if first_local else 0
    return "hour" if span_days <= 2 else "day" if span_days <= 45 else "week"


def _bucket_range(start: datetime, end: datetime, unit: str) -> list[datetime]:
    step = {"hour": timedelta(hours=1), "day": timedelta(days=1), "week": timedelta(weeks=1)}[unit]
    out: list[datetime] = []
    cur = start
    while cur <= end and len(out) < 2000:
        out.append(cur)
        cur += step
    return out


def _where(since, until, providers, models, users, features) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    if since:
        clauses.append("ts >= ?")
        params.append(since)
    if until:
        clauses.append("ts < ?")
        params.append(until)
    # Column names are fixed literals; every value goes through a bound parameter.
    for column, values in (
        ("provider", providers), ("model", models), ("user_tag", users), ("feature_tag", features),
    ):
        if values:
            clauses.append(f"{column} IN ({','.join('?' * len(values))})")
            params.extend(values)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def _r6(x: float) -> float:
    return round(float(x), 6)


# ---------------------------------------------------------------------------
# the aggregation
# ---------------------------------------------------------------------------
def build_dashboard(
    db: Database,
    settings: Settings,
    *,
    range_key: str,
    tz_name: str,
    providers: list[str],
    models: list[str],
    users: list[str],
    features: list[str],
    pricing: PricingTable | None = None,
    with_rows: bool = False,
) -> dict:
    tz, tz_name = _tz(tz_name)
    now = datetime.now(timezone.utc)
    now_local = now.astimezone(tz).replace(tzinfo=None)
    window = WINDOWS[range_key]
    since = now - window if window else None

    where, params = _where(since.strftime(TS_FORMAT) if since else None, None, providers, models, users, features)
    rows = db.query(f"SELECT {COLUMNS} FROM requests{where} ORDER BY ts", params)

    prev_cost = None
    if window and since:
        pwhere, pparams = _where(
            (since - window).strftime(TS_FORMAT), since.strftime(TS_FORMAT), providers, models, users, features
        )
        prev_cost = _r6(db.query(f"SELECT COALESCE(SUM(cost_usd), 0) AS c FROM requests{pwhere}", pparams)[0]["c"])

    # Everything-ever lists: filter options, and a colour slot per model that never changes with filters.
    meta = {
        "models": [r[0] for r in db.query("SELECT model FROM requests WHERE model IS NOT NULL GROUP BY model ORDER BY MIN(id)")],
        "providers": [r[0] for r in db.query("SELECT DISTINCT provider FROM requests ORDER BY 1")],
        "users": [r[0] for r in db.query("SELECT DISTINCT user_tag FROM requests WHERE user_tag IS NOT NULL ORDER BY 1")],
        "features": [r[0] for r in db.query("SELECT DISTINCT feature_tag FROM requests WHERE feature_tag IS NOT NULL ORDER BY 1")],
    }
    slot_of = {m: i for i, m in enumerate(meta["models"][:MAX_NAMED_SERIES])}

    # --- one pass over the rows ------------------------------------------------
    locals_ = [_to_local(r["ts"], tz) for r in rows]
    unit = _unit(range_key, locals_[0] if locals_ else None, now_local)

    spend: dict[datetime, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    latency_by_bucket: dict[datetime, list[float]] = defaultdict(list)
    model_stats: dict[str, dict] = {}
    user_cost: dict[str, list] = defaultdict(lambda: [0.0, 0])
    feature_cost: dict[str, list] = defaultdict(lambda: [0.0, 0])
    # Requests by weekday (Mon=0) and three-hour block of the day, in the viewer's timezone.
    activity = [[0] * 8 for _ in range(7)]

    total_cost = in_tok = out_tok = cache_tok = 0.0
    ok_latencies: list[float] = []
    ok_ttfts: list[float] = []
    failed = 0
    unpriced_models: set[str] = set()
    unpriced_count = 0

    for r, local in zip(rows, locals_):
        model = r["model"] or "unknown"
        cost = r["cost_usd"] or 0.0
        is_failed = (r["status_code"] or 0) >= 400
        bucket = _bucket_start(local, unit)

        total_cost += cost
        in_tok += (r["input_tokens"] or 0) + (r["cache_read_tokens"] or 0) + (r["cache_write_tokens"] or 0)
        out_tok += r["output_tokens"] or 0
        cache_tok += (r["cache_read_tokens"] or 0) + (r["cache_write_tokens"] or 0)
        failed += is_failed
        activity[local.weekday()][local.hour // 3] += 1

        spend[bucket]["Other" if model not in slot_of else model] += cost

        ms = model_stats.setdefault(model, {"requests": 0, "cost": 0.0, "lat": [], "ttft": [], "failed": 0})
        ms["requests"] += 1
        ms["cost"] += cost
        ms["failed"] += is_failed

        if not is_failed and r["latency_ms"] is not None:
            ok_latencies.append(r["latency_ms"])
            latency_by_bucket[bucket].append(r["latency_ms"])
            ms["lat"].append(r["latency_ms"])
            if r["streamed"] and r["ttft_ms"] is not None:
                ok_ttfts.append(r["ttft_ms"])
                ms["ttft"].append(r["ttft_ms"])

        user_cost[r["user_tag"] or UNTAGGED][0] += cost
        user_cost[r["user_tag"] or UNTAGGED][1] += 1
        feature_cost[r["feature_tag"] or UNTAGGED][0] += cost
        feature_cost[r["feature_tag"] or UNTAGGED][1] += 1

        if r["priced"] == 0:
            unpriced_count += 1
            unpriced_models.add(model)

    ok_latencies.sort()
    ok_ttfts.sort()

    # --- time series (empty buckets included so gaps are visible) -------------------
    series_keys = [m for m in meta["models"][:MAX_NAMED_SERIES] if any(m in v for v in spend.values())]
    series = [{"key": m, "slot": slot_of[m]} for m in series_keys]
    if any("Other" in v for v in spend.values()):
        series.append({"key": "Other", "slot": None})

    if range_key == "all":
        first_bucket = _bucket_start(locals_[0], unit) if locals_ else None
    else:
        first_bucket = _bucket_start((since or now).astimezone(tz).replace(tzinfo=None), unit)
    buckets = _bucket_range(first_bucket, _bucket_start(now_local, unit), unit) if first_bucket else []

    spend_points, latency_points = [], []
    for b in buckets:
        values = {k: _r6(v) for k, v in spend.get(b, {}).items() if v}
        spend_points.append({"t": b.isoformat(timespec="seconds"), "values": values})
        lats = sorted(latency_by_bucket.get(b, []))
        latency_points.append({
            "t": b.isoformat(timespec="seconds"),
            "n": len(lats),
            "p50": percentile(lats, 0.50),
            "p95": percentile(lats, 0.95),
            "p99": percentile(lats, 0.99),
        })

    # --- tables ----------------------------------------------------------------------
    by_model = []
    for model, s in sorted(model_stats.items(), key=lambda kv: kv[1]["cost"], reverse=True):
        lat, ttft = sorted(s["lat"]), sorted(s["ttft"])
        by_model.append({
            "model": model, "requests": s["requests"], "cost": _r6(s["cost"]),
            "p50": percentile(lat, 0.50), "p95": percentile(lat, 0.95), "p99": percentile(lat, 0.99),
            "ttft_p50": percentile(ttft, 0.50),
            "error_rate": s["failed"] / s["requests"],
        })

    def shares(d: dict[str, list]) -> list[dict]:
        ranked = sorted(d.items(), key=lambda kv: kv[1][0], reverse=True)[:10]
        return [{"name": k, "cost": _r6(v[0]), "requests": v[1]} for k, v in ranked]

    def request_row(r, local: datetime) -> dict:
        return {
            "id": r["id"], "ts": local.strftime(TS_FORMAT), "provider": r["provider"],
            "model": r["model"], "user": r["user_tag"], "feature": r["feature_tag"],
            "input_tokens": r["input_tokens"], "output_tokens": r["output_tokens"],
            "cache_read_tokens": r["cache_read_tokens"], "cost": _r6(r["cost_usd"] or 0.0),
            "latency_ms": r["latency_ms"], "status": r["status_code"], "error": r["error"],
        }

    paired = list(zip(rows, locals_))
    top = sorted(paired, key=lambda p: p[0]["cost_usd"] or 0.0, reverse=True)[:15]
    fails = [p for p in reversed(paired) if (p[0]["status_code"] or 0) >= 400][:20]

    payload = {
        "range": range_key,
        "tz": tz_name,
        "bucket": unit,
        "generated_at": now.strftime(TS_FORMAT),
        "last_request_at": locals_[-1].strftime(TS_FORMAT) if locals_ else None,
        "summary": {
            "cost": _r6(total_cost),
            "prev_cost": prev_cost,
            "requests": len(rows),
            "input_tokens": int(in_tok),
            "output_tokens": int(out_tok),
            "cache_tokens": int(cache_tok),
            "p50": percentile(ok_latencies, 0.50),
            "p95": percentile(ok_latencies, 0.95),
            "p99": percentile(ok_latencies, 0.99),
            "ttft_p50": percentile(ok_ttfts, 0.50),
            "error_rate": (failed / len(rows)) if rows else 0.0,
        },
        "spend": {"series": series, "points": spend_points},
        "latency": latency_points,
        "by_model": by_model,
        "activity": activity,
        "by_user": shares(user_cost),
        "by_feature": shares(feature_cost),
        "top_requests": [request_row(r, l) for r, l in top],
        "failures": [request_row(r, l) for r, l in fails],
        "unpriced": {"count": unpriced_count, "models": sorted(unpriced_models)},
        "budget": {"limit": settings.daily_budget_usd, "today": _r6(db.spend_for_day(utc_day()))},
        "meta": meta,
        "accuracy": report.accuracy(rows, pricing),
    }
    if with_rows:
        payload["_rows"] = rows
        payload["_local"] = lambda ts: _to_local(ts, tz).strftime(TS_FORMAT)
    return payload


@router.get("/dashboard")
def dashboard(
    request: Request,
    range_key: str = Query("7d", alias="range"),
    tz: str = "UTC",
    provider: list[str] = Query(default=[]),
    model: list[str] = Query(default=[]),
    user: list[str] = Query(default=[]),
    feature: list[str] = Query(default=[]),
):
    if range_key not in WINDOWS:
        raise HTTPException(status_code=400, detail=f"range must be one of {', '.join(WINDOWS)}")
    return build_dashboard(
        request.app.state.db,
        request.app.state.settings,
        range_key=range_key,
        tz_name=tz,
        providers=provider,
        models=model,
        users=user,
        features=feature,
        pricing=getattr(request.app.state, "pricing", None),
    )


@router.get("/report")
def download_report(
    request: Request,
    format: str = "md",
    range_key: str = Query("7d", alias="range"),
    tz: str = "UTC",
    provider: list[str] = Query(default=[]),
    model: list[str] = Query(default=[]),
    user: list[str] = Query(default=[]),
    feature: list[str] = Query(default=[]),
):
    """The current view as a file: a Markdown report (`md`) or every request as CSV (`csv`)."""
    if range_key not in WINDOWS:
        raise HTTPException(status_code=400, detail=f"range must be one of {', '.join(WINDOWS)}")
    if format not in ("md", "csv"):
        raise HTTPException(status_code=400, detail="format must be md or csv")
    data = build_dashboard(
        request.app.state.db,
        request.app.state.settings,
        range_key=range_key,
        tz_name=tz,
        providers=provider,
        models=model,
        users=user,
        features=feature,
        pricing=getattr(request.app.state, "pricing", None),
        with_rows=True,
    )
    day = data["generated_at"][:10]
    if format == "csv":
        body = report.requests_csv(data["_rows"], data["_local"])
        media, name = "text/csv; charset=utf-8", f"llm-requests-{range_key}-{day}.csv"
    else:
        filters = {"providers": provider, "models": model, "users": user, "features": feature}
        body = report.markdown_report(data, filters)
        media, name = "text/markdown; charset=utf-8", f"llm-report-{range_key}-{day}.md"
    return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})
