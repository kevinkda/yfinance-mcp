"""Pydantic v2 input schemas for yfinance-mcp tools.

Each schema validates MCP tool arguments before they reach the yfinance
client. Validation is intentionally strict (``extra="forbid"``, frozen) so
a malformed tool call fails fast client-side instead of producing an opaque
yfinance error.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------

# A ticker symbol. Yahoo symbols are uppercase alphanumerics plus a handful
# of punctuation marks (``.`` for class shares / exchanges, ``-`` for some
# ADR/preferred lines, ``^`` for indices, ``=`` for futures/FX). We keep the
# allowed set tight to reject obvious injection / garbage while still
# covering real Yahoo tickers (e.g. ``BRK-B``, ``^GSPC``, ``EURUSD=X``).
_SymbolStr = Annotated[
    str,
    Field(
        min_length=1,
        max_length=24,
        pattern=r"^[A-Za-z0-9.\-^=]+$",
        description="Yahoo Finance ticker symbol, e.g. AAPL, BRK-B, ^GSPC, EURUSD=X.",
    ),
]

_FinancialsPeriod = Literal["annual", "quarterly"]


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class _StrictModel(BaseModel):
    """Strict base — reject unknown fields and freeze on construction."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    @field_validator("*", mode="before")
    @classmethod
    def _upper_symbol(cls, value: object) -> object:
        # No-op for non-symbol fields; symbol normalisation happens per-field
        # below. Kept as a placeholder hook so subclasses stay uniform.
        return value


# ---------------------------------------------------------------------------
# Tool input schemas
# ---------------------------------------------------------------------------


class GetSplitsInput(_StrictModel):
    """Input for ``get_splits`` — historical stock-split events for a symbol."""

    symbol: _SymbolStr


class GetEarningsCalendarInput(_StrictModel):
    """Input for ``get_earnings_calendar`` — upcoming / past earnings dates."""

    symbol: _SymbolStr
    limit: int | None = Field(
        default=12,
        ge=1,
        le=100,
        description="Max number of earnings-date rows to return (default 12).",
    )


class GetFinancialStatementsInput(_StrictModel):
    """Input for ``get_financial_statements`` — income statement line items."""

    symbol: _SymbolStr
    period: _FinancialsPeriod = Field(
        default="annual",
        description="Reporting period granularity: 'annual' or 'quarterly'.",
    )


class GetAnalystRecommendationsInput(_StrictModel):
    """Input for ``get_analyst_recommendations`` — ratings + upgrades/downgrades."""

    symbol: _SymbolStr
    include_upgrades_downgrades: bool = Field(
        default=True,
        description="Also include the upgrades/downgrades history (default True).",
    )


__all__ = [
    "GetAnalystRecommendationsInput",
    "GetEarningsCalendarInput",
    "GetFinancialStatementsInput",
    "GetSplitsInput",
]
