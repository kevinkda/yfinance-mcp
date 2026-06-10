# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1]

### Changed

- ⚠️ **BREAKING: DuckDB cache is now opt-in (default DISABLED).**
  `cache_enabled()` flips its default from `True` to `False`, so an
  unset `YFINANCE_CACHE_ENABLED` now yields **no cache** — no DuckDB file
  is created and every tool fetches live, reporting
  `_cache_status: "skipped:disabled"`. Re-enable explicitly with
  `YFINANCE_CACHE_ENABLED=true` (also accepts `1` / `yes` / `on`, case- and
  whitespace-insensitive). This zeroes the default on-disk footprint and
  removes implicit persistent state for fresh installs and CI. Tests,
  `.env.example`, `README.md`, and `README_zh.md` updated; 100% coverage
  preserved (truthy/falsy matrix + unset→`get_cache()` None gate added).

## [0.1.0]

### Added

- Initial release: read-only yfinance MCP server (splits, earnings,
  financials, recommendations) with a best-effort DuckDB snapshot cache.
