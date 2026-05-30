# Known Issues

Tracked known issues and limitations for `yfinance-mcp`. For resolved
issues see [docs/CHANGELOG.md](docs/CHANGELOG.md).

## Open / Accepted by design

### Terms-of-Service gray area (the big one)

`yfinance` scrapes an **undocumented** Yahoo Finance endpoint. Yahoo's ToS
prohibit redistribution and do not sanction automated scraping. This server
is **personal, low-volume, research use only** — not commercial, not bulk
redistribution. See [docs/SECURITY.md](docs/SECURITY.md). **Accepted by the
operator who deploys it**, not a defect this repo can fix.

### Data is delayed and best-effort

Yahoo data via yfinance is typically ~15-minutes delayed and carries no
accuracy or latency guarantee. `health_check` / `get_server_info` report
`data_is_realtime: false`. **Never use this server for real-time trading
decisions.** Not a bug.

### yfinance can rate-limit / block your IP (HTTP 429)

Heavy use can get your IP throttled or blocked by Yahoo. The DuckDB cache
exists to minimise call volume. Surfaced as `error.reason = "rate_limited"`.
Inherent to scraping; not eliminable.

### yfinance can break when Yahoo changes its site

Because the endpoint is undocumented, a Yahoo-side change can break a
previously-working `yfinance` version. Defensive parsing degrades to
partial data where possible; a full break surfaces as
`error.reason = "upstream_error"` or empty results. Tracked in
[docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) §4.

## Upstream / Deferred

- **`yfinance` is the single fragile dependency** — dependabot ignores
  `yfinance` major bumps; they require the manual upgrade smoke test in
  `docs/THREAT_MODEL.md` §4.
- **`mcp` 1.x → 2.x major bump deferred** — requires the SDK compatibility
  checklist; dependabot ignores the major bump.
- **PyPI publication deferred** — this is a personal-use server; publishing
  a ToS-gray-area scraper wrapper to PyPI is intentionally not done.
- **Tests (Phase 3) and release (Phase 4) pending** — scaffolding +
  source (Phases 1–2) are complete; the 100%-coverage test campaign
  (batch 4) and the first tagged release are handled by later siblings.

## Resolved

None yet — this is the initial scaffold (v0.1.0, pre-release).
