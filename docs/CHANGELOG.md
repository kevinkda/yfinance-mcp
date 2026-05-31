# Changelog

All notable changes to **yfinance-mcp** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The authoritative version lives in `src/yfinance_mcp/__init__.py` (`__version__`);
`pyproject.toml` carries a `0.0.0+dev` placeholder until the first tagged release
(see [docs/RELEASE.md](RELEASE.md)).

## [Unreleased]

## [0.1.0] — 2026-05-31

Initial tagged release. Read-only MCP server exposing Yahoo Finance data via
[`yfinance`](https://github.com/ranaroussi/yfinance) to supplement the
schwab / polygon / sec-edgar sibling servers (corporate splits, earnings
calendar, financial statements, analyst recommendations).

> **⚠️ Terms-of-Service gray area** — `yfinance` scrapes an undocumented
> Yahoo Finance endpoint. Personal, low-volume, research use only; data is
> delayed and best-effort. See [docs/SECURITY.md](SECURITY.md).

### Added

- **Infrastructure** — `.gitignore`, MIT `LICENSE`, `pyproject.toml`,
  `.pre-commit-config.yaml`, `.markdownlint-cli2.jsonc`, `.secrets.baseline`,
  `.env.example`.
- **CI/CD** — `.github/workflows/test.yml` (consumes the shared
  `reusable-mcp-ci@main` workflow), `codeql.yml`, `dependabot.yml`, issue
  templates, and a pull-request template.
- **Package** — `src/yfinance_mcp/`:
  - `__init__.py` (authoritative `__version__`), `__main__.py`, `bootstrap.py`,
    `_platform.py` (platform shim).
  - `client.py` — `YFinanceClient`, an async wrapper over `yfinance.Ticker`
    with a frozen read-only method allow-list, `asyncio.to_thread` offloading,
    a per-call timeout, normalised `YFinanceError` reasons, and an injectable
    `ticker_factory` for network-free testing.
  - `cache.py` — DuckDB cache schema for splits / earnings / financials /
    recommendations.
  - `models.py` — four Pydantic v2 input schemas.
  - `tools/` — four business tools (`splits`, `earnings`, `financials`,
    `recommendations`) plus two meta tools, sharing `_common.py` helpers.
  - `server.py` — FastMCP entrypoint that surfaces the ToS warning.
- **Docs** — `README.md`, `README_zh.md`, `docs/SECURITY.md`,
  `docs/REGISTER.md`, `docs/RELEASE.md`, `docs/THREAT_MODEL.md`,
  `CONTRIBUTING.md`, `KNOWN_ISSUES.md`, and this changelog.
- **Tests** — full suite of 308 tests reaching **100 % line + branch
  coverage** across every source module, driven entirely by an injected fake
  `ticker_factory` returning canned pandas frames (**zero real yfinance
  network calls**). Covers `client` / `cache` / `models` / all six tools /
  `server` / `meta` / `bootstrap` / `_platform`.
- **Security tests** — OWASP Top 10 for **2017, 2021, and 2025**, plus
  dedicated penetration, exception-path, and boundary-value suites. Each
  test asserts substantively; not-applicable categories (XSS, XXE, auth,
  crypto) carry explicit guards documenting why they do not apply to a
  read-only, no-credential, no-HTML/XML scraping server.

### Changed

- Coverage gate `fail_under` raised from `85` to **`100`** in
  `pyproject.toml`; the version placeholder advances from `0.0.0+dev` to
  `0.1.0`.
- `numpy` capped to `>=2.0,<2.3` (transitive via yfinance/pandas) so `uv
  sync` resolves a manylinux-wheel build instead of an sdist; `uv.lock`
  committed for reproducible CI.

### Security

- Read-only by construction: `yfinance` is a data-scraping library with no
  order / trade / write surface; the client additionally gates every call
  through `_READ_ONLY_METHODS`. The read-only + ToS contract is asserted by
  the OWASP 2025 / ToS test suite (`is_read_only=true`,
  `data_is_realtime=false`).
- ToS gray-zone declaration carried in the README banners,
  [docs/SECURITY.md](SECURITY.md), and [docs/THREAT_MODEL.md](THREAT_MODEL.md).

[Unreleased]: https://github.com/kevinkda/yfinance-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/kevinkda/yfinance-mcp/releases/tag/v0.1.0
