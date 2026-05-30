# Threat model — yfinance-mcp

This document analyses the trust boundaries, the dominant
Terms-of-Service / scraping risk, and the dependency posture for
`yfinance-mcp`. It complements [SECURITY.md](SECURITY.md), which covers the
read-only contract and the ToS gray area in user-facing terms.

## 1. Assets

| Asset | Sensitivity |
| ----- | ----------- |
| Local DuckDB cache (`cache.duckdb`) | Low — contains only already-public Yahoo data, no secrets. chmod `0o600` on POSIX anyway. |
| The user's IP reputation with Yahoo | Medium — heavy scraping can get the IP rate-limited / blocked. |
| Legal standing under Yahoo ToS | Medium — using an unofficial scraper is a gray area; misuse (commercial, bulk redistribution) escalates the risk. |

Note there are **no credentials** in this server — no API key, no OAuth
token. There is nothing secret to exfiltrate. This is the main structural
difference from the Schwab servers' threat model.

## 2. Trust boundaries

```text
LLM host (Cursor / Claude)  --stdio-->  yfinance-mcp process
                                              |
                                              | yfinance (HTTPS, scraped)
                                              v
                                        Yahoo Finance (undocumented endpoint)
                                              |
                                              v
                                        DuckDB cache (local, 0o600)
```

- The **stdio boundary** carries only tool inputs (a symbol string + a few
  enum/int options, all Pydantic-validated) and JSON outputs.
- The **yfinance/HTTPS boundary** is outbound only and read-only.
- The **cache boundary** is local, best-effort, and non-authoritative.

## 3. Attacker model & mitigations

| Attacker / threat | Mitigation | Residual risk |
| ----------------- | ---------- | ------------- |
| Prompt-injected LLM tries to "trade" | No mutation tool exists; `YFinanceClient` allow-list rejects non-data methods | None — surface does not exist |
| Malicious symbol input (injection, traversal) | `_SymbolStr` Pydantic pattern `[A-Za-z0-9.\-^=]`, length ≤ 24 | Low |
| Unbounded / hanging upstream call | `asyncio.wait_for` timeout (default 30s) wraps every call | Low |
| Cache DB corruption / poisoning | Best-effort: corrupt DB quarantined + recreated; tools fall through to live fetch; cache is never trusted for correctness | Low |
| Supply-chain compromise of a dependency | CodeQL; dependabot; reusable CI runs bandit + pip-audit + gitleaks | Medium (see §4) |
| Yahoo blocks the user's IP | Low call volume + cache; **not eliminable** — inherent to scraping | Accepted |
| Yahoo changes/removes the endpoint | Pinned `yfinance` range; manual upgrade smoke test (see §4) | Accepted |

## 4. Dependency posture

### `yfinance` — the critical, fragile dependency

`yfinance` is the single load-bearing dependency and it is structurally
fragile because it scrapes an **undocumented** endpoint that Yahoo can
change at any time. Consequences:

- **Higher breakage rate than a normal library.** A patch release of
  `yfinance` can change column names or return shapes; a Yahoo-side change
  can break a `yfinance` version that previously worked.
- **Dependabot does NOT auto-PR `yfinance` major bumps** (see
  `.github/dependabot.yml`). A major bump must be done manually with a
  live smoke test:

  ```bash
  uv add 'yfinance@<new-version>'
  uv run python -c "import yfinance; t=yfinance.Ticker('AAPL'); \
      print(bool(len(t.get_splits())), t.income_stmt is not None)"
  uv run pytest        # all fakes must still pass (they pin our normalisation contract)
  ```

- Defensive parsing in `tools/_common.py` (`jsonify`, `dataframe_to_records`,
  `series_to_records`) is intentionally tolerant of column drift and
  bad/NaN values so that a minor Yahoo schema change degrades to partial
  data rather than a crash.

### `mcp` SDK

`mcp` 1.x → 2.x is a potential breaking bump; dependabot ignores the major
bump so it can be done deliberately with the SDK compatibility checklist.

### Others

`pydantic` (v2), `duckdb`, `python-dotenv` are mainstream, well-maintained
libraries; minor/patch bumps are grouped weekly by dependabot.

## 5. Terms-of-Service risk (the dominant risk)

This is covered in depth in [SECURITY.md](SECURITY.md#️-terms-of-service-gray-area-read-this-first).
In short: using `yfinance` is a gray area under Yahoo's ToS. This server
mitigates by (a) defaulting to a local cache to minimise call volume,
(b) declaring `data_is_realtime: false` + a `tos_notice` over JSON-RPC and
in the startup log, and (c) documenting the personal-use-only,
no-redistribution constraint prominently. It **cannot** make scraping
ToS-compliant — that residual risk is accepted by the operator who chooses
to deploy.

## 6. Out of scope

- Host compromise (RCE, malware): an attacker with shell can run yfinance
  directly; this server stores no secret and adds no privilege.
- Yahoo-side compromise or data falsification: out of our control;
  callers must treat the data as best-effort regardless.
- Making the ToS gray area "safe": not possible; documented and accepted.
