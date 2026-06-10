"""Cache (DuckDB) coverage tests — real cache rooted in tmp_path, plus
quarantine/error/disabled branches via monkeypatch. Zero network."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import duckdb
import pytest

from yfinance_mcp import cache as cache_module
from yfinance_mcp.cache import (
    Cache,
    _to_float,
    cache_bypass,
    cache_enabled,
    default_db_path,
    get_cache,
)


class TestCacheWrites:
    def test_write_and_read_splits(self, tmp_cache: Cache) -> None:
        n = tmp_cache.write_splits("AAPL", [{"split_date": "2020-08-31", "ratio": 4.0}])
        assert n == 1
        rows = tmp_cache._conn.execute("SELECT symbol, ratio FROM splits").fetchall()
        assert rows == [("AAPL", 4.0)]

    def test_write_earnings(self, tmp_cache: Cache) -> None:
        n = tmp_cache.write_earnings_calendar(
            "AAPL",
            [{"earnings_date": "2026-01-30", "eps_estimate": 2.1, "reported_eps": 2.18, "surprise_pct": 0.03}],
        )
        assert n == 1
        cnt = tmp_cache._conn.execute("SELECT count(*) FROM earnings_calendar").fetchone()[0]
        assert cnt == 1

    def test_write_financials(self, tmp_cache: Cache) -> None:
        n = tmp_cache.write_financials(
            "AAPL", "annual", [{"period_end": "2025-09-30", "line_item": "Total Revenue", "value": 1.0}]
        )
        assert n == 1
        period = tmp_cache._conn.execute("SELECT period FROM financials").fetchone()[0]
        assert period == "annual"

    def test_write_recommendations(self, tmp_cache: Cache) -> None:
        n = tmp_cache.write_recommendations(
            "AAPL",
            [{"kind": "summary", "rec_date": "0m"}, {"kind": "upgrade_downgrade", "firm": "MS", "to_grade": "Buy"}],
        )
        assert n == 2

    def test_empty_rows_returns_zero(self, tmp_cache: Cache) -> None:
        assert tmp_cache.write_splits("AAPL", []) == 0
        assert tmp_cache.write_earnings_calendar("AAPL", []) == 0
        assert tmp_cache.write_financials("AAPL", "annual", []) == 0
        assert tmp_cache.write_recommendations("AAPL", []) == 0

    def test_cache_event_logged_on_insert(self, tmp_cache: Cache) -> None:
        tmp_cache.write_splits("AAPL", [{"split_date": "2020-08-31", "ratio": 4.0}])
        kinds = [r[0] for r in tmp_cache._conn.execute("SELECT kind FROM cache_events").fetchall()]
        assert "INSERT" in kinds

    def test_raw_json_roundtrip(self, tmp_cache: Cache) -> None:
        import json

        tmp_cache.write_splits("AAPL", [{"split_date": "2020-08-31", "ratio": 4.0, "extra": "x"}])
        raw = tmp_cache._conn.execute("SELECT raw_json FROM splits").fetchone()[0]
        assert json.loads(raw)["extra"] == "x"


class TestCacheLifecycle:
    def test_close_idempotent(self, tmp_cache: Cache) -> None:
        tmp_cache.close()
        tmp_cache.close()  # second close must not raise
        assert tmp_cache._conn is None

    def test_write_after_close_returns_zero(self, tmp_cache: Cache) -> None:
        tmp_cache.close()
        assert tmp_cache.write_splits("AAPL", [{"split_date": "x", "ratio": 1.0}]) == 0

    def test_log_event_after_close_noop(self, tmp_cache: Cache) -> None:
        tmp_cache.close()
        tmp_cache._log_event("INSERT", "splits", 1)  # must not raise

    def test_executemany_db_error_logs_and_returns_zero(
        self, tmp_cache: Cache, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real = tmp_cache._conn
        wrapped = MagicMock(wraps=real)
        wrapped.executemany.side_effect = duckdb.Error("boom")
        tmp_cache._conn = wrapped
        assert tmp_cache.write_splits("AAPL", [{"split_date": "x", "ratio": 1.0}]) == 0

    def test_init_schema_ddl_error_is_swallowed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        orig_connect = duckdb.connect

        def bad_execute_conn(*a: Any, **k: Any) -> Any:
            conn = orig_connect(*a, **k)
            wrapped = MagicMock(wraps=conn)
            wrapped.execute.side_effect = duckdb.Error("ddl boom")
            return wrapped

        monkeypatch.setattr(cache_module.duckdb, "connect", bad_execute_conn)
        # Should not raise despite every DDL failing.
        Cache(db_path=tmp_path / "c.duckdb")

    def test_quarantine_on_open_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        db = tmp_path / "c.duckdb"
        db.write_text("corrupt")
        calls = {"n": 0}
        orig_connect = duckdb.connect

        def flaky_connect(path: str, *a: Any, **k: Any) -> Any:
            calls["n"] += 1
            if calls["n"] == 1:
                raise duckdb.Error("cannot open corrupt db")
            return orig_connect(path, *a, **k)

        monkeypatch.setattr(cache_module.duckdb, "connect", flaky_connect)
        cache = Cache(db_path=db)
        assert cache._conn is not None
        assert calls["n"] >= 2


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

    def test_default_db_path_override(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("YFINANCE_CACHE_PATH", str(tmp_path / "x.duckdb"))
        assert default_db_path() == tmp_path / "x.duckdb"

    def test_default_db_path_xdg(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.delenv("YFINANCE_CACHE_PATH", raising=False)
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        p = default_db_path()
        assert p.name == "cache.duckdb"
        assert "yfinance-mcp" in str(p)


class TestCacheSingleton:
    def test_get_cache_disabled_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("YFINANCE_CACHE_ENABLED", "0")
        cache_module.reset_cache_singleton()
        assert get_cache() is None

    def test_get_cache_unset_default_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("YFINANCE_CACHE_ENABLED", raising=False)
        cache_module.reset_cache_singleton()
        assert get_cache() is None

    def test_get_cache_returns_singleton(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("YFINANCE_CACHE_ENABLED", "1")
        monkeypatch.setenv("YFINANCE_CACHE_PATH", str(tmp_path / "c.duckdb"))
        cache_module.reset_cache_singleton()
        c1 = get_cache()
        c2 = get_cache()
        assert c1 is c2 is not None
        cache_module.reset_cache_singleton()

    def test_get_cache_init_failure_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("YFINANCE_CACHE_ENABLED", "1")
        cache_module.reset_cache_singleton()

        def boom(*a: Any, **k: Any) -> Any:
            raise duckdb.Error("init fail")

        monkeypatch.setattr(cache_module, "Cache", boom)
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
