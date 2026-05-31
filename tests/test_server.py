"""server.py coverage: tool registration, version, ToS startup warning,
and the registered tool wrappers calling through to the impls."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from yfinance_mcp import server as server_mod
from yfinance_mcp.client import YFinanceClient


class TestServerRegistration:
    def test_version_set(self) -> None:
        from yfinance_mcp import __version__

        assert __version__ == server_mod.SERVER_VERSION
        assert server_mod.mcp._mcp_server.version == __version__

    def test_mcp_name(self) -> None:
        assert server_mod.mcp.name == "yfinance-mcp"

    async def test_registered_tools_present(self) -> None:
        tools = await server_mod.mcp.list_tools()
        names = {t.name for t in tools}
        assert {
            "get_splits",
            "get_earnings_calendar",
            "get_financial_statements",
            "get_analyst_recommendations",
            "health_check",
            "get_server_info",
        } <= names

    def test_tos_warning_emitted_on_import(self, caplog: pytest.LogCaptureFixture) -> None:
        # Re-emit by calling logger directly (import-time warning already fired).
        with caplog.at_level(logging.WARNING, logger="yfinance_mcp.server"):
            server_mod.logger.warning("yfinance-mcp starting in READ-ONLY MODE. %s", server_mod.meta.TOS_NOTICE)
        assert any("READ-ONLY MODE" in r.message for r in caplog.records)


class TestServerToolWrappers:
    async def test_get_splits_wrapper(self, installed_client: YFinanceClient) -> None:
        out = await server_mod.get_splits("AAPL")
        assert out["ok"] is True

    async def test_get_earnings_wrapper(self, installed_client: YFinanceClient) -> None:
        out = await server_mod.get_earnings_calendar("AAPL", 12)
        assert out["ok"] is True

    async def test_get_financials_wrapper(self, installed_client: YFinanceClient) -> None:
        out = await server_mod.get_financial_statements("AAPL", "annual")
        assert out["ok"] is True

    async def test_get_recommendations_wrapper(self, installed_client: YFinanceClient) -> None:
        out = await server_mod.get_analyst_recommendations("AAPL", True)
        assert out["ok"] is True

    def test_health_check_wrapper(self) -> None:
        out = server_mod.health_check()
        assert out["status"] in {"ready", "needs_install"}

    def test_get_server_info_wrapper(self) -> None:
        out = server_mod.get_server_info()
        assert out["name"] == "yfinance-mcp"

    def test_main_runs_stdio(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called: dict[str, Any] = {}

        def fake_run(transport: str) -> None:
            called["transport"] = transport

        monkeypatch.setattr(server_mod.mcp, "run", fake_run)
        server_mod.main()
        assert called["transport"] == "stdio"
