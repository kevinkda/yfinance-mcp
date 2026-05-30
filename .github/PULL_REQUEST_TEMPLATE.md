# Pull request

## Summary

<!-- 1–3 sentences describing what changed and why. Link the issue this
closes. -->

## Type of change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Documentation only
- [ ] Refactor / chore (no behavior change)
- [ ] Breaking change (semver-major)

## Checklist

- [ ] Tests pass locally — `uv run pytest --cov` (≥ 85% overall).
- [ ] `uv run ruff check src tests` is clean.
- [ ] `uv run ruff format --check src tests` is clean.
- [ ] `uv run mypy --strict src` is clean.
- [ ] Pre-commit hooks pass — `pre-commit run --all-files`.
- [ ] Conventional commit message — `feat(...)`, `fix(...)`,
      `docs(...)`, `chore(...)`, etc.
- [ ] [`CHANGELOG.md`](../CHANGELOG.md) updated under `## [Unreleased]`
      (if applicable).
- [ ] Documentation updated — README, `docs/SECURITY.md`,
      `docs/THREAT_MODEL.md`, etc. (if applicable).
- [ ] Inclusive-language audit — no `master` / `blacklist` /
      `whitelist` / `kill` / `abort`. Use `main` / `deny list` /
      `allow list` / `stop` instead.
- [ ] **Terms-of-Service:** the change keeps yfinance call volume low and
      does not enable bulk / commercial redistribution of Yahoo data
      (see `docs/SECURITY.md`).
- [ ] No secrets, `.env`, or credentials committed.

## Test plan

<!-- How did you verify this change? Include exact commands and
relevant output. -->

## Screenshots / logs (if applicable)

<!-- Trim to ≤ 30 lines. -->
