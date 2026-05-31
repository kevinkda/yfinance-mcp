"""Tool-layer tests: 6 tools normal + error + empty-data paths, plus the
``_common`` normalisation helpers. Zero network (fake ticker_factory)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest

from yfinance_mcp.client import YFinanceClient, YFinanceError
from yfinance_mcp.tools import _common, earnings, financials, meta, recommendations, splits
from yfinance_mcp.tools._common import (
    dataframe_to_records,
    error_payload,
    frame_is_empty,
    get_client,
    jsonify,
    series_to_records,
    set_client,
)


# ===========================================================================
# _common helpers
# ===========================================================================
class TestCommonHelpers:
    def test_get_client_lazy_singleton(self) -> None:
        _common.reset_client_singleton()
        c1 = get_client()
        c2 = get_client()
        assert c1 is c2
        _common.reset_client_singleton()

    @pytest.mark.parametrize(
        "value,expected",
        [(None, None), (1.5, 1.5), ("s", "s"), (3, 3), (True, True), (float("nan"), None), (float("inf"), None)],
    )
    def test_jsonify_scalars(self, value: Any, expected: Any) -> None:
        assert jsonify(value) == expected

    def test_jsonify_numpy_scalar(self) -> None:
        import numpy as np

        assert jsonify(np.int64(7)) == 7

    def test_jsonify_timestamp(self) -> None:
        out = jsonify(pd.Timestamp("2020-01-01"))
        assert out.startswith("2020-01-01")

    def test_jsonify_item_raises_falls_through(self) -> None:
        obj = MagicMock()
        obj.item.side_effect = ValueError("nope")
        obj.isoformat.side_effect = ValueError("nope")
        # str() fallback
        assert isinstance(jsonify(obj), str)

    def test_jsonify_unknown_object_stringified(self) -> None:
        class Weird:
            def __str__(self) -> str:
                return "weird"

        assert jsonify(Weird()) == "weird"

    def test_frame_is_empty(self) -> None:
        assert frame_is_empty(None) is True
        assert frame_is_empty(pd.DataFrame()) is True
        assert frame_is_empty(pd.Series([], dtype=float)) is True
        assert frame_is_empty(pd.Series([1.0])) is False

    def test_frame_is_empty_no_empty_attr_len(self) -> None:
        assert frame_is_empty([]) is True
        assert frame_is_empty([1, 2]) is False

    def test_frame_is_empty_len_typeerror(self) -> None:
        obj = MagicMock()
        obj.empty = None
        obj.__len__ = MagicMock(side_effect=TypeError)
        assert frame_is_empty(obj) is False

    def test_dataframe_to_records(self) -> None:
        df = pd.DataFrame({"A": [1, 2]}, index=["x", "y"])
        recs = dataframe_to_records(df)
        assert recs == [{"index": "x", "A": 1}, {"index": "y", "A": 2}]

    def test_dataframe_to_records_empty(self) -> None:
        assert dataframe_to_records(pd.DataFrame()) == []

    def test_dataframe_to_records_missing_attrs(self) -> None:
        obj = MagicMock()
        obj.empty = False
        obj.to_dict = None
        assert dataframe_to_records(obj) == []

    def test_dataframe_to_records_at_raises(self) -> None:
        df = pd.DataFrame({"A": [1]}, index=["x"])
        wrapped = MagicMock(wraps=df)
        wrapped.empty = False
        wrapped.columns = df.columns
        wrapped.index = df.index
        wrapped.to_dict = df.to_dict
        type(wrapped).at = property(lambda self: (_ for _ in ()).throw(KeyError("boom")))
        recs = dataframe_to_records(wrapped)
        assert recs == [{"index": "x", "A": None}]

    def test_series_to_records(self) -> None:
        s = pd.Series([4.0], index=pd.to_datetime(["2020-08-31"]))
        recs = series_to_records(s, key_name="d", value_name="r")
        assert recs[0]["r"] == 4.0

    def test_series_to_records_empty(self) -> None:
        assert series_to_records(pd.Series([], dtype=float), key_name="d", value_name="r") == []

    def test_series_to_records_no_items(self) -> None:
        obj = MagicMock()
        obj.empty = False
        obj.items = None
        assert series_to_records(obj, key_name="d", value_name="r") == []

    def test_error_payload(self) -> None:
        p = error_payload(YFinanceError("not_found", "x"), "AAPL")
        assert p["ok"] is False
        assert p["error"]["reason"] == "not_found"
        assert p["_cache_status"] == "skipped:error"


# ===========================================================================
# splits
# ===========================================================================
class TestSplits:
    async def test_normal(self, installed_client: YFinanceClient) -> None:
        out = await splits.get_splits_impl({"symbol": "AAPL"})
        assert out["ok"] is True
        assert out["count"] == 2
        assert out["_cache_status"] == "skipped:disabled"

    async def test_error(self, fake_ticker_factory: Any) -> None:
        def factory(symbol: str) -> MagicMock:
            m = fake_ticker_factory(symbol)
            m.get_splits.side_effect = ValueError("No data found")
            return m

        set_client(YFinanceClient(ticker_factory=factory, timeout=5.0))
        out = await splits.get_splits_impl({"symbol": "ZZZZ"})
        _common.reset_client_singleton()
        assert out["ok"] is False
        assert out["error"]["reason"] == "not_found"

    async def test_empty(self, fake_ticker_factory: Any) -> None:
        def factory(symbol: str) -> MagicMock:
            m = fake_ticker_factory(symbol)
            m.get_splits.return_value = pd.Series([], dtype=float)
            return m

        set_client(YFinanceClient(ticker_factory=factory, timeout=5.0))
        out = await splits.get_splits_impl({"symbol": "AAPL"})
        _common.reset_client_singleton()
        assert out["ok"] is True
        assert out["count"] == 0

    async def test_with_cache(self, installed_client: YFinanceClient, tmp_cache: Any) -> None:
        out = await splits.get_splits_impl({"symbol": "AAPL"})
        assert out["_cache_status"] == "snapshot_written:2"


# ===========================================================================
# earnings
# ===========================================================================
class TestEarnings:
    async def test_normal(self, installed_client: YFinanceClient) -> None:
        out = await earnings.get_earnings_calendar_impl({"symbol": "AAPL", "limit": 12})
        assert out["ok"] is True
        assert out["count"] == 3

    async def test_error(self, fake_ticker_factory: Any) -> None:
        def factory(symbol: str) -> MagicMock:
            m = fake_ticker_factory(symbol)
            m.get_earnings_dates.side_effect = RuntimeError("429 rate limit")
            return m

        set_client(YFinanceClient(ticker_factory=factory, timeout=5.0))
        out = await earnings.get_earnings_calendar_impl({"symbol": "AAPL"})
        _common.reset_client_singleton()
        assert out["error"]["reason"] == "rate_limited"

    async def test_with_cache_maps_columns(self, installed_client: YFinanceClient, tmp_cache: Any) -> None:
        out = await earnings.get_earnings_calendar_impl({"symbol": "AAPL"})
        assert out["_cache_status"] == "snapshot_written:3"
        eps = tmp_cache._conn.execute("SELECT eps_estimate FROM earnings_calendar ORDER BY eps_estimate").fetchall()
        assert eps[-1][0] == 2.1

    async def test_find_missing_returns_none(self, installed_client: YFinanceClient, tmp_cache: Any) -> None:
        # rows whose columns do not match any prefix -> None mapped values
        rows = earnings._to_cache_rows([{"index": "2026-01-30", "Other": 1}])
        assert rows[0]["eps_estimate"] is None


# ===========================================================================
# financials
# ===========================================================================
class TestFinancials:
    async def test_annual(self, installed_client: YFinanceClient) -> None:
        out = await financials.get_financial_statements_impl({"symbol": "AAPL", "period": "annual"})
        assert out["ok"] is True
        assert out["period"] == "annual"
        assert out["count"] == 4  # 2 line items x 2 periods

    async def test_quarterly(self, installed_client: YFinanceClient) -> None:
        out = await financials.get_financial_statements_impl({"symbol": "AAPL", "period": "quarterly"})
        assert out["period"] == "quarterly"

    async def test_error(self, fake_ticker_factory: Any) -> None:
        def factory(symbol: str) -> MagicMock:
            m = fake_ticker_factory(symbol)
            type(m).income_stmt = property(lambda self: (_ for _ in ()).throw(KeyError("boom")))
            return m

        set_client(YFinanceClient(ticker_factory=factory, timeout=5.0))
        out = await financials.get_financial_statements_impl({"symbol": "AAPL"})
        _common.reset_client_singleton()
        assert out["ok"] is False
        assert out["error"]["reason"] == "upstream_error"

    async def test_with_cache(self, installed_client: YFinanceClient, tmp_cache: Any) -> None:
        out = await financials.get_financial_statements_impl({"symbol": "AAPL"})
        assert out["_cache_status"] == "snapshot_written:4"

    def test_to_long_form_missing_attrs(self) -> None:
        obj = MagicMock()
        obj.columns = None
        obj.index = None
        assert financials._to_long_form(obj) == []

    def test_to_long_form_at_raises(self) -> None:
        df = pd.DataFrame({pd.Timestamp("2025-09-30"): [1.0]}, index=["Total Revenue"])
        wrapped = MagicMock(wraps=df)
        wrapped.columns = df.columns
        wrapped.index = df.index
        type(wrapped).at = property(lambda self: (_ for _ in ()).throw(ValueError("boom")))
        rows = financials._to_long_form(wrapped)
        assert rows[0]["value"] is None


# ===========================================================================
# recommendations
# ===========================================================================
class TestRecommendations:
    async def test_normal_with_upgrades(self, installed_client: YFinanceClient) -> None:
        out = await recommendations.get_analyst_recommendations_impl(
            {"symbol": "AAPL", "include_upgrades_downgrades": True}
        )
        assert out["ok"] is True
        assert len(out["upgrades_downgrades"]) == 2

    async def test_no_upgrades(self, installed_client: YFinanceClient) -> None:
        out = await recommendations.get_analyst_recommendations_impl(
            {"symbol": "AAPL", "include_upgrades_downgrades": False}
        )
        assert out["upgrades_downgrades"] == []

    async def test_summary_error(self, fake_ticker_factory: Any) -> None:
        def factory(symbol: str) -> MagicMock:
            m = fake_ticker_factory(symbol)
            type(m).recommendations_summary = property(lambda self: (_ for _ in ()).throw(ValueError("No data found")))
            return m

        set_client(YFinanceClient(ticker_factory=factory, timeout=5.0))
        out = await recommendations.get_analyst_recommendations_impl({"symbol": "ZZZZ"})
        _common.reset_client_singleton()
        assert out["ok"] is False

    async def test_upgrades_error_degrades(self, fake_ticker_factory: Any) -> None:
        def factory(symbol: str) -> MagicMock:
            m = fake_ticker_factory(symbol)
            type(m).upgrades_downgrades = property(lambda self: (_ for _ in ()).throw(RuntimeError("429")))
            return m

        set_client(YFinanceClient(ticker_factory=factory, timeout=5.0))
        out = await recommendations.get_analyst_recommendations_impl(
            {"symbol": "AAPL", "include_upgrades_downgrades": True}
        )
        _common.reset_client_singleton()
        # Summary succeeded, upgrades degraded to empty.
        assert out["ok"] is True
        assert out["upgrades_downgrades"] == []

    async def test_with_cache(self, installed_client: YFinanceClient, tmp_cache: Any) -> None:
        out = await recommendations.get_analyst_recommendations_impl({"symbol": "AAPL"})
        assert out["_cache_status"].startswith("snapshot_written:")

    def test_pick_missing(self) -> None:
        assert recommendations._pick({"a": 1}, "zzz") is None

    def test_summary_rows_to_cache(self) -> None:
        out = recommendations._summary_rows_to_cache([{"index": "0m"}])
        assert out == [{"kind": "summary", "rec_date": "0m"}]


# ===========================================================================
# meta
# ===========================================================================
class TestMeta:
    def test_health_check_ready(self) -> None:
        out = meta.health_check_impl()
        assert out["status"] == "ready"
        assert out["is_read_only"] is True
        assert out["data_is_realtime"] is False
        assert out["checks"]["network_checked"] is False
        assert "Terms-of-Service" in out["tos_notice"]

    def test_health_check_needs_install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import builtins

        real_import = builtins.__import__

        def fake_import(name: str, *a: Any, **k: Any) -> Any:
            if name == "yfinance":
                raise ImportError("no yfinance")
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        out = meta.health_check_impl()
        assert out["status"] == "needs_install"
        assert out["checks"]["yfinance_importable"] is False

    def test_get_server_info(self) -> None:
        out = meta.get_server_info_impl()
        assert out["name"] == "yfinance-mcp"
        assert out["version"] == "0.1.0"
        assert out["is_read_only"] is True
        assert out["data_is_realtime"] is False
        assert len(out["tools"]) == 6
        assert "Terms-of-Service" in out["tos_notice"]
