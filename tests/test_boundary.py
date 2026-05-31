"""Boundary-value tests: min/max/empty/None and frame-shape edges. Zero network."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest
from pydantic import ValidationError

from yfinance_mcp.cache import _to_float
from yfinance_mcp.client import YFinanceClient
from yfinance_mcp.models import GetEarningsCalendarInput, GetSplitsInput
from yfinance_mcp.tools import _common, earnings, financials, recommendations, splits
from yfinance_mcp.tools._common import dataframe_to_records, jsonify, series_to_records


class TestSymbolLengthBoundaries:
    def test_min_length_one(self) -> None:
        assert GetSplitsInput.model_validate({"symbol": "A"}).symbol == "A"

    def test_max_length_24(self) -> None:
        sym = "A" * 24
        assert GetSplitsInput.model_validate({"symbol": sym}).symbol == sym

    def test_length_25_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GetSplitsInput.model_validate({"symbol": "A" * 25})

    def test_length_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GetSplitsInput.model_validate({"symbol": ""})


class TestLimitBoundaries:
    @pytest.mark.parametrize("limit", [1, 2, 50, 99, 100])
    def test_in_range(self, limit: int) -> None:
        assert GetEarningsCalendarInput.model_validate({"symbol": "AAPL", "limit": limit}).limit == limit

    @pytest.mark.parametrize("limit", [0, -1, 101, 102, 10**9])
    def test_out_of_range(self, limit: int) -> None:
        with pytest.raises(ValidationError):
            GetEarningsCalendarInput.model_validate({"symbol": "AAPL", "limit": limit})

    def test_none_allowed(self) -> None:
        assert GetEarningsCalendarInput.model_validate({"symbol": "AAPL", "limit": None}).limit is None


class TestEmptyFrames:
    async def test_splits_empty_series(self, fake_ticker_factory: Any) -> None:
        def factory(symbol: str) -> MagicMock:
            m = fake_ticker_factory(symbol)
            m.get_splits.return_value = pd.Series([], dtype=float)
            return m

        _common.set_client(YFinanceClient(ticker_factory=factory, timeout=5.0))
        out = await splits.get_splits_impl({"symbol": "AAPL"})
        _common.reset_client_singleton()
        assert out["count"] == 0
        assert out["splits"] == []

    async def test_earnings_empty_frame(self, fake_ticker_factory: Any) -> None:
        def factory(symbol: str) -> MagicMock:
            m = fake_ticker_factory(symbol)
            m.get_earnings_dates.return_value = pd.DataFrame()
            return m

        _common.set_client(YFinanceClient(ticker_factory=factory, timeout=5.0))
        out = await earnings.get_earnings_calendar_impl({"symbol": "AAPL"})
        _common.reset_client_singleton()
        assert out["count"] == 0

    async def test_financials_none_frame(self, fake_ticker_factory: Any) -> None:
        def factory(symbol: str) -> MagicMock:
            m = fake_ticker_factory(symbol)
            m.income_stmt = None
            return m

        _common.set_client(YFinanceClient(ticker_factory=factory, timeout=5.0))
        out = await financials.get_financial_statements_impl({"symbol": "AAPL"})
        _common.reset_client_singleton()
        assert out["count"] == 0
        assert out["income_statement"] == []

    async def test_recommendations_empty(self, fake_ticker_factory: Any) -> None:
        def factory(symbol: str) -> MagicMock:
            m = fake_ticker_factory(symbol)
            m.recommendations_summary = pd.DataFrame()
            m.upgrades_downgrades = pd.DataFrame()
            return m

        _common.set_client(YFinanceClient(ticker_factory=factory, timeout=5.0))
        out = await recommendations.get_analyst_recommendations_impl({"symbol": "AAPL"})
        _common.reset_client_singleton()
        assert out["count"] == 0


class TestValueBoundaries:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (0, 0.0),
            (0.0, 0.0),
            (-1.5, -1.5),
            (1e308, 1e308),
            (None, None),
            ("", None),
            ("inf", float("inf")),  # _to_float does not special-case inf strings
        ],
    )
    def test_to_float_boundaries(self, value: Any, expected: Any) -> None:
        import math

        result = _to_float(value)
        if isinstance(expected, float) and math.isnan(expected):
            assert result is not None and math.isnan(result)
        else:
            assert result == expected

    def test_jsonify_nan_to_none(self) -> None:
        assert jsonify(float("nan")) is None

    def test_jsonify_inf_to_none(self) -> None:
        assert jsonify(float("inf")) is None
        assert jsonify(float("-inf")) is None

    def test_jsonify_zero(self) -> None:
        assert jsonify(0) == 0
        assert jsonify(0.0) == 0.0


class TestSingleRowFrames:
    def test_series_single_item(self) -> None:
        s = pd.Series([4.0], index=pd.to_datetime(["2020-08-31"]))
        recs = series_to_records(s, key_name="d", value_name="r")
        assert len(recs) == 1

    def test_dataframe_single_cell(self) -> None:
        df = pd.DataFrame({"A": [1]}, index=["x"])
        recs = dataframe_to_records(df)
        assert recs == [{"index": "x", "A": 1}]

    def test_dataframe_with_nan_cell(self) -> None:
        df = pd.DataFrame({"A": [float("nan")]}, index=["x"])
        recs = dataframe_to_records(df)
        assert recs[0]["A"] is None
