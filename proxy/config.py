from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _float(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    return float(value)


@dataclass
class Settings:
    """Runtime configuration. Everything can be set through environment variables."""

    db_path: str = "data/monitor.db"
    pricing_path: str = "pricing.json"
    anthropic_base_url: str = "https://api.anthropic.com"
    openai_base_url: str = "https://api.openai.com"
    daily_budget_usd: float | None = None
    slack_webhook_url: str | None = None
    log_prompts: bool = False
    # OpenAI only reports usage on streamed chat completions if asked to.
    inject_openai_usage: bool = True
    request_timeout_s: float = 300.0

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        return cls(
            db_path=env.get("DB_PATH", "data/monitor.db"),
            pricing_path=env.get("PRICING_PATH", "pricing.json"),
            anthropic_base_url=env.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
            openai_base_url=env.get("OPENAI_BASE_URL", "https://api.openai.com"),
            daily_budget_usd=_float(env.get("DAILY_BUDGET_USD")),
            slack_webhook_url=(env.get("SLACK_WEBHOOK_URL") or None),
            log_prompts=_bool(env.get("LOG_PROMPTS"), False),
            inject_openai_usage=_bool(env.get("INJECT_OPENAI_USAGE"), True),
            request_timeout_s=float(env.get("REQUEST_TIMEOUT_S", "300")),
        )
