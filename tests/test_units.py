import json
import os

import pytest

from proxy.pricing import PricingTable
from proxy.usage import SSEParser, StreamAccumulator, normalize_usage


def test_pricing_longest_prefix_wins():
    table = PricingTable(models={
        "gpt-4o": {"input": 2.5, "output": 10},
        "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    })
    assert table.lookup("gpt-4o-mini-2024-07-18")["input"] == 0.15
    assert table.lookup("gpt-4o-2024-08-06")["input"] == 2.5
    assert table.lookup("nope") is None


def test_pricing_default_cache_multipliers():
    table = PricingTable(models={"m": {"input": 10, "output": 20}})
    cost, priced = table.cost("m", 0, 0, cache_read_tokens=1_000_000, cache_write_tokens=1_000_000)
    assert priced and cost == pytest.approx(1.0 + 12.5)


def test_pricing_hot_reload(tmp_path):
    path = tmp_path / "pricing.json"
    path.write_text(json.dumps({"models": {"a": {"input": 1, "output": 1}}}))
    table = PricingTable(path)
    assert table.lookup("a")["input"] == 1

    path.write_text(json.dumps({"models": {"a": {"input": 7, "output": 1}}}))
    stat = path.stat()
    os.utime(path, (stat.st_atime, stat.st_mtime + 5))
    assert table.lookup("a")["input"] == 7


def test_pricing_keeps_last_good_table_on_bad_json(tmp_path):
    path = tmp_path / "pricing.json"
    path.write_text(json.dumps({"models": {"a": {"input": 1, "output": 1}}}))
    table = PricingTable(path)
    path.write_text("{ not json")
    stat = path.stat()
    os.utime(path, (stat.st_atime, stat.st_mtime + 5))
    assert table.lookup("a")["input"] == 1


def test_zero_token_unknown_model_is_not_flagged():
    assert PricingTable(models={}).cost("whatever", 0, 0) == (0.0, True)


def test_sse_parser_handles_split_lines_and_done():
    parser = SSEParser()
    data = b'event: x\ndata: {"a": 1}\n\ndata: {"b": 2}\n\ndata: [DONE]\n\n'
    events = []
    for i in range(0, len(data), 3):
        events += parser.feed(data[i : i + 3])
    assert events == [{"a": 1}, {"b": 2}]


def test_normalize_openai_subtracts_cached_from_prompt():
    u = normalize_usage({"prompt_tokens": 100, "completion_tokens": 5, "prompt_tokens_details": {"cached_tokens": 30}}, "openai")
    assert (u.input_tokens, u.cache_read_tokens, u.output_tokens) == (70, 30, 5)


def test_normalize_anthropic_keeps_cache_separate():
    u = normalize_usage({"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 90, "cache_creation_input_tokens": 3}, "anthropic")
    assert (u.input_tokens, u.cache_read_tokens, u.cache_write_tokens) == (10, 90, 3)


def test_anthropic_stream_never_goes_backwards():
    acc = StreamAccumulator("anthropic")
    acc.feed({"type": "message_start", "message": {"usage": {"input_tokens": 50, "output_tokens": 1}}})
    acc.feed({"type": "message_delta", "usage": {"output_tokens": 30, "input_tokens": None}})
    acc.feed({"type": "message_delta", "usage": {"output_tokens": 0}})  # stale/zero must not reset
    assert (acc.usage.input_tokens, acc.usage.output_tokens) == (50, 30)


def test_stream_error_event_is_captured():
    acc = StreamAccumulator("anthropic")
    acc.feed({"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}})
    assert acc.error == "Overloaded"
