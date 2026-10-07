# LinkedIn post kit

Fill in the **[brackets]** with YOUR real numbers from running the demo on your own usage.
Don't use the synthetic seed data for claims. If you screenshot it, say it's demo data.

## Hook options (pick one)

1. "I built a proxy that shows exactly where my LLM budget goes. Switching to it takes one line."
2. "Most teams can't answer: which feature burns the most tokens? So I built the thing that can."
3. "Found out [X%] of my LLM spend came from [one feature]. Here's the 400-line tool I built to see it."

## Post draft

> **[Hook]**
>
> LLM bills are a black box until the invoice arrives. So I built an **LLM cost & latency monitor**:
> a small proxy that logs tokens, cost, and latency for every request.
>
> **Adopting it is one line:** change `base_url`.
>
> What it tracks:
> • cost per request, model, user and feature
> • p50 / p95 / p99 latency and time-to-first-token for streams
> • error rate, most expensive calls, daily budget alerts
>
> What I learned building it:
> 1. **Streaming is the hard part.** You have to count tokens without delaying a single chunk.
>    Anthropic and OpenAI report usage in different places and different shapes.
> 2. **"First byte" isn't time-to-first-token.** I measure the first *content* delta instead.
> 3. **Monitoring must never break the app.** Logging failures are swallowed; unknown models are flagged instead of showing $0.
> 4. **[Your own finding: e.g. "Prompt caching cut input cost by X% on my summarizer."]**
>
> Stack: FastAPI · httpx · SQLite · React + TypeScript + Recharts · Docker. Tested end to end against a mocked upstream.
>
> Repo + demo in the comments 👇
>
> #LLM #AIEngineering #Python #FastAPI #MLOps #GenAI

## First comment

> Repo: **[GitHub link]**
> 30-second demo: **[link or attach]**
> Next up: a model router that sends easy prompts to cheaper models, and a semantic cache. Both built on the same logs.

## 30-45 second demo shot list

1. (0-5s) Terminal: one line changed: `base_url="http://localhost:8000/anthropic"`.
2. (5-15s) Run `python scripts/demo_traffic.py --n 50`; calls scroll by.
3. (15-35s) Dashboard with **Live refresh** on: spend ticking up, latency lines moving, per-feature bars appearing.
4. (35-45s) Click one expensive request, then end on the headline number and your real finding.

## Tips

- Lead the post with the result, not the stack. Put the repo in the first comment, not the post body.
- A short video beats screenshots. Record at 1080p, trim dead time, add captions (most people watch muted).
- Post a follow-up a week later (the router or the cache) to turn one post into a series.
