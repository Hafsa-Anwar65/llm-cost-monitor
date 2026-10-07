"""FastAPI proxy that forwards to Anthropic / OpenAI and logs tokens, cost and latency.

Point your SDK's base URL at this server and nothing else changes:

    Anthropic:  base_url="http://localhost:8000/anthropic"
    OpenAI:     base_url="http://localhost:8000/openai/v1"

Attribution is optional: send `X-User-Tag` and `X-Feature-Tag` headers.
API keys are forwarded as-is and are never stored or logged.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import anyio
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, alerts, api
from .config import Settings
from .db import Database, utc_now_str
from .pricing import PricingTable
from .usage import (
    SSEParser,
    StreamAccumulator,
    Usage,
    error_message,
    usage_from_response,
)

log = logging.getLogger("llm_monitor")

UI_DIR = Path(__file__).parent / "static"  # built React dashboard (see web/)

# Headers that must not be copied between the client, us, and the upstream.
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te",
    "trailers", "transfer-encoding", "upgrade", "host", "content-length",
    "content-encoding", "accept-encoding",
}
TAG_HEADERS = {"x-user-tag", "x-feature-tag"}
# Endpoints that mention a model but are free / carry no billable usage.
SKIP_LOG_SUFFIXES = ("count_tokens",)
METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]


@dataclass
class Call:
    provider: str
    path: str
    model: str | None
    user: str | None
    feature: str | None
    streamed: bool
    loggable: bool
    prompt_preview: str | None
    t0: float


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _forward_headers(headers) -> dict[str, str]:
    out = {
        k: v for k, v in headers.items()
        if k.lower() not in HOP_BY_HOP and k.lower() not in TAG_HEADERS
    }
    out["accept-encoding"] = "identity"  # keep bodies uncompressed so we can parse them
    return out


def _response_headers(headers) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP}


def _tags(headers, parsed) -> tuple[str | None, str | None]:
    user = headers.get("x-user-tag")
    feature = headers.get("x-feature-tag")
    if not user and isinstance(parsed, dict):  # fall back to fields the SDKs already send
        meta = parsed.get("metadata")
        if isinstance(meta, dict) and meta.get("user_id"):
            user = str(meta["user_id"])
        elif parsed.get("user"):
            user = str(parsed["user"])
    return (user[:128] if user else None), (feature[:128] if feature else None)


def _prompt_preview(parsed) -> str | None:
    if not isinstance(parsed, dict):
        return None
    content = parsed.get("messages") or parsed.get("input") or parsed.get("prompt")
    if content is None:
        return None
    return json.dumps(content, ensure_ascii=False)[:2000]


def _spawn(app: FastAPI, coro) -> None:
    try:
        task = asyncio.get_running_loop().create_task(coro)
    except RuntimeError:
        coro.close()
        return
    app.state.tasks.add(task)
    task.add_done_callback(app.state.tasks.discard)


def record(
    app: FastAPI,
    call: Call,
    *,
    status: int,
    error: str | None = None,
    usage: Usage | None = None,
    first_token_at: float | None = None,
) -> None:
    """Write one row. Never raises: logging must not break the caller's request."""
    if not call.loggable:
        return
    try:
        now = time.perf_counter()
        latency_ms = int((now - call.t0) * 1000)
        ttft_ms = int((first_token_at - call.t0) * 1000) if first_token_at else None
        u = usage or Usage()
        cost, priced = app.state.pricing.cost(
            call.model, u.input_tokens, u.output_tokens, u.cache_read_tokens, u.cache_write_tokens
        )
        app.state.db.insert_request({
            "ts": utc_now_str(),
            "provider": call.provider,
            "endpoint": "/" + call.path.lstrip("/"),
            "model": call.model or "unknown",
            "user_tag": call.user,
            "feature_tag": call.feature,
            "streamed": int(call.streamed),
            "input_tokens": u.input_tokens,
            "output_tokens": u.output_tokens,
            "cache_read_tokens": u.cache_read_tokens,
            "cache_write_tokens": u.cache_write_tokens,
            "cost_usd": cost,
            "priced": int(priced),
            "latency_ms": latency_ms,
            "ttft_ms": ttft_ms,
            "status_code": status,
            "error": error,
            "prompt_preview": call.prompt_preview,
        })
        log.info(
            "%s %s %s -> %s in=%d out=%d cache=%d/%d $%.5f %dms%s",
            call.provider, call.model, call.path, status,
            u.input_tokens, u.output_tokens, u.cache_read_tokens, u.cache_write_tokens,
            cost, latency_ms, "" if ttft_ms is None else f" ttft={ttft_ms}ms",
        )
        if app.state.settings.daily_budget_usd:
            _spawn(app, alerts.check_daily_budget(app.state.settings, app.state.db))
    except Exception:
        log.exception("failed to record request")


