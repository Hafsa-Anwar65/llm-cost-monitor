# Design notes

Short answers to "why did you build it this way?", useful for the README, a blog post, or an interview.

## Why a proxy instead of an SDK wrapper?

A proxy works with any language and any SDK, needs no code changes beyond the base URL, and
sees exactly what goes over the wire. The cost is one extra network hop and one more service to run.

## Streaming

The hard part is measuring a stream without slowing it down. The proxy yields every chunk to the
client immediately; a small incremental SSE parser (tolerant of chunk boundaries splitting a line)
feeds a per-provider accumulator. The row is written in a `finally` block so it is recorded even when
the client disconnects mid-stream. TTFT is the time to the first content delta, because Anthropic sends
a `message_start` event almost instantly, so "first byte" would flatter the numbers.

## Token accounting

| | Anthropic | OpenAI |
|---|---|---|
| Uncached input | `input_tokens` | `prompt_tokens - cached_tokens` |
| Cache read | `cache_read_input_tokens` | `prompt_tokens_details.cached_tokens` |
| Cache write | `cache_creation_input_tokens` | n/a |
| Output | `output_tokens` | `completion_tokens` / `output_tokens` |

Everything is normalised into four counters so cost is one formula.
Streaming counters are cumulative, so the accumulator keeps the max seen and a late zero can never reset it.

## Failure philosophy

Monitoring must never take down production. Logging is wrapped so an exception is logged and swallowed;
an unreachable upstream becomes a clean 502 (and is itself logged); unknown models are flagged
`priced = 0` rather than silently costing $0.

## Dashboard design

The dashboard is a React + TypeScript + Recharts app (`web/`) that reads one JSON endpoint,
`GET /api/dashboard`. The server does the filtering (parameterised SQL), the percentiles and the time
bucketing in the viewer's timezone, so the browser only draws.

- **Colour follows the model, never its rank.** Each model keeps its hue as filters change (assigned in
  first-seen order). Only the first 8 models get a hue; beyond that, the tail folds into a gray "Other".
- The look is a dark, near-black canvas with violet and lime accents (light theme available). Model hues are
  fixed per model; because several are close in lightness, every chart has a legend and a table view, so
  colour is never the only way to identify a model.
- Layout: pill navigation, a big total with the split by model beside it, key figures, then rounded cards
  (spend, activity heatmap by weekday and time, latency, costliest requests, per-model table, user, feature, failures).
- The page opens with a plain-language sentence (what was spent, what changed, who or what drove it)
  followed by the key figures; charts come after.
- One filter row above everything it scopes. Single-series charts (spend by user / feature) use one colour,
  because the labels already carry identity. Percentiles use successful requests only, so fast failures don't flatter latency.
- No dual axes anywhere: spend and latency are separate charts.
- Live refresh polls every 5 seconds and keeps the previous data on screen while refetching.
- The production build is committed in `proxy/static/` and served by FastAPI, so running it needs only Python.

## Testing approach

The real FastAPI app is exercised end to end against a mocked upstream (`httpx.MockTransport`), including
SSE payloads deliberately trickled in 7-byte chunks. Beyond the unit tests, the proxy was also smoke-tested over real sockets against a
slow fake streaming upstream to confirm that bytes arrive progressively rather than being buffered.

The dashboard API has its own tests (`tests/test_api.py`): filters, percentiles, bucketing, budget and the served UI.
The UI itself was checked in a real browser in light, dark and mobile layouts.
