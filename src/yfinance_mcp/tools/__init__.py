"""Tool entrypoints for yfinance-mcp.

All tools are read-only. yfinance exposes no mutation surface; the narrow
allow-list in :mod:`yfinance_mcp.client` keeps it that way.
"""

from . import earnings, financials, meta, recommendations, splits

__all__ = [
    "earnings",
    "financials",
    "meta",
    "recommendations",
    "splits",
]
