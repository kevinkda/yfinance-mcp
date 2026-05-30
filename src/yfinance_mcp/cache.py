"""DuckDB-backed local cache for yfinance-mcp.

Stores **historical snapshots** of the read-only Yahoo Finance frames this
server fetches, so an LLM agent can run "what changed since last week"
queries without re-hitting Yahoo (which is both slow and ToS-sensitive):

  * ``splits``           — one row per (symbol, split_date, observed_at)
  * ``earnings_calendar``— upcoming/declared earnings dates per symbol
  * ``financials``       — income-statement line items (annual / quarterly)
  * ``recommendations``  — analyst rating rows + upgrades/downgrades
  * ``cache_events``     — diagnostic event log (INSERT / SKIP / ERROR)

Storage
-------
Single-file DuckDB database under
``${XDG_STATE_HOME}/yfinance-mcp/cache.duckdb`` (or ``%LOCALAPPDATA%`` on
Windows). The DB file is chmod'd to ``0o600`` on POSIX.

Failure mode
------------
**Cache is best-effort.** Any DuckDB / IO error is caught, logged at
WARNING, and the caller falls through to the live yfinance response. A
corrupt DB is renamed aside (``cache.duckdb.corrupt-<ts>``) and a fresh one
created. This module is NOT a correctness dependency — every tool works
with the cache disabled (``YFINANCE_CACHE_ENABLED=0``).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import duckdb

from . import _platform

log = logging.getLogger(__name__)

CACHE_DB_FILENAME: Final[str] = "cache.duckdb"
CACHE_DIR_NAME: Final[str] = "yfinance-mcp"

ENV_CACHE_ENABLED: Final[str] = "YFINANCE_CACHE_ENABLED"
ENV_CACHE_BYPASS: Final[str] = "YFINANCE_CACHE_BYPASS"
ENV_CACHE_PATH: Final[str] = "YFINANCE_CACHE_PATH"


def _truthy(raw: str | None, *, default: bool) -> bool:
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def cache_enabled() -> bool:
    return _truthy(os.environ.get(ENV_CACHE_ENABLED), default=True)


def cache_bypass() -> bool:
    return _truthy(os.environ.get(ENV_CACHE_BYPASS), default=False)


def default_db_path() -> Path:
    override = os.environ.get(ENV_CACHE_PATH, "").strip()
    if override:
        return Path(override).expanduser()
    return _platform.state_root() / CACHE_DIR_NAME / CACHE_DB_FILENAME


# ---------------------------------------------------------------------------
# Schema (DDL) — keep idempotent; CREATE TABLE IF NOT EXISTS.
# ---------------------------------------------------------------------------

_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS splits (
        observed_at  TIMESTAMP NOT NULL,
        symbol       VARCHAR   NOT NULL,
        split_date   VARCHAR   NOT NULL,
        ratio        DOUBLE,
        raw_json     VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS earnings_calendar (
        observed_at    TIMESTAMP NOT NULL,
        symbol         VARCHAR   NOT NULL,
        earnings_date  VARCHAR,
        eps_estimate   DOUBLE,
        reported_eps   DOUBLE,
        surprise_pct   DOUBLE,
        raw_json       VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS financials (
        observed_at  TIMESTAMP NOT NULL,
        symbol       VARCHAR   NOT NULL,
        period       VARCHAR   NOT NULL,  -- annual / quarterly
        period_end   VARCHAR,
        line_item    VARCHAR,
        value        DOUBLE,
        raw_json     VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS recommendations (
        observed_at  TIMESTAMP NOT NULL,
        symbol       VARCHAR   NOT NULL,
        kind         VARCHAR,             -- summary / upgrade_downgrade
        firm         VARCHAR,
        to_grade     VARCHAR,
        from_grade   VARCHAR,
        action       VARCHAR,
        rec_date     VARCHAR,
        raw_json     VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cache_events (
        ts          TIMESTAMP NOT NULL,
        kind        VARCHAR   NOT NULL,  -- INSERT / SKIP / ERROR
        table_name  VARCHAR,
        row_count   BIGINT,
        detail      VARCHAR
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_splits_symbol ON splits(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_earnings_symbol ON earnings_calendar(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_financials_symbol ON financials(symbol, period)",
    "CREATE INDEX IF NOT EXISTS idx_recommendations_symbol ON recommendations(symbol, kind)",
)


# ---------------------------------------------------------------------------
# Cache class
# ---------------------------------------------------------------------------


class Cache:
    """Thread-safe DuckDB cache.

    Open ONE instance per process and reuse it (see :func:`get_cache`). The
    class owns the DuckDB connection and a re-entrant lock that serialises
    writes from concurrent tool calls.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path: Path = db_path or default_db_path()
        self._lock = threading.RLock()
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._open()

    # -- lifecycle --------------------------------------------------------

    def _open(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(self._db_path.parent, 0o700)
        try:
            self._conn = duckdb.connect(str(self._db_path))
        except duckdb.Error as exc:
            log.warning("DuckDB open failed at %s: %s; quarantining and retrying", self._db_path, exc)
            self._quarantine_and_retry()
        self._init_schema()
        with contextlib.suppress(OSError):
            _platform.secure_chmod(self._db_path, 0o600)

    def _quarantine_and_retry(self) -> None:
        ts = int(time.time())
        bad = self._db_path.with_name(f"{self._db_path.name}.corrupt-{ts}")
        with contextlib.suppress(OSError):
            self._db_path.rename(bad)
            log.warning("Quarantined corrupt cache to %s", bad)
        self._conn = duckdb.connect(str(self._db_path))

    def _init_schema(self) -> None:
        assert self._conn is not None
        for stmt in _DDL:
            try:
                self._conn.execute(stmt)
            except duckdb.Error as exc:
                log.warning("DuckDB DDL failed: %s; stmt=%s", exc, stmt[:60])

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                with contextlib.suppress(duckdb.Error):
                    self._conn.close()
                self._conn = None

    # -- write helpers ----------------------------------------------------

    def _log_event(self, kind: str, table: str, count: int, detail: str = "") -> None:
        if self._conn is None:
            return
        with contextlib.suppress(duckdb.Error):
            self._conn.execute(
                "INSERT INTO cache_events (ts, kind, table_name, row_count, detail) VALUES (?, ?, ?, ?, ?)",
                [datetime.now(UTC), kind, table, count, detail[:500]],
            )

    def _executemany(self, table: str, sql: str, rows: list[list[Any]]) -> int:
        if self._conn is None or not rows:
            return 0
        with self._lock:
            try:
                self._conn.executemany(sql, rows)
                self._log_event("INSERT", table, len(rows))
            except duckdb.Error as exc:
                self._log_event("ERROR", table, 0, str(exc))
                log.warning("cache write to %s failed: %s", table, exc)
                return 0
        return len(rows)

    def write_splits(self, symbol: str, rows: list[dict[str, Any]]) -> int:
        ts = datetime.now(UTC)
        prepared = [
            [
                ts,
                symbol,
                str(r.get("split_date") or ""),
                _to_float(r.get("ratio")),
                json.dumps(r, default=str),
            ]
            for r in rows
        ]
        return self._executemany(
            "splits",
            "INSERT INTO splits (observed_at, symbol, split_date, ratio, raw_json) VALUES (?, ?, ?, ?, ?)",
            prepared,
        )

    def write_earnings_calendar(self, symbol: str, rows: list[dict[str, Any]]) -> int:
        ts = datetime.now(UTC)
        prepared = [
            [
                ts,
                symbol,
                str(r.get("earnings_date") or ""),
                _to_float(r.get("eps_estimate")),
                _to_float(r.get("reported_eps")),
                _to_float(r.get("surprise_pct")),
                json.dumps(r, default=str),
            ]
            for r in rows
        ]
        return self._executemany(
            "earnings_calendar",
            "INSERT INTO earnings_calendar (observed_at, symbol, earnings_date, eps_estimate, "
            "reported_eps, surprise_pct, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            prepared,
        )

    def write_financials(self, symbol: str, period: str, rows: list[dict[str, Any]]) -> int:
        ts = datetime.now(UTC)
        prepared = [
            [
                ts,
                symbol,
                period,
                str(r.get("period_end") or ""),
                str(r.get("line_item") or ""),
                _to_float(r.get("value")),
                json.dumps(r, default=str),
            ]
            for r in rows
        ]
        return self._executemany(
            "financials",
            "INSERT INTO financials (observed_at, symbol, period, period_end, line_item, value, raw_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            prepared,
        )

    def write_recommendations(self, symbol: str, rows: list[dict[str, Any]]) -> int:
        ts = datetime.now(UTC)
        prepared = [
            [
                ts,
                symbol,
                str(r.get("kind") or ""),
                str(r.get("firm") or ""),
                str(r.get("to_grade") or ""),
                str(r.get("from_grade") or ""),
                str(r.get("action") or ""),
                str(r.get("rec_date") or ""),
                json.dumps(r, default=str),
            ]
            for r in rows
        ]
        return self._executemany(
            "recommendations",
            "INSERT INTO recommendations (observed_at, symbol, kind, firm, to_grade, from_grade, "
            "action, rec_date, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            prepared,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_cache_singleton: Cache | None = None
_cache_singleton_lock = threading.Lock()


def get_cache() -> Cache | None:
    """Return the process-wide :class:`Cache` (lazy init).

    Returns ``None`` if caching is disabled via ``YFINANCE_CACHE_ENABLED=0``.
    """
    global _cache_singleton
    if not cache_enabled():
        return None
    with _cache_singleton_lock:
        if _cache_singleton is None:
            try:
                _cache_singleton = Cache()
            except duckdb.Error as exc:
                log.warning("Cache init failed; running without cache: %s", exc)
                return None
        return _cache_singleton


def reset_cache_singleton() -> None:
    """Test hook: drop the cached singleton (does NOT delete the DB file)."""
    global _cache_singleton
    with _cache_singleton_lock:
        if _cache_singleton is not None:
            _cache_singleton.close()
        _cache_singleton = None


__all__ = [
    "Cache",
    "cache_bypass",
    "cache_enabled",
    "default_db_path",
    "get_cache",
    "reset_cache_singleton",
]
