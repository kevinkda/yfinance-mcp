"""yfinance-mcp — read-only MCP server for Yahoo Finance data via yfinance.

Exposes four read-only data tools (stock splits, earnings calendar,
financial statements, analyst recommendations) plus two meta tools. It
supplements the companion read-only servers (``schwab-marketdata-mcp``,
``polygon-news-mcp``, ``sec-edgar-mcp``) by filling the gaps they leave.

.. warning::
    **Terms-of-Service gray area.** yfinance scrapes an *undocumented*
    Yahoo Finance endpoint. Yahoo's Terms of Service prohibit
    redistribution of its data and do not sanction programmatic scraping.
    This server is intended for **personal, low-volume, research use
    only**. It is NOT for commercial use or bulk redistribution. The data
    is delayed (typically ~15 minutes) and best-effort — never treat it as
    a real-time or authoritative feed. See ``docs/SECURITY.md``.
"""

__version__ = "0.1.1"
