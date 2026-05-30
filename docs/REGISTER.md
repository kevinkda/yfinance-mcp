# Setup — yfinance-mcp

Unlike the companion Schwab / Polygon servers, **yfinance-mcp needs no
registration, no API key, and no OAuth.** This page exists to make that
explicit and to point you at the licensed alternatives where they apply.

## There is nothing to register

`yfinance` scrapes public Yahoo Finance pages. There is no developer
portal to sign up for, no app to create, no key to paste. Setup is just:

```bash
git clone https://github.com/kevinkda/yfinance-mcp.git
cd yfinance-mcp
uv sync --extra dev
uv run yfinance-mcp   # done
```

## Why no key? (and the catch)

Yahoo does not offer a free, public, documented market-data API for this
data. `yfinance` works by mimicking the browser requests the Yahoo Finance
website itself makes. That is convenient — but it is also why:

- it can **break without notice** when Yahoo changes its site,
- it can **rate-limit / block your IP** (HTTP 429) under heavy use,
- it is a **Terms-of-Service gray area** (see
  [SECURITY.md](SECURITY.md)).

So "no key" is not free lunch — it is an unofficial, best-effort,
personal-use-only data path. Keep volume low; the DuckDB cache exists to
help you avoid re-fetching.

## When to use a licensed server instead

Prefer these wherever they cover what you need — they wrap *licensed* APIs
and are not ToS gray areas:

| Need | Use |
| ---- | --- |
| Real-time / delayed quotes, price history, option chains, market hours | [`schwab-marketdata-mcp`](https://github.com/kevinkda/schwab-marketdata-mcp) |
| Your own account positions / orders / transactions | [`schwab-positions-mcp`](https://github.com/kevinkda/schwab-positions-mcp) |
| News headlines & articles | [`polygon-news-mcp`](https://github.com/kevinkda/polygon-news-mcp) |
| SEC filings (10-K / 10-Q / 8-K / Form 4) | [`sec-edgar-mcp`](https://github.com/kevinkda/sec-edgar-mcp) |
| **Gaps the above leave** — splits, simple earnings calendar, income statement, analyst recs | **this server** |

## Optional configuration

See [`.env.example`](../.env.example). Everything is optional:

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `YFINANCE_CACHE_ENABLED` | `1` | Set `0` to disable the DuckDB snapshot cache. |
| `YFINANCE_CACHE_BYPASS` | `0` | Set `1` to always fetch live (still writes the cache). |
| `YFINANCE_CACHE_PATH` | `${XDG_STATE_HOME}/yfinance-mcp/cache.duckdb` | Override cache DB location. |
| `YFINANCE_TIMEOUT_SECONDS` | `30` | Per-call timeout for the wrapped yfinance request. |
| `LOG_LEVEL` | `WARNING` | stderr log level. |
