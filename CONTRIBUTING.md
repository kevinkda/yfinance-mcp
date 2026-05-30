# Contributing to yfinance-mcp

Thanks for considering a contribution! This is a **read-only** MCP server
that wraps `yfinance`. Two non-negotiables before you start:

1. **Read-only.** No order / trade / write / fund-movement surface, ever.
   yfinance is a data library; keep it that way.
2. **Terms-of-Service.** yfinance scrapes an undocumented Yahoo endpoint —
   a ToS gray area. Read [`docs/SECURITY.md`](docs/SECURITY.md). Changes
   must keep call volume low and must not enable bulk / commercial
   redistribution.

## Development setup

```bash
git clone https://github.com/kevinkda/yfinance-mcp
cd yfinance-mcp
uv sync --extra dev
uv run pre-commit install
```

No API key / credentials needed.

## Quality gates (must pass before PR)

- `uv run pytest --cov` — all tests pass (≥ 85% overall; target 100%).
- `uv run ruff check src tests` — 0 warnings.
- `uv run ruff format --check src tests` — must be formatted.
- `uv run mypy --strict src` — 0 errors.
- `uv run bandit -r src -lll` — 0 high.
- `uv run pip-audit` — 0 known vulnerabilities.
- `pre-commit run --all-files` — all hooks pass.

### Writing tests without hitting Yahoo

`YFinanceClient` takes an injectable `ticker_factory`. Inject a fake that
returns canned pandas frames and install it via
`tools._common.set_client(YFinanceClient(ticker_factory=fake))`. **Tests
must not make real network calls** (a `network` pytest marker exists for
the rare opt-in live test, skipped by default).

## What contributions are welcome

- Bug fixes, docs, additional tests, defensive-parsing hardening for
  yfinance schema drift.
- New **read-only** yfinance data tools that fill a genuine gap the
  companion licensed servers (`schwab-marketdata-mcp`, `polygon-news-mcp`,
  `sec-edgar-mcp`) do not cover. Add the method to `_READ_ONLY_METHODS`.
- Anything that increases call volume, enables redistribution, or adds a
  mutation surface — **out of scope**, will be rejected.

## Commit message style

Follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat(tools): add get_dividends read-only tool`
- `fix(common): tolerate renamed yfinance earnings column`
- `docs(security): clarify ToS personal-use constraint`

Subject ≤ 72 chars. Use English. Body explains *why*, not *what*.

## Branching

- `main` is the integration branch. PRs target `main`.
- **Never force-push `main`.**

## Inclusive language

Follow
[Amazon's inclusive language guidelines](https://aws.amazon.com/blogs/aws/blogpost-inclusive-language/).
Use `main` / `deny list` / `allow list` / `stop` instead of
`master` / `blacklist` / `whitelist` / `kill`. Self-audit before submitting.

## Security disclosures

Do **not** open a public issue for vulnerabilities. Use the GitHub private
security advisory flow:
<https://github.com/kevinkda/yfinance-mcp/security/advisories>.

## License

By submitting a PR, you agree your contribution will be licensed under MIT
(see [LICENSE](LICENSE)). MIT covers the code only — not Yahoo's data.