# ---------------------------------------------------------------------------
# core forwarding logic
# ---------------------------------------------------------------------------
async def forward(request: Request, provider: str, path: str):
    app = request.app
    settings: Settings = app.state.settings
    client: httpx.AsyncClient = app.state.client

    base = settings.anthropic_base_url if provider == "anthropic" else settings.openai_base_url
    url = f"{base.rstrip('/')}/{path.lstrip('/')}"
    if request.url.query:
        url += f"?{request.url.query}"

    body = await request.body()
    parsed = None
    if body and "json" in request.headers.get("content-type", "").lower():
        try:
            parsed = json.loads(body)
        except ValueError:
            parsed = None

    is_dict = isinstance(parsed, dict)
    model = parsed.get("model") if is_dict else None
    streamed = bool(parsed.get("stream")) if is_dict else False

    # OpenAI only emits token usage on a stream if we ask for it.
    if (
        provider == "openai" and streamed and settings.inject_openai_usage
        and path.rstrip("/").endswith("chat/completions")
    ):
        opts = parsed.get("stream_options")
        if not isinstance(opts, dict):
            opts = {}
        if "include_usage" not in opts:
            opts["include_usage"] = True
            parsed["stream_options"] = opts
            body = json.dumps(parsed).encode()

    user, feature = _tags(request.headers, parsed)
    call = Call(
        provider=provider,
        path=path,
        model=model if isinstance(model, str) else None,
        user=user,
        feature=feature,
        streamed=streamed,
        loggable=(
            request.method == "POST" and is_dict
            and not path.rstrip("/").endswith(SKIP_LOG_SUFFIXES)
        ),
        prompt_preview=_prompt_preview(parsed) if settings.log_prompts else None,
        t0=time.perf_counter(),
    )

    upstream_req = client.build_request(
        request.method, url, headers=_forward_headers(request.headers), content=body or None
    )

    try:
        upstream = await client.send(upstream_req, stream=True)
    except httpx.HTTPError as exc:
        return _bad_gateway(app, call, exc)

    resp_headers = _response_headers(upstream.headers)
    content_type = upstream.headers.get("content-type", "")

    if "text/event-stream" in content_type:
        return StreamingResponse(
            _stream(app, call, upstream),
            status_code=upstream.status_code,
            headers=resp_headers,
        )

    try:
        content = await upstream.aread()
    except httpx.HTTPError as exc:
        await upstream.aclose()
        return _bad_gateway(app, call, exc)
    await upstream.aclose()

    usage, error = None, None
    if call.loggable:
        try:
            obj = json.loads(content)
        except ValueError:
            obj = None
        usage = usage_from_response(provider, obj)
        if upstream.status_code >= 400:
            error = error_message(obj) or f"HTTP {upstream.status_code}"
    record(app, call, status=upstream.status_code, usage=usage, error=error)

    return Response(content=content, status_code=upstream.status_code, headers=resp_headers)


def _bad_gateway(app: FastAPI, call: Call, exc: Exception) -> JSONResponse:
    message = f"{type(exc).__name__}: {exc}"[:500]
    record(app, call, status=502, error=message)
    return JSONResponse(
        {"type": "error", "error": {"type": "proxy_error", "message": f"Upstream request failed: {message}"}},
        status_code=502,
    )


async def _stream(app: FastAPI, call: Call, upstream: httpx.Response):
    """Relay the SSE stream chunk by chunk while tallying usage on the side."""
    parser = SSEParser()
    acc = StreamAccumulator(call.provider)
    first_token_at: float | None = None
    completed = False
    error: str | None = None
    try:
        async for chunk in upstream.aiter_raw():
            if call.loggable and chunk:
                for event in parser.feed(chunk):
                    acc.feed(event)
                    if first_token_at is None and acc.saw_content:
                        first_token_at = time.perf_counter()
            yield chunk
        completed = True
    except Exception as exc:
        error = f"stream interrupted: {type(exc).__name__}: {exc}"[:500]
        raise
    finally:
        if not completed and error is None:
            error = "stream aborted (client disconnected)"
        error = acc.error or error
        if upstream.status_code >= 400 and not error:
            error = f"HTTP {upstream.status_code}"
        record(
            app, call,
            status=upstream.status_code,
            usage=acc.usage if acc.usage.found else None,
            error=error,
            first_token_at=first_token_at,
        )
        with anyio.CancelScope(shield=True):
            try:
                await upstream.aclose()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# app factory
# ---------------------------------------------------------------------------
def create_app(
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.request_timeout_s, connect=10.0),
            transport=transport,
        )
        log.info(
            "LLM Cost Monitor %s ready: db=%s, %d priced models, daily budget=%s",
            __version__, settings.db_path, len(app.state.pricing.models()),
            settings.daily_budget_usd or "off",
        )
        yield
        await app.state.client.aclose()

    app = FastAPI(
        title="LLM Cost Monitor", version=__version__, lifespan=lifespan,
        docs_url=None, redoc_url=None, openapi_url=None,
    )
    app.state.settings = settings
    app.state.db = Database(settings.db_path)
    app.state.pricing = PricingTable(settings.pricing_path)
    app.state.tasks = set()

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "llm-cost-monitor", "version": __version__}

    @app.get("/", include_in_schema=False)
    async def root():
        if UI_DIR.joinpath("index.html").exists():
            return RedirectResponse("/dashboard/")
        return {"status": "ok", "service": "llm-cost-monitor", "version": __version__}

    app.include_router(api.router)
    if UI_DIR.joinpath("index.html").exists():  # the built React dashboard
        app.mount("/dashboard", StaticFiles(directory=UI_DIR, html=True), name="dashboard")

    @app.api_route("/anthropic/{path:path}", methods=METHODS)
    async def anthropic_proxy(path: str, request: Request):
        return await forward(request, "anthropic", path)

    @app.api_route("/openai/{path:path}", methods=METHODS)
    async def openai_proxy(path: str, request: Request):
        return await forward(request, "openai", path)

    # Convenience aliases so a bare base URL (http://localhost:8000) also works.
    @app.post("/v1/messages")
    async def alias_messages(request: Request):
        return await forward(request, "anthropic", "v1/messages")

    @app.post("/v1/chat/completions")
    async def alias_chat(request: Request):
        return await forward(request, "openai", "v1/chat/completions")

    @app.post("/v1/responses")
    async def alias_responses(request: Request):
        return await forward(request, "openai", "v1/responses")

    return app


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
app = create_app()
