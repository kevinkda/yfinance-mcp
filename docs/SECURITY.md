# Security model — yfinance-mcp

`yfinance-mcp` is a **read-only** MCP server. It surfaces Yahoo Finance
data (stock splits, earnings calendar, income statements, analyst
recommendations) to LLM agents via the [`yfinance`](https://github.com/ranaroussi/yfinance)
library. It has no order, mutation, write, or fund-movement surface of any
kind — yfinance is a data-scraping library and cannot place trades.

This document covers two things: (1) the **Terms-of-Service gray area**
that is the dominant risk for this server, and (2) the conventional
read-only / threat-model posture.

## ⚠️ Terms-of-Service gray area (read this first)

**`yfinance` scrapes an *undocumented* Yahoo Finance endpoint.** Yahoo does
not publish a public, free, programmatic data API for this data, and its
Terms of Service:

- **prohibit redistribution** of Yahoo Finance data, and
- **do not sanction automated scraping** of the site.

`yfinance` works by mimicking browser requests against internal Yahoo
endpoints that can change or disappear without notice. Using it therefore
sits in a **legal / ToS gray area**.

### What this means for you

This server is provided for **personal, low-volume, research and
educational use only**. By running it you accept the following constraints:

| Constraint | Rationale |
| ---------- | --------- |
| **Personal use only.** Do not use this server in a commercial product or service. | Yahoo's ToS prohibits commercial use of scraped data. |
| **No redistribution.** Do not re-publish, resell, or bulk-export the data this server returns. | Yahoo's ToS prohibits redistribution. |
| **Low volume.** Keep call frequency modest; do not loop over thousands of symbols. | High volume risks IP blocks (HTTP 429) and is more clearly abusive under the ToS. The DuckDB cache exists precisely to avoid re-fetching. |
| **Data is delayed & best-effort.** Treat every value as ~15-minutes delayed and possibly stale or wrong. | yfinance is unofficial; Yahoo gives no accuracy or latency guarantee. **Never** use this for real-time trading decisions. |
| **You assume the risk.** Yahoo may block your IP, and the scraped endpoint may break at any `yfinance` or Yahoo change. | This is the nature of an unofficial scraper. |

If you need a sanctioned, real-time, redistributable feed, use a paid
market-data vendor with a proper API and license. The companion
[`schwab-marketdata-mcp`](https://github.com/kevinkda/schwab-marketdata-mcp)
and [`polygon-news-mcp`](https://github.com/kevinkda/polygon-news-mcp)
servers wrap *licensed* APIs and should be preferred wherever they cover
the data you need; `yfinance-mcp` exists only to fill the gaps they leave.

### `data_is_realtime: false`

Both meta tools (`health_check`, `get_server_info`) return
`data_is_realtime: false` and a `tos_notice` string over JSON-RPC, and the
server emits a startup `WARNING` with the same notice, so a calling agent
(or a human reviewer) can sanity-check the contract before relying on the
data.

## Read-only posture

### No mutation surface exists

yfinance has no trading / order / write API. This server's tool surface is
limited to four read-only data tools plus two meta tools (see
`get_server_info`). The `YFinanceClient` wrapper
(`src/yfinance_mcp/client.py`) additionally gates every call through a
frozen `_READ_ONLY_METHODS` allow-list and raises `YFinanceError(reason=
"blocked_method")` for anything not on it — defence-in-depth against a
future refactor accidentally reaching for some new yfinance helper.

### No credentials at rest

Unlike the Schwab servers, yfinance-mcp stores **no API key, no OAuth
token, no secret of any kind**. There is no credential file to leak. The
only local state is the best-effort DuckDB cache of already-public data.

## Threat model

### In scope

| Threat | Mitigation |
| ------ | ---------- |
| LLM is jailbroken / prompt-injected into "trading" | No mutation tool exists; the client allow-list rejects non-data methods |
| Malicious dependency added via PR | CodeQL workflow; dependabot; reusable CI (bandit + pip-audit + gitleaks) |
| Cache DB corruption | Best-effort: corrupt DB is quarantined aside and recreated; tools fall through to live fetch |
| Untrusted symbol input (injection) | Pydantic `_SymbolStr` pattern restricts symbols to `[A-Za-z0-9.\-^=]` |
| Unbounded yfinance call hanging the event loop | Every call is `asyncio.wait_for`-bounded (default 30s, `YFINANCE_TIMEOUT_SECONDS`) |

### Out of scope

| Threat | Why not |
| ------ | ------- |
| Yahoo blocks your IP (HTTP 429) | Inherent to scraping; mitigated by low volume + cache, not eliminable |
| Yahoo changes / removes the scraped endpoint | Upstream `yfinance` breakage; tracked in `docs/THREAT_MODEL.md` |
| Host compromise (RCE, malware) | Attacker can run yfinance directly; this server adds no secret to steal |
| Legal action over ToS violation | You accept the gray-area risk by deploying; this server cannot make scraping ToS-compliant |

### `yfinance` upstream risk

`yfinance` is the single critical dependency and it scrapes an
undocumented endpoint, so it breaks more often than a normal library. See
`docs/THREAT_MODEL.md` for the bus-factor and upgrade-discipline analysis.
Dependabot is configured to **not** auto-PR `yfinance` major bumps — those
require a manual smoke test against live symbols first.

## Reporting security issues

Open a private security advisory on GitHub:
<https://github.com/kevinkda/yfinance-mcp/security/advisories>. Do **not**
open a public issue with the details.
