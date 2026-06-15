"""Pluggable derived-history cache for yfinance-mcp (v0.7 T0).

.. versionchanged:: 0.2.0
    ⚠️ **BREAKING** — the embedded DuckDB cache is removed.  The cache now
    delegates to a pluggable
    :class:`~yfinance_mcp.cache_backend.CacheBackend`:

    * **memory** (default) — in-process, zero external dependency,
      concurrency-safe, non-blocking (no global ``RLock``, no file locks).
      The memory backend keeps **no durable history**, so snapshot writes
      report ``0`` rows persisted (graceful degradation).
    * **clickhouse** (opt-in) — ``pip install yfinance-mcp[clickhouse]`` +
      ``YFINANCE_CLICKHOUSE_URL`` + ``YFINANCE_CACHE_BACKEND=clickhouse`` to
      durably persist the historical Yahoo Finance snapshots.

    Selection via ``YFINANCE_CACHE_BACKEND`` (``memory`` | ``clickhouse``,
    default ``memory``).

Stores **historical snapshots** of the read-only Yahoo Finance frames this
server fetches as append-only derived-analysis time series:

  * ``splits``            — one row per (symbol, split_date, observed_at)
  * ``earnings_calendar`` — upcoming/declared earnings dates per symbol
  * ``financials``        — income-statement line items (annual / quarterly)
  * ``recommendations``   — analyst rating rows + upgrades/downgrades

Failure mode: **best-effort** — every backend swallows storage errors and the
caller falls through to the live yfinance response.  This module is NOT a
correctness dependency: every tool works with the cache disabled
(``YFINANCE_CACHE_ENABLED=0``).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import UTC, datetime
from typing import Any, Final

from .cache_backend import (
    CacheBackend,
    get_cache_backend,
)

log = logging.getLogger(__name__)

CACHE_DIR_NAME: Final[str] = "yfinance-mcp"

ENV_CACHE_ENABLED: Final[str] = "YFINANCE_CACHE_ENABLED"
ENV_CACHE_BYPASS: Final[str] = "YFINANCE_CACHE_BYPASS"

_SPLITS_SERIES: Final[str] = "splits"
_EARNINGS_SERIES: Final[str] = "earnings_calendar"
_FINANCIALS_SERIES: Final[str] = "financials"
_RECOMMENDATIONS_SERIES: Final[str] = "recommendations"


def _truthy(raw: str | None, *, default: bool) -> bool:
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def cache_enabled() -> bool:
    """Honor ``YFINANCE_CACHE_ENABLED`` (default off — opt-in).

    .. versionchanged:: 0.1.1
        cache now opt-in, default disabled.  Set ``YFINANCE_CACHE_ENABLED=true``
        (also accepts ``1`` / ``yes`` / ``on``) to enable it.
    """
    return _truthy(os.environ.get(ENV_CACHE_ENABLED), default=False)


def cache_bypass() -> bool:
    return _truthy(os.environ.get(ENV_CACHE_BYPASS), default=False)


# ---------------------------------------------------------------------------
# Cache facade
# ---------------------------------------------------------------------------


class Cache:
    """Backend-agnostic derived-history writer.  One instance per process.

    Delegates all storage to a :class:`CacheBackend` (memory by default,
    ClickHouse when opted in).  The legacy snapshot-write public API is kept
    verbatim so tools require no changes.

    Each ``write_*`` method appends one row per record to the corresponding
    derived-analysis time series and returns the number of rows the backend
    durably persisted (``0`` on the memory backend, which keeps no history).
    """

    def __init__(self, backend: CacheBackend | None = None) -> None:
        self.backend: CacheBackend = backend if backend is not None else get_cache_backend()
        self._lock = threading.Lock()

    def close(self) -> None:
        # Pluggable backends own their own lifecycle; nothing to close for
        # the memory backend, and the ClickHouse client is process-scoped.
        return None

    def __enter__(self) -> Cache:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        del exc_type, exc, tb
        self.close()

    # -- internal append helper ------------------------------------------

    def _append_rows(self, series: str, rows: list[dict[str, Any]]) -> int:
        """Append rows to *series*; return the count durably persisted.

        The memory backend persists no history (returns a degradation
        signal) → ``0`` rows.  The ClickHouse backend persists each row →
        full count.  Storage errors are swallowed best-effort → ``0``.
        """
        if not rows:
            return 0
        persisted = 0
        with self._lock:
            for row in rows:
                try:
                    result = self.backend.append_timeseries(series, row)
                except Exception as exc:  # pragma: no cover - defensive
                    log.warning("append_timeseries failed for %s: %s", series, exc)
                    break
                if result.get("status") == "ok":
                    persisted += 1
                else:
                    # Memory backend (or error) — no durable history. Stop:
                    # all rows in this batch share the same backend outcome.
                    break
        return persisted

    # -- write helpers (public API — tools depend on these) ---------------

    def write_splits(self, symbol: str, rows: list[dict[str, Any]]) -> int:
        ts = datetime.now(UTC).isoformat()
        prepared = [
            {
                "observed_at": ts,
                "symbol": symbol,
                "split_date": str(r.get("split_date") or ""),
                "ratio": _to_float(r.get("ratio")),
                "raw_json": json.dumps(r, default=str),
            }
            for r in rows
        ]
        return self._append_rows(_SPLITS_SERIES, prepared)

    def write_earnings_calendar(self, symbol: str, rows: list[dict[str, Any]]) -> int:
        ts = datetime.now(UTC).isoformat()
        prepared = [
            {
                "observed_at": ts,
                "symbol": symbol,
                "earnings_date": str(r.get("earnings_date") or ""),
                "eps_estimate": _to_float(r.get("eps_estimate")),
                "reported_eps": _to_float(r.get("reported_eps")),
                "surprise_pct": _to_float(r.get("surprise_pct")),
                "raw_json": json.dumps(r, default=str),
            }
            for r in rows
        ]
        return self._append_rows(_EARNINGS_SERIES, prepared)

    def write_financials(self, symbol: str, period: str, rows: list[dict[str, Any]]) -> int:
        ts = datetime.now(UTC).isoformat()
        prepared = [
            {
                "observed_at": ts,
                "symbol": symbol,
                "period": period,
                "period_end": str(r.get("period_end") or ""),
                "line_item": str(r.get("line_item") or ""),
                "value": _to_float(r.get("value")),
                "raw_json": json.dumps(r, default=str),
            }
            for r in rows
        ]
        return self._append_rows(_FINANCIALS_SERIES, prepared)

    def write_recommendations(self, symbol: str, rows: list[dict[str, Any]]) -> int:
        ts = datetime.now(UTC).isoformat()
        prepared = [
            {
                "observed_at": ts,
                "symbol": symbol,
                "kind": str(r.get("kind") or ""),
                "firm": str(r.get("firm") or ""),
                "to_grade": str(r.get("to_grade") or ""),
                "from_grade": str(r.get("from_grade") or ""),
                "action": str(r.get("action") or ""),
                "rec_date": str(r.get("rec_date") or ""),
                "raw_json": json.dumps(r, default=str),
            }
            for r in rows
        ]
        return self._append_rows(_RECOMMENDATIONS_SERIES, prepared)

    # -- query (derived-analysis history readback) -----------------------

    def query_history(self, series: str, *, limit: int = 1000) -> dict[str, Any]:
        """Read back a derived-analysis time series.

        Returns the backend payload — ``{"status": "ok", "rows": [...]}`` when
        ClickHouse-backed, or a ``requires_clickhouse_persistence`` signal on
        the memory backend.
        """
        return self.backend.query_timeseries(series, {"limit": limit})


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

    Returns ``None`` when caching is disabled, which is the **default** —
    the cache is opt-in via ``YFINANCE_CACHE_ENABLED=true``.
    """
    global _cache_singleton
    if not cache_enabled():
        return None
    with _cache_singleton_lock:
        if _cache_singleton is None:
            try:
                _cache_singleton = Cache()
            except Exception as exc:  # pragma: no cover - defensive backend init
                log.warning("Cache init failed; running without cache: %s", exc)
                return None
        return _cache_singleton


def reset_cache_singleton() -> None:
    """Test hook: drop the cached singleton."""
    global _cache_singleton
    with _cache_singleton_lock:
        if _cache_singleton is not None:
            _cache_singleton.close()
        _cache_singleton = None


__all__ = [
    "CACHE_DIR_NAME",
    "ENV_CACHE_BYPASS",
    "ENV_CACHE_ENABLED",
    "Cache",
    "cache_bypass",
    "cache_enabled",
    "get_cache",
    "reset_cache_singleton",
]
