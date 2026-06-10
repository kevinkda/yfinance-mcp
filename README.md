# yfinance-mcp

> **⚠️ TERMS-OF-SERVICE GRAY AREA — [docs/SECURITY.md](docs/SECURITY.md)**
>
> This server uses [`yfinance`](https://github.com/ranaroussi/yfinance),
> which **scrapes an undocumented Yahoo Finance endpoint**. Yahoo's Terms
> of Service prohibit redistribution and do not sanction automated
> scraping. **Personal, low-volume, research use ONLY** — not for
> commercial use or bulk redistribution. Data is **delayed (~15 min) and
> best-effort**, never real-time or authoritative. You assume the risk.
>
> **🔒 READ-ONLY** — no order / trade / write surface. yfinance is a
> data-scraping library and cannot place trades.

[![test](https://github.com/kevinkda/yfinance-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/kevinkda/yfinance-mcp/actions/workflows/test.yml)
[![CodeQL](https://github.com/kevinkda/yfinance-mcp/actions/workflows/codeql.yml/badge.svg)](https://github.com/kevinkda/yfinance-mcp/actions/workflows/codeql.yml)

[简体中文](README_zh.md)

`yfinance-mcp` is an MCP (Model Context Protocol) server that exposes a
small set of **read-only** Yahoo Finance data points to any MCP-compatible
LLM client (Claude Desktop, Cursor, etc.). It deliberately **supplements**
the companion read-only servers —
[`schwab-marketdata-mcp`](https://github.com/kevinkda/schwab-marketdata-mcp),
[`polygon-news-mcp`](https://github.com/kevinkda/polygon-news-mcp), and
[`sec-edgar-mcp`](https://github.com/kevinkda/sec-edgar-mcp) — by filling
the gaps they leave (stock splits, a simple earnings calendar, income
statements, and analyst recommendations). Prefer those licensed servers
wherever they cover the data you need.

## Tools (6)

### Data (4)

| Tool | Description |
| ---- | ----------- |
| `get_splits` | Historical stock-split events (date → split ratio). |
| `get_earnings_calendar` | Upcoming / past earnings dates with EPS estimate / reported / surprise%. |
| `get_financial_statements` | Income-statement line items (`period="annual"` or `"quarterly"`), wide + long form. |
| `get_analyst_recommendations` | Analyst rating summary + optional upgrades/downgrades history. |

### Meta (2)

| Tool | Description |
| ---- | ----------- |
| `health_check` | Readiness probe — confirms yfinance is importable **without** contacting Yahoo. |
| `get_server_info` | Server metadata — version, platform, `is_read_only: true`, `data_is_realtime: false`, ToS notice, tool list. |

## Install

```bash
git clone https://github.com/kevinkda/yfinance-mcp.git
cd yfinance-mcp
uv sync --extra dev
```

Requires Python ≥ 3.11. **No API key, no OAuth, no credentials** — yfinance
scrapes public Yahoo endpoints.

## Configure (optional)

There is nothing you *must* configure. If you want to tune the cache or
timeout, copy the example env file:

```bash
cp .env.example .env
# edit .env to set YFINANCE_CACHE_ENABLED, YFINANCE_TIMEOUT_SECONDS, etc.
```

## Run

```bash
uv run yfinance-mcp            # MCP stdio transport
# or
uv run python -m yfinance_mcp  # equivalent
```

Wire it into Claude Desktop / Cursor by pointing at the binary in the usual
MCP `command` + `args` shape.

## Cache

Fetched frames (splits / earnings / financials / recommendations) are
persisted as historical snapshots to a local DuckDB at
`~/.local/state/yfinance-mcp/cache.duckdb`, so your LLM agent can run
"what changed since last time" queries **without re-scraping Yahoo** (which
is both slow and ToS-sensitive). The cache is best-effort: any DuckDB error
is logged and the tool falls through to a live fetch. The cache is **opt-in
(default DISABLED)** — enable it with `YFINANCE_CACHE_ENABLED=true` (also
accepts `1` / `yes` / `on`).

## Security & Terms of Service

- **ToS gray area:** see [docs/SECURITY.md](docs/SECURITY.md) — the most
  important doc in this repo. Read it before deploying.
- **Threat model:** see [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).
- **Read-only:** no order / trade / write surface; client method
  allow-list in `src/yfinance_mcp/client.py`.
- **No credentials at rest:** nothing to leak.

## License

MIT — see [LICENSE](LICENSE). The MIT license covers *this code*; it does
**not** grant any right to Yahoo's data. See [docs/SECURITY.md](docs/SECURITY.md).
