# Release process — yfinance-mcp

This is the release runbook. Phases 1–2 (scaffold + source) are complete;
**Phase 3 (tests) and Phase 4 (release) are done by later siblings** — this
doc is the checklist they will follow.

## Versioning

- Semantic versioning: `MAJOR.MINOR.PATCH`.
- The authoritative version lives in **`src/yfinance_mcp/__init__.py`**
  (`__version__`), which is wired into `mcp._mcp_server.version` in
  `server.py`. The current source version is `0.1.0`.
- `pyproject.toml` carries a placeholder `0.0.0+dev` until the first tagged
  release, at which point Phase 4 syncs it to the `__init__` version.

## Pre-release checklist (Phase 3 must be green first)

- [ ] `uv run pytest --cov` — all tests pass, coverage ≥ 85% (target 100%
      for the batch-4 campaign).
- [ ] `uv run ruff check src tests` — clean.
- [ ] `uv run ruff format --check src tests` — clean.
- [ ] `uv run mypy --strict src` — clean.
- [ ] `uv run bandit -r src -lll` — 0 high.
- [ ] `uv run pip-audit` — 0 known vulnerabilities.
- [ ] `pre-commit run --all-files` — all hooks pass.
- [ ] A live smoke test against a real symbol (e.g. `AAPL`) for each of the
      4 data tools, run **manually and once** (do not loop — ToS / rate
      limits).
- [ ] `docs/CHANGELOG.md` updated: move `## [Unreleased]` entries under a
      new `## [X.Y.Z] - YYYY-MM-DD` heading.
- [ ] `docs/SECURITY.md` ToS notice reviewed and still accurate.

## Cut the release (Phase 4)

```bash
# 1. Sync versions
#    - bump src/yfinance_mcp/__init__.py __version__ to X.Y.Z
#    - set pyproject.toml version = "X.Y.Z"
# 2. Commit
git add src/yfinance_mcp/__init__.py pyproject.toml docs/CHANGELOG.md
git commit -m "chore(release): vX.Y.Z"
# 3. Tag (annotated)
git tag -a vX.Y.Z -m "yfinance-mcp vX.Y.Z"
# 4. Push
git push origin main
git push origin vX.Y.Z
# 5. GitHub release from the tag, body = the CHANGELOG section
~/bin/gh release create vX.Y.Z --title "vX.Y.Z" --notes-file <(...)
```

## Post-release

- [ ] Verify the `test` and `CodeQL` workflows pass on the tagged commit.
- [ ] Confirm `get_server_info` reports the new version.
- [ ] (If publishing to PyPI later) — out of scope for the initial release;
      this is a personal-use server and PyPI publication of a ToS-gray-area
      scraper wrapper is intentionally deferred.

## Notes

- **Never force-push `main`.**
- yfinance major bumps are NOT part of a routine release — they follow the
  manual upgrade smoke test in `docs/THREAT_MODEL.md` §4.
