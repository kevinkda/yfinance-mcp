"""Core 100%-coverage tests for yfinance-mcp.

Exercises client.py, cache.py, models.py, tools/* and meta with canned
pandas frames via the fake ticker_factory — zero network calls. Error
branches use monkeypatch + MagicMock(wraps=real) per the batch-1 template.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest

from yfinance_mcp.client import (
    _READ_ONLY_METHODS,
    YFinanceClient,
    YFinanceError,
    _default_ticker_factory,
    _timeout_seconds,
)


# ===========================================================================
# client.py
# ===========================================================================
class TestClient:
    async def test_get_splits_call(self, fake_client: YFinanceClient) -> None:
        series = await fake_client.call("AAPL", "get_splits")
        assert len(series) == 2

    async def test_property_attr_not_called(self, fake_client: YFinanceClient) -> None:
        # income_stmt is a property (not callable) — returned as-is.
        frame = await fake_client.call("AAPL", "income_stmt")
        assert isinstance(frame, pd.DataFrame)

    async def test_blocked_method(self, fake_client: YFinanceClient) -> None:
        with pytest.raises(YFinanceError) as ei:
            await fake_client.call("AAPL", "history")
        assert ei.value.reason == "blocked_method"

    async def test_blocked_write_verb(self, fake_client: YFinanceClient) -> None:
        for verb in ("download", "place_order", "set_proxy", "__init__"):
            with pytest.raises(YFinanceError) as ei:
                await fake_client.call("AAPL", verb)
            assert ei.value.reason == "blocked_method"

    async def test_rate_limited(self, fake_ticker_factory: Any) -> None:
        def factory(symbol: str) -> MagicMock:
            m = fake_ticker_factory(symbol)
            m.get_splits.side_effect = RuntimeError("HTTP 429 Too Many Requests")
            return m

        client = YFinanceClient(ticker_factory=factory, timeout=5.0)
        with pytest.raises(YFinanceError) as ei:
            await client.call("AAPL", "get_splits")
        assert ei.value.reason == "rate_limited"

    async def test_not_found(self, fake_ticker_factory: Any) -> None:
        def factory(symbol: str) -> MagicMock:
            m = fake_ticker_factory(symbol)
            m.get_splits.side_effect = ValueError("No data found, symbol may be delisted")
            return m

        client = YFinanceClient(ticker_factory=factory, timeout=5.0)
        with pytest.raises(YFinanceError) as ei:
            await client.call("ZZZZ", "get_splits")
        assert ei.value.reason == "not_found"

    async def test_not_found_404(self, fake_ticker_factory: Any) -> None:
        def factory(symbol: str) -> MagicMock:
            m = fake_ticker_factory(symbol)
            m.get_splits.side_effect = RuntimeError("404 Client Error")
            return m

        client = YFinanceClient(ticker_factory=factory, timeout=5.0)
        with pytest.raises(YFinanceError) as ei:
            await client.call("ZZZZ", "get_splits")
        assert ei.value.reason == "not_found"

    async def test_upstream_error(self, fake_ticker_factory: Any) -> None:
        def factory(symbol: str) -> MagicMock:
            m = fake_ticker_factory(symbol)
            m.get_splits.side_effect = KeyError("weird internal key")
            return m

        client = YFinanceClient(ticker_factory=factory, timeout=5.0)
        with pytest.raises(YFinanceError) as ei:
            await client.call("AAPL", "get_splits")
        assert ei.value.reason == "upstream_error"

    async def test_timeout(self, fake_ticker_factory: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        import yfinance_mcp.client as client_mod

        async def fake_wait_for(coro: Any, timeout: float) -> Any:  # noqa: ASYNC109
            # Close the wrapped coroutine so it is not left un-awaited (which
            # would emit a RuntimeWarning promoted to an error by filterwarnings).
            coro.close()
            raise TimeoutError

        monkeypatch.setattr(client_mod.asyncio, "wait_for", fake_wait_for)
        client = YFinanceClient(ticker_factory=fake_ticker_factory, timeout=0.01)
        with pytest.raises(YFinanceError) as ei:
            await client.call("AAPL", "get_splits")
        assert ei.value.reason == "timeout"

    def test_error_str(self) -> None:
        exc = YFinanceError("not_found", "detail here")
        assert "not_found" in str(exc)
        assert exc.detail == "detail here"

    def test_default_factory_imports_yfinance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Inject a fake ``yfinance`` module so the default factory exercises
        # its ``import yfinance`` + ``Ticker(symbol)`` path with zero network
        # and no real-session resource warnings.
        import sys

        sentinel = MagicMock(name="yf.Ticker.instance")
        fake_yf = MagicMock(name="fake_yfinance_module")
        fake_yf.Ticker.return_value = sentinel
        monkeypatch.setitem(sys.modules, "yfinance", fake_yf)
        assert _default_ticker_factory("AAPL") is sentinel
        fake_yf.Ticker.assert_called_once_with("AAPL")

    def test_timeout_seconds_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("YFINANCE_TIMEOUT_SECONDS", raising=False)
        assert _timeout_seconds() == 30.0

    def test_timeout_seconds_custom(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("YFINANCE_TIMEOUT_SECONDS", "12.5")
        assert _timeout_seconds() == 12.5

    def test_timeout_seconds_invalid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("YFINANCE_TIMEOUT_SECONDS", "not-a-number")
        assert _timeout_seconds() == 30.0

    def test_timeout_seconds_nonpositive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("YFINANCE_TIMEOUT_SECONDS", "-5")
        assert _timeout_seconds() == 30.0

    def test_default_timeout_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("YFINANCE_TIMEOUT_SECONDS", "7")
        client = YFinanceClient(ticker_factory=lambda s: MagicMock())
        assert client._timeout == 7.0

    async def test_inner_yfinance_error_reraised(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # If the factory/invoke raises a YFinanceError, it must propagate
        # unchanged (line 147: ``except YFinanceError: raise``).
        def factory(symbol: str) -> Any:
            raise YFinanceError("not_found", "inner")

        client = YFinanceClient(ticker_factory=factory, timeout=5.0)
        with pytest.raises(YFinanceError) as ei:
            await client.call("AAPL", "get_splits")
        assert ei.value.reason == "not_found"
        assert ei.value.detail == "inner"

    def test_allow_list_frozen(self) -> None:
        assert isinstance(_READ_ONLY_METHODS, frozenset)
        assert "get_splits" in _READ_ONLY_METHODS
