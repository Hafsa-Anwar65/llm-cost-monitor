"""Extract token usage from Anthropic / OpenAI responses and SSE streams.

Everything is normalised to four counters:

    input_tokens        prompt tokens that were NOT served from cache
    output_tokens       generated tokens
    cache_read_tokens   prompt tokens read from cache
    cache_write_tokens  prompt tokens written to cache (Anthropic only)

Anthropic reports cache tokens separately from `input_tokens`; OpenAI reports cached
tokens as a subset of `prompt_tokens`. We subtract so the cost formula is uniform.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    found: bool = False


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def normalize_usage(raw: dict, provider: str) -> Usage:
    if not isinstance(raw, dict):
        return Usage()

    if "prompt_tokens" in raw:  # OpenAI chat completions / embeddings
        prompt = _int(raw.get("prompt_tokens"))
        cached = _int((raw.get("prompt_tokens_details") or {}).get("cached_tokens"))
        return Usage(
            input_tokens=max(prompt - cached, 0),
            output_tokens=_int(raw.get("completion_tokens")),
            cache_read_tokens=cached,
            found=True,
        )

    if provider == "openai":  # OpenAI Responses API
        total_in = _int(raw.get("input_tokens"))
        cached = _int((raw.get("input_tokens_details") or {}).get("cached_tokens"))
        return Usage(
            input_tokens=max(total_in - cached, 0),
            output_tokens=_int(raw.get("output_tokens")),
            cache_read_tokens=cached,
            found=True,
        )

    return Usage(  # Anthropic Messages API
        input_tokens=_int(raw.get("input_tokens")),
        output_tokens=_int(raw.get("output_tokens")),
        cache_read_tokens=_int(raw.get("cache_read_input_tokens")),
        cache_write_tokens=_int(raw.get("cache_creation_input_tokens")),
        found=True,
    )


def usage_from_response(provider: str, obj) -> Usage | None:
    """Usage from a complete (non-streamed) JSON response body."""
    if not isinstance(obj, dict):
        return None
    raw = obj.get("usage")
    if raw is None and isinstance(obj.get("response"), dict):
        raw = obj["response"].get("usage")
    if not isinstance(raw, dict):
        return None
    return normalize_usage(raw, provider)


def error_message(obj) -> str | None:
    """Pull a human-readable message out of a provider error body."""
    if not isinstance(obj, dict) or "error" not in obj:
        return None
    err = obj["error"]
    if isinstance(err, dict):
        return str(err.get("message") or err.get("type") or err)[:500]
    return str(err)[:500]


class SSEParser:
    """Incremental server-sent-events parser that tolerates arbitrary chunk boundaries."""

    def __init__(self) -> None:
        self._buf = b""

    def feed(self, chunk: bytes) -> list[dict]:
        self._buf += chunk
        parts = self._buf.split(b"\n")
        self._buf = parts.pop()  # last piece may be an incomplete line
        events: list[dict] = []
        for line in parts:
            line = line.strip()
            if not line.startswith(b"data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == b"[DONE]":
                continue
            try:
                obj = json.loads(payload)
            except ValueError:
                continue
            if isinstance(obj, dict):
                events.append(obj)
        return events


class StreamAccumulator:
    """Folds a stream of parsed SSE events into usage, first-token and error info."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        self.usage = Usage()
        self.saw_content = False
        self.error: str | None = None

    def feed(self, event: dict) -> None:
        etype = event.get("type")
        if etype == "error":
            self.error = error_message(event) or "stream error"
            return
        if self.provider == "anthropic":
            self._anthropic(event, etype)
        else:
            self._openai(event, etype)

    # -- Anthropic: usage arrives in message_start (input) and message_delta (output)
    def _anthropic(self, event: dict, etype) -> None:
        if etype == "message_start":
            raw = (event.get("message") or {}).get("usage")
            if isinstance(raw, dict):
                self._merge(raw)
        elif etype == "message_delta":
            raw = event.get("usage")
            if isinstance(raw, dict):
                self._merge(raw)
        elif etype == "content_block_delta":
            self.saw_content = True

    def _merge(self, raw: dict) -> None:
        # Counters are cumulative, so keep the max of whatever each event reports.
        u = self.usage
        u.found = True
        for attr, key in (
            ("input_tokens", "input_tokens"),
            ("output_tokens", "output_tokens"),
            ("cache_read_tokens", "cache_read_input_tokens"),
            ("cache_write_tokens", "cache_creation_input_tokens"),
        ):
            value = raw.get(key)
            if value is not None:
                setattr(u, attr, max(getattr(u, attr), _int(value)))

    # -- OpenAI: usage in the final chunk (chat) or response.completed (Responses API)
    def _openai(self, event: dict, etype) -> None:
        raw = event.get("usage")
        if raw is None and isinstance(event.get("response"), dict):
            raw = event["response"].get("usage")
        if isinstance(raw, dict):
            self.usage = normalize_usage(raw, "openai")

        if etype == "response.output_text.delta":
            self.saw_content = True
        else:
            for choice in event.get("choices") or []:
                delta = (choice or {}).get("delta") or {}
                if delta.get("content") or delta.get("tool_calls"):
                    self.saw_content = True
