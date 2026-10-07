"""End-to-end tests: the real FastAPI app talking to a mocked upstream provider."""

import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from proxy import alerts
from proxy.config import Settings
from proxy.main import create_app

PRICING = {
    "models": {
        "claude-test": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75},
        "gpt-test": {"input": 2.5, "output": 10.0, "cache_read": 1.25},
    }
}


@pytest.fixture
def make_client(tmp_path):
    def _make(handler, **overrides):
        pricing = tmp_path / "pricing.json"
        pricing.write_text(json.dumps(PRICING))
        settings = Settings(
            db_path=str(tmp_path / "t.db"), pricing_path=str(pricing), **overrides
        )
        app = create_app(settings, transport=httpx.MockTransport(handler))
        return TestClient(app)

    return _make


def sse(*events) -> bytes:
    out = b""
    for name, data in events:
        if name:
            out += f"event: {name}\n".encode()
        out += f"data: {json.dumps(data)}\n\n".encode()
    return out


async def trickle(data: bytes, size: int = 7):
    """Yield the payload in tiny chunks so SSE lines get split across chunk boundaries."""
    for i in range(0, len(data), size):
        yield data[i : i + size]


ANTHROPIC_BODY = {
    "model": "claude-test-1",
    "max_tokens": 16,
    "messages": [{"role": "user", "content": "hi"}],
}


def test_anthropic_non_streaming(make_client):
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        return httpx.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "content": [{"type": "text", "text": "hello"}],
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 500,
                    "cache_read_input_tokens": 2000,
                    "cache_creation_input_tokens": 400,
                },
            },
        )

    with make_client(handler) as client:
        resp = client.post(
            "/anthropic/v1/messages",
            json=ANTHROPIC_BODY,
            headers={"x-api-key": "sk-secret", "x-user-tag": "alice", "x-feature-tag": "chat"},
        )
        assert resp.status_code == 200
        assert resp.json()["content"][0]["text"] == "hello"
        rows = client.app.state.db.all_requests()

    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    assert seen["headers"]["x-api-key"] == "sk-secret"  # key is passed through
    assert "x-user-tag" not in seen["headers"]  # tags are stripped before forwarding

    (row,) = rows
    assert (row["provider"], row["model"]) == ("anthropic", "claude-test-1")
    assert (row["user_tag"], row["feature_tag"]) == ("alice", "chat")
    assert (row["input_tokens"], row["output_tokens"]) == (1000, 500)
    assert (row["cache_read_tokens"], row["cache_write_tokens"]) == (2000, 400)
    assert row["cost_usd"] == pytest.approx(0.0126)  # (3000 + 7500 + 600 + 1500) / 1e6
    assert row["streamed"] == 0 and row["priced"] == 1 and row["status_code"] == 200
    assert row["latency_ms"] >= 0


