from __future__ import annotations

import logging

import httpx

from .config import Settings
from .db import Database, utc_day

log = logging.getLogger("llm_monitor.alerts")


async def send_webhook(url: str, message: str) -> None:
    """POST to a Slack-compatible webhook ("text") that also works for Discord ("content")."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json={"text": message, "content": message})
        resp.raise_for_status()


async def check_daily_budget(settings: Settings, db: Database) -> None:
    """Fire a one-per-day alert once today's (UTC) spend crosses DAILY_BUDGET_USD."""
    budget = settings.daily_budget_usd
    if not budget:
        return
    day = utc_day()
    spend = db.spend_for_day(day)
    if spend < budget:
        return
    if not db.claim_alert(day, "daily_budget"):
        return

    message = (
        f"LLM spend for {day} (UTC) is ${spend:,.2f}, "
        f"over the ${budget:,.2f} daily budget."
    )
    log.warning(message)
    if settings.slack_webhook_url:
        try:
            await send_webhook(settings.slack_webhook_url, message)
        except Exception as exc:  # alerts must never break the proxy
            log.error("budget webhook failed: %r", exc)
