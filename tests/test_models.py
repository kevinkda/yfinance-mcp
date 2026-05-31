"""Pydantic input-schema validation tests for yfinance-mcp models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from yfinance_mcp.models import (
    GetAnalystRecommendationsInput,
    GetEarningsCalendarInput,
    GetFinancialStatementsInput,
    GetSplitsInput,
)


class TestGetSplitsInput:
    def test_valid(self) -> None:
        m = GetSplitsInput.model_validate({"symbol": "AAPL"})
        assert m.symbol == "AAPL"

    def test_strips_whitespace(self) -> None:
        assert GetSplitsInput.model_validate({"symbol": "  AAPL  "}).symbol == "AAPL"

    @pytest.mark.parametrize("sym", ["BRK-B", "^GSPC", "EURUSD=X", "BRK.B", "aapl"])
    def test_real_yahoo_symbols(self, sym: str) -> None:
        assert GetSplitsInput.model_validate({"symbol": sym}).symbol == sym

    @pytest.mark.parametrize("sym", ["", "A" * 25, "AAPL;DROP", "AA PL", "../etc", "<script>", "AA$PL"])
    def test_rejects_bad_symbols(self, sym: str) -> None:
        with pytest.raises(ValidationError):
            GetSplitsInput.model_validate({"symbol": sym})

    def test_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            GetSplitsInput.model_validate({"symbol": "AAPL", "evil": 1})

    def test_frozen(self) -> None:
        m = GetSplitsInput.model_validate({"symbol": "AAPL"})
        with pytest.raises(ValidationError):
            m.symbol = "MSFT"  # type: ignore[misc]


class TestGetEarningsCalendarInput:
    def test_default_limit(self) -> None:
        assert GetEarningsCalendarInput.model_validate({"symbol": "AAPL"}).limit == 12

    def test_custom_limit(self) -> None:
        assert GetEarningsCalendarInput.model_validate({"symbol": "AAPL", "limit": 50}).limit == 50

    def test_limit_none(self) -> None:
        assert GetEarningsCalendarInput.model_validate({"symbol": "AAPL", "limit": None}).limit is None

    @pytest.mark.parametrize("bad", [0, -1, 101, 1000])
    def test_limit_out_of_range(self, bad: int) -> None:
        with pytest.raises(ValidationError):
            GetEarningsCalendarInput.model_validate({"symbol": "AAPL", "limit": bad})

    @pytest.mark.parametrize("edge", [1, 100])
    def test_limit_boundaries_ok(self, edge: int) -> None:
        assert GetEarningsCalendarInput.model_validate({"symbol": "AAPL", "limit": edge}).limit == edge


class TestGetFinancialStatementsInput:
    def test_default_period(self) -> None:
        assert GetFinancialStatementsInput.model_validate({"symbol": "AAPL"}).period == "annual"

    @pytest.mark.parametrize("period", ["annual", "quarterly"])
    def test_valid_periods(self, period: str) -> None:
        assert GetFinancialStatementsInput.model_validate({"symbol": "AAPL", "period": period}).period == period

    def test_invalid_period(self) -> None:
        with pytest.raises(ValidationError):
            GetFinancialStatementsInput.model_validate({"symbol": "AAPL", "period": "monthly"})


class TestGetAnalystRecommendationsInput:
    def test_default_include(self) -> None:
        assert GetAnalystRecommendationsInput.model_validate({"symbol": "AAPL"}).include_upgrades_downgrades is True

    def test_false_include(self) -> None:
        m = GetAnalystRecommendationsInput.model_validate({"symbol": "AAPL", "include_upgrades_downgrades": False})
        assert m.include_upgrades_downgrades is False
