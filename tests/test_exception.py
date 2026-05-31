"""Exception-path tests: every error branch surfaces a clean, normalised
result instead of leaking an internal exception. Zero network."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import duckdb
import pytest

from yfinance_mcp.client import YFinanceClient, YFinanceError
from yfinance_mcp.tools import _common, earnings, financials, recommendations, splits


class TestClientExceptionNormalisation:
    @pytest.mark.parametrize(
        "exc,expected",
        [
            (RuntimeError("HTTP Error 429: too many requests"), "rate_limited"),
            (ValueError("rate limit exceeded"), "rate_limited"),
            (RuntimeError("No data found"), "not_found"),
            (KeyError("delisted"), "not_found"),
            (RuntimeError("404"), "not_found"),
            (ConnectionError("connection refused"), "upstream_error"),
            (TypeError("unexpected type"), "upstream_error"),
            (Exception("totally generic"), "upstream_error"),
        ],
    )
    async def test_all_exception_classes_normalised(
        self, fake_ticker_factory: Any, exc: Exception, expected: str
    ) -> None:
        def factory(symbol: str) -> MagicMock:
            m = fake_ticker_factory(symbol)
            m.get_splits.side_effect = exc
            return m

        client = YFinanceClient(ticker_factory=factory, timeout=5.0)
        with pytest.raises(YFinanceError) as ei:
            await client.call("AAPL", "get_splits")
        assert ei.value.reason == expected

    async def test_keyerror_in_delisted_branch(self, fake_ticker_factory: Any) -> None:
        def factory(symbol: str) -> MagicMock:
            m = fake_ticker_factory(symbol)
            m.get_splits.side_effect = ValueError("symbol may be delisted; no data")
            return m

        client = YFinanceClient(ticker_factory=factory, timeout=5.0)
        with pytest.raises(YFinanceError) as ei:
            await client.call("AAPL", "get_splits")
        assert ei.value.reason == "not_found"


class TestToolExceptionEnvelopes:
    async def test_splits_error_envelope(self, fake_ticker_factory: Any) -> None:
        def factory(symbol: str) -> MagicMock:
            m = fake_ticker_factory(symbol)
            m.get_splits.side_effect = RuntimeError("429")
            return m

        _common.set_client(YFinanceClient(ticker_factory=factory, timeout=5.0))
        out = await splits.get_splits_impl({"symbol": "AAPL"})
        _common.reset_client_singleton()
        assert out == {
            "ok": False,
            "symbol": "AAPL",
            "error": {"reason": "rate_limited", "detail": "429"},
            "_cache_status": "skipped:error",
        }

    async def test_earnings_error_envelope(self, fake_ticker_factory: Any) -> None:
        def factory(symbol: str) -> MagicMock:
            m = fake_ticker_factory(symbol)
            m.get_earnings_dates.side_effect = RuntimeError("No data found")
            return m

        _common.set_client(YFinanceClient(ticker_factory=factory, timeout=5.0))
        out = await earnings.get_earnings_calendar_impl({"symbol": "AAPL"})
        _common.reset_client_singleton()
        assert out["ok"] is False
        assert out["error"]["reason"] == "not_found"

    async def test_financials_error_envelope(self, fake_ticker_factory: Any) -> None:
        def factory(symbol: str) -> MagicMock:
            m = fake_ticker_factory(symbol)
            type(m).income_stmt = property(lambda self: (_ for _ in ()).throw(RuntimeError("429")))
            return m

        _common.set_client(YFinanceClient(ticker_factory=factory, timeout=5.0))
        out = await financials.get_financial_statements_impl({"symbol": "AAPL"})
        _common.reset_client_singleton()
        assert out["error"]["reason"] == "rate_limited"

    async def test_recommendations_summary_error_envelope(self, fake_ticker_factory: Any) -> None:
        def factory(symbol: str) -> MagicMock:
            m = fake_ticker_factory(symbol)
            type(m).recommendations_summary = property(lambda self: (_ for _ in ()).throw(RuntimeError("404")))
            return m

        _common.set_client(YFinanceClient(ticker_factory=factory, timeout=5.0))
        out = await recommendations.get_analyst_recommendations_impl({"symbol": "AAPL"})
        _common.reset_client_singleton()
        assert out["ok"] is False
        assert out["error"]["reason"] == "not_found"


class TestCacheExceptionResilience:
    def test_executemany_error_does_not_raise(self, tmp_cache: Any) -> None:
        real = tmp_cache._conn
        wrapped = MagicMock(wraps=real)
        wrapped.executemany.side_effect = duckdb.Error("disk I/O error")
        tmp_cache._conn = wrapped
        # Must swallow and return 0, never raise.
        assert tmp_cache.write_financials("AAPL", "annual", [{"line_item": "x", "value": 1.0}]) == 0

    def test_log_event_error_swallowed(self, tmp_cache: Any) -> None:
        real = tmp_cache._conn
        wrapped = MagicMock(wraps=real)
        wrapped.execute.side_effect = duckdb.Error("log fail")
        tmp_cache._conn = wrapped
        # Must not raise.
        tmp_cache._log_event("INSERT", "splits", 1)
        tmp_cache._conn = real

    def test_close_swallows_duckdb_error(self, tmp_cache: Any) -> None:
        real = tmp_cache._conn
        wrapped = MagicMock(wraps=real)
        wrapped.close.side_effect = duckdb.Error("already closed")
        tmp_cache._conn = wrapped
        tmp_cache.close()  # must not raise
        assert tmp_cache._conn is None


class TestJsonifyExceptionPaths:
    def test_jsonify_item_exception_then_isoformat_exception(self) -> None:
        from yfinance_mcp.tools._common import jsonify

        obj = MagicMock()
        obj.item.side_effect = TypeError("no item")
        obj.isoformat.side_effect = TypeError("no iso")
        assert isinstance(jsonify(obj), str)

    def test_jsonify_isoformat_success(self) -> None:
        from yfinance_mcp.tools._common import jsonify

        obj = MagicMock()
        obj.item = None  # not callable
        obj.isoformat.return_value = "2020-01-01T00:00:00"
        assert jsonify(obj) == "2020-01-01T00:00:00"
