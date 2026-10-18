"""Tests for the accuracy checks and the downloadable report."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from proxy.config import Settings
from proxy.main import create_app
from proxy.pricing import PricingTable
from proxy.report import accuracy

FMT = "%Y-%m-%d %H:%M:%S"
PRICES = '{"models": {"m1": {"input": 1.0, "output": 2.0}}}'


def row(**kw) -> dict:
    base = {
        "id": 1, "ts": (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(FMT),
        "provider": "anthropic", "endpoint": "/v1/messages", "model": "m1", "user_tag": "u1",
        "feature_tag": "chat", "streamed": 0, "input_tokens": 1_000_000, "output_tokens": 500_000,
        "cache_read_tokens": 0, "cache_write_tokens": 0, "cost_usd": 2.0, "priced": 1,
        "latency_ms": 100, "ttft_ms": None, "status_code": 200, "error": None,
    }
    base.update(kw)
    return base


def by_id(result: dict) -> dict:
    return {c["id"]: c for c in result["checks"]}


@pytest.fixture
def pricing(tmp_path):
    path = tmp_path / "pricing.json"
    path.write_text(PRICES)
    return PricingTable(path)


def test_clean_data_scores_100(pricing):
    result = accuracy([row(), row(id=2)], pricing)
    assert result["score"] == 100 and result["grade"] == "High"
    checks = by_id(result)
    assert checks["reconcile"]["status"] == "ok"
    assert checks["ttft"]["status"] == "na"  # no streams, so not scored


def test_problems_are_flagged(pricing):
    rows = [
        row(),
        row(id=2, input_tokens=0, output_tokens=0, cost_usd=0.0),           # usage missing
        row(id=3, model="mystery", priced=0, cost_usd=0.0),                 # no price
        row(id=4, cost_usd=3.0),                                            # cost drift (+$1)
        row(id=5, latency_ms=None, feature_tag=None),                       # no latency, untagged
        row(id=6, streamed=1, ttft_ms=None),                                # stream without TTFT
    ]
    checks = by_id(accuracy(rows, pricing))
    assert checks["usage"]["status"] == "fail" and "1 successful" in checks["usage"]["detail"]
    assert checks["priced"]["status"] == "fail" and "mystery" in checks["priced"]["detail"]
    assert checks["reconcile"]["status"] == "warn" and "$1.0000" in checks["reconcile"]["detail"]
    assert checks["latency"]["status"] == "fail"
    assert checks["ttft"]["status"] == "fail"
    assert checks["attribution"]["status"] == "warn"


def test_failed_requests_do_not_count_as_missing_usage(pricing):
    rows = [row(), row(id=2, status_code=529, input_tokens=0, output_tokens=0, cost_usd=0.0, latency_ms=None)]
    checks = by_id(accuracy(rows, pricing))
    assert checks["usage"]["status"] == "ok" and checks["latency"]["status"] == "ok"


@pytest.fixture
def client(tmp_path):
    (tmp_path / "pricing.json").write_text(PRICES)
    s = Settings(db_path=str(tmp_path / "r.db"), pricing_path=str(tmp_path / "pricing.json"))
    app = create_app(s, transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    with TestClient(app) as c:
        c.app.state.db.insert_many([
            {k: v for k, v in row().items() if k != "id"},
            {k: v for k, v in row(feature_tag="search|beta", cost_usd=3.0).items() if k != "id"},
        ])
        yield c


def test_dashboard_includes_accuracy(client):
    acc = client.get("/api/dashboard?range=7d").json()["accuracy"]
    assert acc["requests_checked"] == 2
    assert by_id(acc)["reconcile"]["status"] == "warn"


def test_markdown_report_download(client):
    res = client.get("/api/report?range=7d&format=md&feature=chat")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/markdown")
    assert 'filename="llm-report-7d-' in res.headers["content-disposition"]
    body = res.text
    assert "# LLM Cost & Latency Report" in body and "features: chat" in body
    assert "| Total spend | $2.00 |" in body and "## Accuracy checks" in body


def test_csv_report_download_and_escaping(client):
    res = client.get("/api/report?range=7d&format=csv&tz=Asia/Karachi")
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/csv")
    lines = res.text.strip().splitlines()
    assert lines[0].startswith("id,time_local,provider,model")
    assert len(lines) == 3 and "search|beta" in res.text


def test_report_rejects_bad_input(client):
    assert client.get("/api/report?format=pdf").status_code == 400
    assert client.get("/api/report?range=1y").status_code == 400
