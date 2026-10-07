#!/usr/bin/env python
"""Send real, cheap requests THROUGH the proxy so the dashboard fills with live data.

This is the script to run while screen-recording the demo. It uses your own API keys
(from the environment) and tiny prompts / max 80 output tokens, so 50 calls cost cents.

    export ANTHROPIC_API_KEY=...        # and/or OPENAI_API_KEY=...
    export DEMO_ANTHROPIC_MODEL=<a cheap model you have access to>
    python scripts/demo_traffic.py --n 50
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from proxy.pricing import PricingTable  # noqa: E402

PROMPTS = [
    "Explain what a reverse proxy does in two sentences.",
    "Give me three names for a coffee shop run by robots.",
    "Summarize the plot of Cinderella in one sentence.",
    "What is the difference between latency and throughput?",
    "Write a haiku-style tip about writing unit tests.",
    "List two pros and two cons of microservices.",
    "Translate 'good morning, team' into French and Spanish.",
    "Why is the sky blue? Keep it under 40 words.",
]
USERS = ["alice", "bob", "carol", "dave"]
FEATURES = ["chat-assistant", "doc-summarizer", "code-review", "classifier"]


def call_anthropic(client: httpx.Client, proxy: str, key: str, model: str, prompt: str, stream: bool, tags: dict):
    body = {"model": model, "max_tokens": 80, "stream": stream,
            "messages": [{"role": "user", "content": prompt}]}
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01", **tags}
    return client.build_request("POST", f"{proxy}/anthropic/v1/messages", json=body, headers=headers)


def call_openai(client: httpx.Client, proxy: str, key: str, model: str, prompt: str, stream: bool, tags: dict):
    body = {"model": model, "max_completion_tokens": 80, "stream": stream,
            "messages": [{"role": "user", "content": prompt}]}
    headers = {"authorization": f"Bearer {key}", **tags}
    return client.build_request("POST", f"{proxy}/openai/v1/chat/completions", json=body, headers=headers)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--proxy", default="http://localhost:8000")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--delay", type=float, default=0.3, help="seconds between calls")
    ap.add_argument("--pricing", default=os.getenv("PRICING_PATH", "pricing.json"))
    args = ap.parse_args()

    targets = []  # (name, builder, key, model)
    if os.getenv("ANTHROPIC_API_KEY"):
        targets.append(("anthropic", call_anthropic, os.environ["ANTHROPIC_API_KEY"],
                        os.getenv("DEMO_ANTHROPIC_MODEL", "claude-haiku-5-5")))
    if os.getenv("OPENAI_API_KEY"):
        targets.append(("openai", call_openai, os.environ["OPENAI_API_KEY"],
                        os.getenv("DEMO_OPENAI_MODEL", "gpt-4o-mini")))
    if not targets:
        sys.exit("Set ANTHROPIC_API_KEY and/or OPENAI_API_KEY first. "
                 "(No keys? Use `python scripts/seed_demo_data.py` for synthetic data.)")

    table = PricingTable(args.pricing)
    for name, _, _, model in targets:
        if table.lookup(model) is None:
            print(f"warning: no price for {name} model '{model}' in {args.pricing}; "
                  "its cost will show as $0 (flagged 'unpriced') until you add it.")

    try:
        httpx.get(f"{args.proxy}/health", timeout=3).raise_for_status()
    except httpx.HTTPError as exc:
        sys.exit(f"Proxy not reachable at {args.proxy} ({exc}). Start it first.")

    ok = failed = 0
    with httpx.Client(timeout=120) as client:
        for i in range(1, args.n + 1):
            name, build, key, model = random.choice(targets)
            stream = random.random() < 0.5
            tags = {"x-user-tag": random.choice(USERS), "x-feature-tag": random.choice(FEATURES)}
            req = build(client, args.proxy, key, model, random.choice(PROMPTS), stream, tags)
            t0 = time.perf_counter()
            try:
                resp = client.send(req, stream=True)
                for _ in resp.iter_raw():  # drain the body (stream or not)
                    pass
                resp.close()
                status = resp.status_code
            except httpx.HTTPError as exc:
                status = f"ERR {type(exc).__name__}"
            ms = (time.perf_counter() - t0) * 1000
            good = status == 200
            ok += good
            failed += not good
            print(f"[{i:>3}/{args.n}] {name:<9} {'stream' if stream else 'plain ':<6} "
                  f"{tags['x-user-tag']:<6} {status} {ms:6.0f} ms")
            time.sleep(args.delay)

    print(f"\nDone: {ok} ok, {failed} failed. Open the dashboard: {args.proxy}/dashboard")


if __name__ == "__main__":
    main()
