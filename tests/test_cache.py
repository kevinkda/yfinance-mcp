"""Cache facade coverage tests for the pluggable backend (v0.7 T0).

.. versionchanged:: 0.2.0
    DuckDB removed; the cache delegates to a pluggable ``CacheBackend``
    (memory default).  Snapshot writes append to a derived-analysis time
    series — the memory backend keeps no durable history (persists 0 rows),
    a ClickHouse backend persists the full batch.  Zero network.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from yfinance_mcp import cache as cache_module
from yfinance_mcp.cache import (
    Cache,
    _to_float,
    cache_bypass,
    cache_enabled,
    get_cache,
)
from yfinance_mcp.cache_backend import ClickHouseBackend, MemoryBackend


def _ch_cache() -> tuple[Cache, MagicMock]:
    client = MagicMock()
    client.command.return_value = None
    client.insert.return_value = None
    result = MagicMock()
    result.result_rows = []
    client.query.return_value = result
    return Cache(backend=ClickHouseBackend(url="clickhouse://x", client=client)), client


def _inserted_rows(client: MagicMock) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for call in client.insert.call_args_list:
        for entry in call.args[1]:
            rows.append(json.loads(entry[1]))
    return rows


# ---------------------------------------------------------------------------
# Snapshot writes — ClickHouse backend (durable history → persists N)
# ---------------------------------------------------------------------------


class TestCacheWritesClickHouse:
    def test_write_splits(self) -> None:
        cache, client = _ch_cache()
        n = cache.write_splits("AAPL", [{"split_date": "2020-08-31", "ratio": 4.0}])
        assert n == 1
        rows = _inserted_rows(client)
        assert rows[0]["symbol"] == "AAPL"
        assert rows[0]["ratio"] == 4.0

    def test_write_earnings(self) -> None:
        cache, _ = _ch_cache()
        n = cache.write_earnings_calendar(
            "AAPL",
            [{"earnings_date": "2026-01-30", "eps_estimate": 2.1, "reported_eps": 2.18, "surprise_pct": 0.03}],
        )
        assert n == 1

    def test_write_financials(self) -> None:
        cache, client = _ch_cache()
        n = cache.write_financials(
            "AAPL", "annual", [{"period_end": "2025-09-30", "line_item": "Total Revenue", "value": 1.0}]
        )
        assert n == 1
        assert _inserted_rows(client)[0]["period"] == "annual"

    def test_write_recommendations(self) -> None:
        cache, _ = _ch_cache()
        n = cache.write_recommendations(
            "AAPL",
            [{"kind": "summary", "rec_date": "0m"}, {"kind": "upgrade_downgrade", "firm": "MS", "to_grade": "Buy"}],
        )
        assert n == 2

    def test_raw_json_roundtrip(self) -> None:
        cache, client = _ch_cache()
        cache.write_splits("AAPL", [{"split_date": "2020-08-31", "ratio": 4.0, "extra": "x"}])
        rows = _inserted_rows(client)
        assert json.loads(rows[0]["raw_json"])["extra"] == "x"

    def test_write_error_returns_zero(self) -> None:
        cache, client = _ch_cache()
        client.insert.side_effect = RuntimeError("boom")
        assert cache.write_splits("AAPL", [{"split_date": "x", "ratio": 1.0}]) == 0


# ---------------------------------------------------------------------------
# Snapshot writes — memory backend (no durable history → persists 0)
# ---------------------------------------------------------------------------


class TestCacheWritesMemory:
    def test_memory_persists_zero(self) -> None:
        cache = Cache(backend=MemoryBackend())
        assert cache.write_splits("AAPL", [{"split_date": "x", "ratio": 1.0}]) == 0
        assert cache.write_earnings_calendar("AAPL", [{"earnings_date": "x"}]) == 0
        assert cache.write_financials("AAPL", "annual", [{"line_item": "x"}]) == 0
        assert cache.write_recommendations("AAPL", [{"kind": "summary"}]) == 0

    def test_empty_rows_returns_zero(self) -> None:
        cache = Cache(backend=MemoryBackend())
        assert cache.write_splits("AAPL", []) == 0
        assert cache.write_earnings_calendar("AAPL", []) == 0
        assert cache.write_financials("AAPL", "annual", []) == 0
        assert cache.write_recommendations("AAPL", []) == 0

    def test_query_history_degrades(self) -> None:
        cache = Cache(backend=MemoryBackend())
        assert cache.query_history("splits")["status"] == "requires_clickhouse_persistence"

    def test_query_history_clickhouse(self) -> None:
        cache, client = _ch_cache()
        result = MagicMock()
        result.result_rows = [['{"symbol": "AAPL"}']]
        client.query.return_value = result
        out = cache.query_history("splits", limit=5)
        assert out["status"] == "ok"
        assert out["rows"] == [{"symbol": "AAPL"}]


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestCacheLifecycle:
    def test_close_idempotent(self) -> None:
        cache = Cache(backend=MemoryBackend())
        cache.close()
        cache.close()

    def test_context_manager(self) -> None:
        with Cache(backend=MemoryBackend()) as cache:
            assert cache.write_splits("AAPL", [{"split_date": "x", "ratio": 1.0}]) == 0

    def test_default_backend_is_memory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("YFINANCE_CACHE_BACKEND", raising=False)
        assert Cache().backend.name == "memory"

    def test_append_rows_empty_returns_zero(self) -> None:
        cache = Cache(backend=MemoryBackend())
        assert cache._append_rows("splits", []) == 0


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class TestCacheConfig:
    def test_cache_enabled_default_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("YFINANCE_CACHE_ENABLED", raising=False)
        assert cache_enabled() is False

    def test_cache_enabled_empty_string_default_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("YFINANCE_CACHE_ENABLED", "")
        assert cache_enabled() is False

    @pytest.mark.parametrize(
        "val,expected",
        [
            ("1", True),
            ("true", True),
            ("yes", True),
            ("on", True),
            ("TRUE", True),
            ("Yes", True),
            ("ON", True),
            ("  true  ", True),
            (" 1 ", True),
            ("0", False),
            ("false", False),
            ("no", False),
            ("off", False),
            ("FALSE", False),
            ("nope", False),
            ("2", False),
        ],
    )
    def test_cache_enabled_values(self, monkeypatch: pytest.MonkeyPatch, val: str, expected: bool) -> None:
        monkeypatch.setenv("YFINANCE_CACHE_ENABLED", val)
        assert cache_enabled() is expected

    def test_cache_bypass_default_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("YFINANCE_CACHE_BYPASS", raising=False)
        assert cache_bypass() is False

    def test_cache_bypass_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("YFINANCE_CACHE_BYPASS", "1")
        assert cache_bypass() is True


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestCacheSingleton:
    def test_get_cache_disabled_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("YFINANCE_CACHE_ENABLED", "0")
        cache_module.reset_cache_singleton()
        assert get_cache() is None

    def test_get_cache_unset_default_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("YFINANCE_CACHE_ENABLED", raising=False)
        cache_module.reset_cache_singleton()
        assert get_cache() is None

    def test_get_cache_returns_singleton(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("YFINANCE_CACHE_ENABLED", "1")
        monkeypatch.delenv("YFINANCE_CACHE_BACKEND", raising=False)
        cache_module.reset_cache_singleton()
        c1 = get_cache()
        c2 = get_cache()
        assert c1 is c2 is not None
        assert c1.backend.name == "memory"
        cache_module.reset_cache_singleton()

    def test_get_cache_init_failure_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("YFINANCE_CACHE_ENABLED", "1")
        cache_module.reset_cache_singleton()

        def boom(*a: Any, **k: Any) -> Any:
            raise RuntimeError("init fail")

        monkeypatch.setattr(cache_module, "get_cache_backend", boom)
        assert get_cache() is None
        cache_module.reset_cache_singleton()

    def test_reset_singleton_when_none(self) -> None:
        cache_module.reset_cache_singleton()
        cache_module.reset_cache_singleton()  # no-op, no raise


class TestToFloat:
    @pytest.mark.parametrize(
        "value,expected",
        [(None, None), ("", None), ("1.5", 1.5), (2, 2.0), ("abc", None), ([], None)],
    )
    def test_to_float(self, value: Any, expected: Any) -> None:
        assert _to_float(value) == expected
