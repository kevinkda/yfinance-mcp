# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-06-15

### Changed

- ⚠️ **BREAKING: the embedded DuckDB cache is removed and replaced by a
  pluggable cache backend (v0.7 T0).** Storage is selected via
  `YFINANCE_CACHE_BACKEND`:
  - **memory** (default) — in-process, zero external dependency,
    concurrency-safe, non-blocking. Removes the single-connection DuckDB +
    global `RLock`, the on-disk `cache.duckdb` file, file locks, the
    corrupt-DB quarantine machinery, the `cache_events` audit table, and the
    `YFINANCE_CACHE_PATH` override. Keeps **no durable history**, so snapshot
    writes report `snapshot_written:0` (graceful degradation).
  - **clickhouse** (opt-in) — `pip install yfinance-mcp[clickhouse]` with
    `YFINANCE_CLICKHOUSE_URL` and `YFINANCE_CACHE_BACKEND=clickhouse` to
    durably persist the splits / earnings / financials / recommendations
    history.
- **Removed the `duckdb` runtime dependency.** ClickHouse is an opt-in
  `[clickhouse]` extra only; the default install ships with **zero new
  dependencies** (the `numpy<2.3` cap for the yfinance/pandas toolchain is
  retained) and works out of the box.
- The snapshot-write public API (`write_splits` / `write_earnings_calendar` /
  `write_financials` / `write_recommendations`) is unchanged — all tools are
  unaffected.
- 100% line+branch coverage preserved (memory degradation, ClickHouse via a
  mocked client, factory fallback, backend error paths).

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
