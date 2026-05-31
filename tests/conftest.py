"""Shared fixtures for the yfinance-mcp test suite.

Every fixture here keeps tests **hermetic and network-free**:

* :func:`fake_ticker_factory` builds a ``ticker_factory`` that returns a
  :class:`unittest.mock.MagicMock` exposing the allow-listed read-only
  yfinance ``Ticker`` surface, backed by *canned* pandas frames. No
  :class:`yfinance.Ticker` is ever constructed, so **zero network calls**
  happen during the whole suite.
* :func:`installed_client` injects a :class:`YFinanceClient` built around
  the fake factory as the process-wide tools singleton.
* :func:`tmp_cache` roots a real :class:`Cache` at ``tmp_path`` so the
  DuckDB cache is exercised for real without touching ``$XDG_STATE_HOME``.

The autouse ``_hermetic_env`` fixture scrubs every ``YFINANCE_*`` env var,
chdirs into ``tmp_path`` (so ``bootstrap_dotenv`` cannot pick up the
developer's real ``.env``), and disables the cache by default. Tests that
want the cache opt in via the :func:`tmp_cache` fixture.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest

from yfinance_mcp import cache as cache_module
from yfinance_mcp.cache import Cache
from yfinance_mcp.client import YFinanceClient
from yfinance_mcp.tools import _common as tools_common

# ---------------------------------------------------------------------------
# Canned pandas frames — shaped exactly like the real yfinance returns but
# tiny and deterministic. Defined as factory functions so each test gets a
# fresh copy (pandas frames are mutable).
# ---------------------------------------------------------------------------


def canned_splits_series() -> pd.Series:
    """Series indexed by split date, value = split ratio (yfinance shape)."""
    idx = pd.to_datetime(["2014-06-09", "2020-08-31"])
    return pd.Series([7.0, 4.0], index=idx, name="Stock Splits")


def canned_earnings_frame() -> pd.DataFrame:
    """DataFrame indexed by earnings datetime (yfinance get_earnings_dates)."""
    idx = pd.to_datetime(["2026-01-30", "2025-10-30", "2025-07-31"])
    return pd.DataFrame(
        {
            "EPS Estimate": [2.10, 1.60, 1.40],
            "Reported EPS": [2.18, 1.64, 1.39],
            "Surprise(%)": [0.038, 0.025, -0.007],
        },
        index=idx,
    )


def canned_income_stmt() -> pd.DataFrame:
    """Income statement: index = line item, columns = period-end dates."""
    cols = pd.to_datetime(["2025-09-30", "2024-09-30"])
    return pd.DataFrame(
        {
            cols[0]: [394_328_000_000.0, 99_803_000_000.0],
            cols[1]: [383_285_000_000.0, 96_995_000_000.0],
        },
        index=["Total Revenue", "Net Income"],
    )


def canned_recommendations_summary() -> pd.DataFrame:
    """Analyst-rating summary frame (counts per period)."""
    return pd.DataFrame(
        {
            "period": ["0m", "-1m"],
            "strongBuy": [11, 12],
            "buy": [21, 20],
            "hold": [6, 6],
            "sell": [1, 1],
            "strongSell": [0, 0],
        }
    )


def canned_upgrades_downgrades() -> pd.DataFrame:
    """Upgrades/downgrades history frame, indexed by date."""
    idx = pd.to_datetime(["2026-01-15", "2025-12-01"])
    return pd.DataFrame(
        {
            "Firm": ["Morgan Stanley", "Goldman Sachs"],
            "ToGrade": ["Overweight", "Buy"],
            "FromGrade": ["Equal-Weight", "Neutral"],
            "Action": ["up", "up"],
        },
        index=idx,
    )


# ---------------------------------------------------------------------------
# Environment hygiene
# ---------------------------------------------------------------------------

_YF_ENV_VARS = (
    "YFINANCE_TIMEOUT_SECONDS",
    "YFINANCE_CACHE_ENABLED",
    "YFINANCE_CACHE_BYPASS",
    "YFINANCE_CACHE_PATH",
    "YFINANCE_MCP_DOTENV_LOADED",
)


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Scrub yfinance env, disable cache by default, and chdir to a sandbox.

    Also resets the cache + client singletons before and after each test so
    tests cannot leak shared global state into one another.
    """
    for var in _YF_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    # Cache disabled by default; tests opt in via ``tmp_cache``.
    monkeypatch.setenv("YFINANCE_CACHE_ENABLED", "0")
    monkeypatch.chdir(tmp_path)
    cache_module.reset_cache_singleton()
    tools_common.reset_client_singleton()
    try:
        yield
    finally:
        cache_module.reset_cache_singleton()
        tools_common.reset_client_singleton()
        os.environ.pop("YFINANCE_MCP_DOTENV_LOADED", None)


# ---------------------------------------------------------------------------
# Fake yfinance ticker_factory — the heart of the zero-network strategy
# ---------------------------------------------------------------------------


def _build_ticker_mock(symbol: str) -> MagicMock:
    """A MagicMock standing in for a yfinance ``Ticker`` with canned data."""
    mock = MagicMock(name=f"FakeTicker[{symbol}]")
    mock.symbol = symbol
    # Callable methods.
    mock.get_splits.return_value = canned_splits_series()
    mock.get_earnings_dates.return_value = canned_earnings_frame()
    mock.get_recommendations.return_value = canned_recommendations_summary()
    mock.get_calendar.return_value = {}
    # Property-style attributes (NOT callable).
    mock.income_stmt = canned_income_stmt()
    mock.quarterly_income_stmt = canned_income_stmt()
    mock.recommendations_summary = canned_recommendations_summary()
    mock.upgrades_downgrades = canned_upgrades_downgrades()
    return mock


@pytest.fixture
def fake_ticker_factory() -> Callable[[str], MagicMock]:
    """Return a ``ticker_factory`` yielding canned-data ticker mocks."""

    def _factory(symbol: str) -> MagicMock:
        return _build_ticker_mock(symbol)

    return _factory


@pytest.fixture
def fake_client(fake_ticker_factory: Callable[[str], MagicMock]) -> YFinanceClient:
    """A :class:`YFinanceClient` wired to the fake factory (fast timeout)."""
    return YFinanceClient(ticker_factory=fake_ticker_factory, timeout=5.0)


@pytest.fixture
def installed_client(fake_client: YFinanceClient) -> Iterator[YFinanceClient]:
    """Install ``fake_client`` as the process-wide tools singleton."""
    tools_common.set_client(fake_client)
    try:
        yield fake_client
    finally:
        tools_common.reset_client_singleton()


# ---------------------------------------------------------------------------
# DuckDB cache rooted in tmp_path
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Cache]:
    """A real :class:`Cache` rooted at ``tmp_path`` and installed as singleton."""
    monkeypatch.setenv("YFINANCE_CACHE_ENABLED", "1")
    cache_module.reset_cache_singleton()
    db_path = tmp_path / "cache.duckdb"
    cache = Cache(db_path=db_path)
    cache_module._cache_singleton = cache
    try:
        yield cache
    finally:
        cache_module.reset_cache_singleton()


@pytest.fixture
def make_ticker_mock() -> Callable[..., MagicMock]:
    """Factory for a custom ticker mock; override individual return values.

    Usage::

        mock = make_ticker_mock(get_splits=raising_callable)
    """

    def _make(**overrides: Any) -> MagicMock:
        mock = _build_ticker_mock("OVERRIDE")
        for attr, value in overrides.items():
            setattr(mock, attr, value)
        return mock

    return _make
