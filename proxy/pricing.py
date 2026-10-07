from __future__ import annotations

import json
import os
import threading
from pathlib import Path

# Used only when a model entry does not list explicit cache prices (Anthropic's multipliers).
DEFAULT_CACHE_READ_MULT = 0.10
DEFAULT_CACHE_WRITE_MULT = 1.25


class PricingTable:
    """USD-per-million-token prices loaded from a JSON file.

    * Models match by longest prefix, so "gpt-4o-mini-2024-07-18" matches "gpt-4o-mini",
      not "gpt-4o".
    * The file is re-read automatically when it changes, so you can edit prices
      without restarting the proxy.
    """

    def __init__(self, path: str | os.PathLike | None = None, models: dict | None = None):
        self.path = Path(path) if path else None
        self._models: dict[str, dict] = {}
        self._mtime: float | None = None
        self._lock = threading.Lock()
        if models is not None:
            self._set(models)
        else:
            self._reload(force=True)

    # -- loading ---------------------------------------------------------
    def _set(self, models: dict) -> None:
        cleaned = {
            k.lower(): v
            for k, v in models.items()
            if not k.startswith("_") and isinstance(v, dict)
        }
        # Longest keys first so prefix matching picks the most specific entry.
        self._models = dict(sorted(cleaned.items(), key=lambda kv: len(kv[0]), reverse=True))

    def _reload(self, force: bool = False) -> None:
        if self.path is None:
            return
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            return
        if not force and mtime == self._mtime:
            return
        with self._lock:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return  # keep the last good table
            self._set(data.get("models", data))
            self._mtime = mtime

    # -- lookups ---------------------------------------------------------
    def models(self) -> list[str]:
        self._reload()
        return list(self._models)

    def lookup(self, model: str | None) -> dict | None:
        if not model:
            return None
        self._reload()
        name = model.lower()
        for key, price in self._models.items():
            if name.startswith(key):
                return price
        return None

    def cost(
        self,
        model: str | None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> tuple[float, bool]:
        """Return (cost_usd, priced). `priced` is False when tokens were used but the
        model has no price entry, so the dashboard can flag it instead of showing $0."""
        total = input_tokens + output_tokens + cache_read_tokens + cache_write_tokens
        price = self.lookup(model)
        if price is None:
            return 0.0, total == 0
        try:
            inp = float(price["input"])
            out = float(price["output"])
        except (KeyError, TypeError, ValueError):
            return 0.0, total == 0
        cache_read = float(price.get("cache_read", inp * DEFAULT_CACHE_READ_MULT))
        cache_write = float(price.get("cache_write", inp * DEFAULT_CACHE_WRITE_MULT))
        cost = (
            input_tokens * inp
            + output_tokens * out
            + cache_read_tokens * cache_read
            + cache_write_tokens * cache_write
        ) / 1_000_000
        return cost, True