def test_anthropic_streaming_with_ttft(make_client):
    payload = sse(
        ("message_start", {"type": "message_start", "message": {"id": "m", "usage": {"input_tokens": 25, "output_tokens": 1}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hel"}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "lo"}}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 42}}),
        ("message_stop", {"type": "message_stop"}),
    )

    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=trickle(payload))

    with make_client(handler) as client:
        resp = client.post("/anthropic/v1/messages", json={**ANTHROPIC_BODY, "stream": True})
        assert resp.content == payload  # relayed byte-for-byte
        (row,) = client.app.state.db.all_requests()

    assert row["streamed"] == 1
    assert (row["input_tokens"], row["output_tokens"]) == (25, 42)
    assert row["ttft_ms"] is not None and row["ttft_ms"] <= row["latency_ms"]
    assert row["cost_usd"] == pytest.approx((25 * 3 + 42 * 15) / 1e6)


def test_openai_streaming_injects_usage_option(make_client):
    captured = {}
    payload = (
        sse((None, {"choices": [{"delta": {"role": "assistant"}}]}))
        + sse((None, {"choices": [{"delta": {"content": "Hi"}}]}))
        + sse((None, {"choices": [], "usage": {"prompt_tokens": 100, "completion_tokens": 20, "prompt_tokens_details": {"cached_tokens": 40}}}))
        + b"data: [DONE]\n\n"
    )

    def handler(request: httpx.Request):
        captured["body"] = json.loads(request.content)
        captured["url"] = str(request.url)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=trickle(payload, 11))

    with make_client(handler) as client:
        resp = client.post(
            "/openai/v1/chat/completions",
            json={"model": "gpt-test-mini", "stream": True, "messages": []},
            headers={"authorization": "Bearer sk-x"},
        )
        assert resp.content == payload
        (row,) = client.app.state.db.all_requests()

    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["body"]["stream_options"] == {"include_usage": True}
    assert (row["input_tokens"], row["cache_read_tokens"], row["output_tokens"]) == (60, 40, 20)
    assert row["cost_usd"] == pytest.approx((60 * 2.5 + 20 * 10 + 40 * 1.25) / 1e6)
    assert row["ttft_ms"] is not None


def test_openai_responses_api_non_streaming(make_client):
    def handler(request):
        return httpx.Response(200, json={
            "id": "resp_1",
            "usage": {"input_tokens": 200, "output_tokens": 50, "input_tokens_details": {"cached_tokens": 100}},
        })

    with make_client(handler) as client:
        client.post("/openai/v1/responses", json={"model": "gpt-test", "input": "hi"})
        (row,) = client.app.state.db.all_requests()

    assert (row["input_tokens"], row["cache_read_tokens"], row["output_tokens"]) == (100, 100, 50)


def test_upstream_error_is_relayed_and_logged(make_client):
    def handler(request):
        return httpx.Response(429, json={"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}})

    with make_client(handler) as client:
        resp = client.post("/anthropic/v1/messages", json=ANTHROPIC_BODY)
        assert resp.status_code == 429
        (row,) = client.app.state.db.all_requests()

    assert row["status_code"] == 429 and "slow down" in row["error"]
    assert row["input_tokens"] == 0 and row["cost_usd"] == 0


def test_unreachable_upstream_returns_502(make_client):
    def handler(request):
        raise httpx.ConnectError("boom")

    with make_client(handler) as client:
        resp = client.post("/anthropic/v1/messages", json=ANTHROPIC_BODY)
        assert resp.status_code == 502
        (row,) = client.app.state.db.all_requests()

    assert row["status_code"] == 502 and "ConnectError" in row["error"]


def test_unpriced_model_is_flagged_not_silently_free(make_client):
    def handler(request):
        return httpx.Response(200, json={"usage": {"input_tokens": 10, "output_tokens": 5}})

    with make_client(handler) as client:
        client.post("/anthropic/v1/messages", json={**ANTHROPIC_BODY, "model": "mystery-model"})
        (row,) = client.app.state.db.all_requests()

    assert row["priced"] == 0 and row["cost_usd"] == 0 and row["input_tokens"] == 10


def test_count_tokens_and_get_requests_are_not_logged(make_client):
    def handler(request):
        return httpx.Response(200, json={"input_tokens": 123})

    with make_client(handler) as client:
        client.post("/anthropic/v1/messages/count_tokens", json=ANTHROPIC_BODY)
        client.get("/openai/v1/models")
        assert client.app.state.db.all_requests() == []


def test_user_falls_back_to_body_fields(make_client):
    def handler(request):
        return httpx.Response(200, json={"usage": {"input_tokens": 1, "output_tokens": 1}})

    with make_client(handler) as client:
        client.post("/anthropic/v1/messages", json={**ANTHROPIC_BODY, "metadata": {"user_id": "u-42"}})
        (row,) = client.app.state.db.all_requests()

    assert row["user_tag"] == "u-42" and row["feature_tag"] is None


def test_prompt_logging_is_off_by_default_and_opt_in(make_client):
    def handler(request):
        return httpx.Response(200, json={"usage": {"input_tokens": 1, "output_tokens": 1}})

    with make_client(handler) as client:
        client.post("/anthropic/v1/messages", json=ANTHROPIC_BODY)
        assert client.app.state.db.all_requests()[0]["prompt_preview"] is None

    with make_client(handler, log_prompts=True) as client:
        client.post("/anthropic/v1/messages", json=ANTHROPIC_BODY)
        # both clients share one DB file in this test, so look at the newest row
        assert "hi" in client.app.state.db.all_requests()[-1]["prompt_preview"]


def test_budget_alert_fires_once(make_client, monkeypatch):
    sent = []

    async def fake_webhook(url, message):
        sent.append((url, message))

    monkeypatch.setattr(alerts, "send_webhook", fake_webhook)

    def handler(request):
        return httpx.Response(200, json={"usage": {"input_tokens": 1000, "output_tokens": 500, "cache_read_input_tokens": 2000, "cache_creation_input_tokens": 400}})

    with make_client(handler, daily_budget_usd=0.01, slack_webhook_url="https://hooks.example/x") as client:
        for _ in range(2):  # each call costs $0.0126, so the first one crosses $0.01
            client.post("/anthropic/v1/messages", json=ANTHROPIC_BODY)
        deadline = time.time() + 3
        while not sent and time.time() < deadline:
            time.sleep(0.05)
        time.sleep(0.2)

    assert len(sent) == 1
    assert sent[0][0] == "https://hooks.example/x" and "daily budget" in sent[0][1]


def test_health(make_client):
    with make_client(lambda r: httpx.Response(200)) as client:
        assert client.get("/health").json()["status"] == "ok"
