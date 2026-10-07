from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  ts                 TEXT NOT NULL,            -- UTC, 'YYYY-MM-DD HH:MM:SS'
  provider           TEXT NOT NULL,            -- anthropic | openai
  endpoint           TEXT,
  model              TEXT,
  user_tag           TEXT,                     -- from X-User-Tag
  feature_tag        TEXT,                     -- from X-Feature-Tag
  streamed           INTEGER DEFAULT 0,
  input_tokens       INTEGER DEFAULT 0,        -- uncached prompt tokens
  output_tokens      INTEGER DEFAULT 0,
  cache_read_tokens  INTEGER DEFAULT 0,
  cache_write_tokens INTEGER DEFAULT 0,
  cost_usd           REAL    DEFAULT 0,
  priced             INTEGER DEFAULT 1,        -- 0 = tokens used but model has no price
  latency_ms         INTEGER,
  ttft_ms            INTEGER,                  -- time to first generated token (streams)
  status_code        INTEGER,
  error              TEXT,
  prompt_preview     TEXT                      -- only when LOG_PROMPTS=1
);
CREATE INDEX IF NOT EXISTS idx_requests_ts ON requests(ts);
CREATE INDEX IF NOT EXISTS idx_requests_model ON requests(model);

CREATE TABLE IF NOT EXISTS alerts (
  day  TEXT NOT NULL,
  kind TEXT NOT NULL,
  ts   TEXT NOT NULL,
  PRIMARY KEY (day, kind)
);
"""

COLUMNS = [
    "ts", "provider", "endpoint", "model", "user_tag", "feature_tag", "streamed",
    "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens",
    "cost_usd", "priced", "latency_ms", "ttft_ms", "status_code", "error",
    "prompt_preview",
]

_INSERT = "INSERT INTO requests ({cols}) VALUES ({marks})".format(
    cols=", ".join(COLUMNS), marks=", ".join(f":{c}" for c in COLUMNS)
)


def utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class Database:
    """Tiny thread-safe SQLite wrapper (WAL mode so the dashboard can read while we write)."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    @staticmethod
    def _row(row: dict) -> dict:
        return {c: row.get(c) for c in COLUMNS}

    def insert_request(self, row: dict) -> None:
        with self._lock:
            self._conn.execute(_INSERT, self._row(row))
            self._conn.commit()

    def insert_many(self, rows: list[dict]) -> None:
        with self._lock:
            self._conn.executemany(_INSERT, [self._row(r) for r in rows])
            self._conn.commit()

    def clear_requests(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM requests")
            self._conn.execute("DELETE FROM alerts")
            self._conn.commit()

    def all_requests(self) -> list[dict]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM requests ORDER BY id")
            return [dict(r) for r in cur.fetchall()]

    def query(self, sql: str, params=()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def spend_for_day(self, day: str) -> float:
        with self._lock:
            cur = self._conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM requests WHERE ts >= ? AND ts <= ?",
                (f"{day} 00:00:00", f"{day} 23:59:59"),
            )
            return float(cur.fetchone()[0])

    def claim_alert(self, day: str, kind: str) -> bool:
        """True only the first time (day, kind) is claimed, so each alert fires once."""
        with self._lock:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO alerts (day, kind, ts) VALUES (?, ?, ?)",
                (day, kind, utc_now_str()),
            )
            self._conn.commit()
            return cur.rowcount == 1
