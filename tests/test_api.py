"""Tests for the JSON API behind the React dashboard."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from proxy.config import Settings
from proxy.main import create_app

FMT = "%Y-%m-%d %H:%M:%S"


def ts(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) - delta).strftime(FMT)


def row(**kw) -> dict:
    base = {
        "ts": ts(timedelta(hours=1)), "provider": "anthropic", "endpoint": "/v1/messages",
        "model": "m1", "user_tag": None, "feature_tag": None, "streamed": 0,
        "input_tokens": 10, "output_tokens": 5, "cache_read_tokens": 0, "cache_write_tokens": 0,
        "cost_usd": 1.0, "priced": 1, "latency_ms": 100, "ttft_ms": None, "status_code": 200,
        "error": None,
    }
    base.update(kw)
    return base


@pytest.fixture
def make_app(tmp_path):
    def _make(**settings):
        (tmp_path / "pricing.json").write_text('{"models": {}}')
        s = Settings(db_path=str(tmp_path / "api.db"), pricing_path=str(tmp_path / "pricing.json"), **settings)
        app = create_app(s, transport=httpx.MockTransport(lambda r: httpx.Response(200)))
        return TestClient(app)

    return _make


def test_totals_percentiles_and_error_rate(make_app):
    with make_app() as client:
        db = client.app.state.db
        db.insert_many([row(latency_ms=v) for v in (100, 200, 300, 400, 500)]
                       + [row(status_code=500, latency_ms=50, cost_usd=0.0, error="boom")])
        data = client.get("/api/dashboard?range=7d").json()

    s = data["summary"]
    assert s["requests"] == 6 and s["cost"] == pytest.approx(5.0)
    assert s["error_rate"] == pytest.approx(1 / 6)
    assert s["p50"] == pytest.approx(300)  # failures are excluded from latency
    assert s["p95"] == pytest.approx(480)  # linear interpolation, matches pandas
    assert data["failures"][0]["error"] == "boom"
    assert data["by_model"][0]["model"] == "m1" and data["by_model"][0]["requests"] == 6


def test_filters_and_untagged_buckets(make_app):
    with make_app() as client:
        client.app.state.db.insert_many([
            row(model="a", user_tag="alice", feature_tag="chat", cost_usd=2.0),
            row(model="b", user_tag="bob", feature_tag=None, cost_usd=3.0, provider="openai"),
        ])
        everything = client.get("/api/dashboard").json()
        only_a = client.get("/api/dashboard?model=a").json()
        both_users = client.get("/api/dashboard?user=alice&user=bob").json()
        nothing = client.get("/api/dashboard?model=missing").json()

    assert everything["summary"]["cost"] == pytest.approx(5.0)
    assert {x["name"] for x in everything["by_feature"]} == {"chat", "(untagged)"}
    assert only_a["summary"]["cost"] == pytest.approx(2.0)
    assert both_users["summary"]["requests"] == 2
    assert nothing["summary"]["requests"] == 0 and nothing["summary"]["p50"] is None
    assert nothing["meta"]["models"] == ["a", "b"]  # filter options stay stable
    assert client is not None


def test_ranges_and_previous_period(make_app):
    with make_app() as client:
        client.app.state.db.insert_many([
            row(ts=ts(timedelta(days=1)), cost_usd=4.0),     # this week
            row(ts=ts(timedelta(days=10)), cost_usd=1.5),    # previous week
            row(ts=ts(timedelta(days=60)), cost_usd=9.0),    # long ago
        ])
        week = client.get("/api/dashboard?range=7d").json()["summary"]
        everything = client.get("/api/dashboard?range=all").json()["summary"]

    assert week["cost"] == pytest.approx(4.0) and week["prev_cost"] == pytest.approx(1.5)
    assert everything["cost"] == pytest.approx(14.5) and everything["prev_cost"] is None


def test_models_beyond_eight_fold_into_other(make_app):
    with make_app() as client:
        client.app.state.db.insert_many([row(model=f"model-{i}", cost_usd=1.0) for i in range(10)])
        spend = client.get("/api/dashboard?range=24h").json()["spend"]

    keys = [s["key"] for s in spend["series"]]
    assert keys[:8] == [f"model-{i}" for i in range(8)] and keys[-1] == "Other"
    assert [s["slot"] for s in spend["series"]] == [*range(8), None]
    assert sum(sum(p["values"].values()) for p in spend["points"]) == pytest.approx(10.0)


def test_unpriced_and_budget(make_app):
    with make_app(daily_budget_usd=10.0) as client:
        client.app.state.db.insert_many([
            row(model="ghost", priced=0, cost_usd=0.0),
            row(cost_usd=2.5),
        ])
        data = client.get("/api/dashboard").json()

    assert data["unpriced"] == {"count": 1, "models": ["ghost"]}
    assert data["budget"]["limit"] == 10.0 and data["budget"]["today"] == pytest.approx(2.5)


def test_timezone_shifts_day_buckets(make_app):
    # 22:30 UTC yesterday is already "today" in Karachi (UTC+5)
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).replace(hour=22, minute=30, second=0, microsecond=0)
    with make_app() as client:
        client.app.state.db.insert_many([row(ts=yesterday.strftime(FMT), cost_usd=7.0)])
        utc = client.get("/api/dashboard?range=7d&tz=UTC").json()
        pk = client.get("/api/dashboard?range=7d&tz=Asia/Karachi").json()
        bogus = client.get("/api/dashboard?range=7d&tz=Not/AZone").json()

    def day_with_spend(d):
        return next(p["t"] for p in d["spend"]["points"] if p["values"])[:10]

    assert day_with_spend(utc) == yesterday.strftime("%Y-%m-%d")
    assert day_with_spend(pk) == (yesterday + timedelta(days=1)).strftime("%Y-%m-%d")
    assert bogus["tz"] == "UTC"


def test_activity_counts_requests_by_weekday_and_block(make_app):
    with make_app() as client:
        client.app.state.db.insert_many([row() for _ in range(4)])
        grid = client.get("/api/dashboard?range=7d").json()["activity"]
    assert len(grid) == 7 and all(len(day) == 8 for day in grid)
    assert sum(sum(day) for day in grid) == 4


def test_bad_range_is_rejected(make_app):
    with make_app() as client:
        assert client.get("/api/dashboard?range=forever").status_code == 400


def test_empty_database_returns_a_valid_shape(make_app):
    with make_app() as client:
        data = client.get("/api/dashboard").json()
    assert data["summary"]["requests"] == 0 and data["meta"]["models"] == []
    assert data["by_model"] == [] and data["failures"] == []


def test_built_ui_is_served_when_present(make_app):
    if not Path("proxy/static/index.html").exists():
        pytest.skip("React UI not built (run `npm run build` in web/)")
    with make_app() as client:
        assert client.get("/dashboard/").status_code == 200
        assert client.get("/", follow_redirects=False).status_code in (302, 307)
