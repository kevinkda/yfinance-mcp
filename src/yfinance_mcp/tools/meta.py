"""``health_check`` and ``get_server_info`` meta tools."""

from __future__ import annotations

import platform
import sys
from datetime import UTC, datetime
from typing import Any

from .. import __version__

#: The four data tools + two meta tools this server registers.
TOOL_NAMES = (
    "get_splits",
    "get_earnings_calendar",
    "get_financial_statements",
    "get_analyst_recommendations",
    "health_check",
    "get_server_info",
)

#: Single source of truth for the Terms-of-Service banner string, reused by
#: the server startup log and the meta tools.
TOS_NOTICE = (
    "yfinance scrapes an undocumented Yahoo Finance endpoint; use is a "
    "Terms-of-Service gray area. Personal, low-volume, research use only. "
    "Data is delayed (~15 min) and best-effort — not real-time or "
    "authoritative. See docs/SECURITY.md."
)


def health_check_impl(_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Lightweight readiness check.

    Confirms yfinance is importable and reports its version **without making
    a network call** (yfinance has no credentials / token to verify, and we
    deliberately avoid hammering Yahoo on every health probe).
    """
    yfinance_version: str | None = None
    yfinance_importable = False
    try:
        import yfinance

        yfinance_importable = True
        yfinance_version = getattr(yfinance, "__version__", None)
    except ImportError:
        yfinance_importable = False

    status = "ready" if yfinance_importable else "needs_install"

    return {
        "status": status,
        "is_read_only": True,
        "data_is_realtime": False,
        "tos_notice": TOS_NOTICE,
        "checks": {
            "yfinance_importable": yfinance_importable,
            "yfinance_version": yfinance_version,
            "network_checked": False,
        },
        "checked_at": datetime.now(UTC).isoformat(),
    }


def get_server_info_impl(_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Server metadata — version, platform, read-only + ToS declaration."""
    return {
        "name": "yfinance-mcp",
        "version": __version__,
        "is_read_only": True,
        "data_is_realtime": False,
        "data_source": "Yahoo Finance (via yfinance, undocumented endpoint)",
        "tos_notice": TOS_NOTICE,
        "tools": list(TOOL_NAMES),
        "python_version": sys.version,
        "platform": platform.platform(),
        "security_doc": "docs/SECURITY.md",
    }
