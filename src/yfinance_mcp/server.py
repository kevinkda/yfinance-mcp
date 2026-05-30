"""yfinance-mcp MCP server entrypoint.

READ-ONLY market data via yfinance.

.. warning::
    **Terms-of-Service gray area.** yfinance scrapes an undocumented Yahoo
    Finance endpoint. This server is for personal, low-volume research use
    only — not commercial use or bulk redistribution. Data is delayed
    (~15 min) and best-effort. See ``docs/SECURITY.md``.

The first thing this module does at import time is bootstrap ``.env`` so
optional tuning knobs (cache controls, timeout, log level) are present
before any tool runs. It then emits a startup WARNING declaring the
read-only + ToS contract.
"""

from __future__ import annotations

from . import bootstrap

bootstrap.bootstrap_dotenv()

import logging  # noqa: E402
from typing import Any  # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402

from . import __version__ as SERVER_VERSION  # noqa: E402
from .tools import earnings, financials, meta, recommendations, splits  # noqa: E402

logger = logging.getLogger(__name__)
logger.warning("yfinance-mcp starting in READ-ONLY MODE. %s", meta.TOS_NOTICE)

mcp: FastMCP = FastMCP("yfinance-mcp")
mcp._mcp_server.version = SERVER_VERSION


# ---------------------------------------------------------------------------
# Tool registrations — each delegates to the async ``*_impl`` in
# ``yfinance_mcp.tools.<module>``. This file is the single source of truth
# for the MCP tool surface.
# ---------------------------------------------------------------------------


@mcp.tool(
    name="get_splits",
    description="Historical stock-split events for a symbol (date -> split ratio). Read-only Yahoo Finance data.",
)
async def get_splits(symbol: str) -> dict[str, Any]:
    return await splits.get_splits_impl({"symbol": symbol})


@mcp.tool(
    name="get_earnings_calendar",
    description=(
        "Upcoming and past earnings dates for a symbol, with EPS estimate / "
        "reported EPS / surprise%. Read-only Yahoo Finance data."
    ),
)
async def get_earnings_calendar(symbol: str, limit: int | None = 12) -> dict[str, Any]:
    return await earnings.get_earnings_calendar_impl({"symbol": symbol, "limit": limit})


@mcp.tool(
    name="get_financial_statements",
    description=(
        "Income-statement line items for a symbol (period='annual' or "
        "'quarterly'). Returns both wide and long-form rows. Read-only "
        "Yahoo Finance data."
    ),
)
async def get_financial_statements(symbol: str, period: str = "annual") -> dict[str, Any]:
    return await financials.get_financial_statements_impl({"symbol": symbol, "period": period})


@mcp.tool(
    name="get_analyst_recommendations",
    description=(
        "Analyst rating summary (strongBuy/buy/hold/sell counts) plus "
        "optional upgrades/downgrades history for a symbol. Read-only Yahoo "
        "Finance data."
    ),
)
async def get_analyst_recommendations(
    symbol: str,
    include_upgrades_downgrades: bool = True,
) -> dict[str, Any]:
    return await recommendations.get_analyst_recommendations_impl(
        {"symbol": symbol, "include_upgrades_downgrades": include_upgrades_downgrades}
    )


@mcp.tool(
    name="health_check",
    description="Lightweight readiness check; confirms yfinance is importable without contacting Yahoo.",
)
def health_check() -> dict[str, Any]:
    return meta.health_check_impl()


@mcp.tool(
    name="get_server_info",
    description="Server metadata — version, platform, read-only declaration, ToS notice, tool list.",
)
def get_server_info() -> dict[str, Any]:
    return meta.get_server_info_impl()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover
    main()
