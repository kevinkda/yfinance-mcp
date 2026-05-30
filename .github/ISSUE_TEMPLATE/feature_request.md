---
name: Feature request
about: Suggest a new tool, behavior, or improvement.
title: "feat: <short summary>"
labels: ["enhancement"]
---

## Motivation

What problem are you trying to solve? What is the current workflow that
this feature would simplify or unblock?

## Proposed change

Describe the proposed API. If this is a new tool, sketch the input /
output schema:

```text
new_tool_name(symbol: str, ...) -> {...}
```

## Scope alignment

Please answer all of these before submitting — these gate whether the
proposal can be accepted:

- [ ] **Is the data reachable through a documented `yfinance` method?**
      Provide the `yfinance` method name (e.g. `Ticker.get_splits`).
- [ ] **Is it read-only?** This server exposes no order / mutation / write
      surface by design — yfinance is a market-data library only.
- [ ] **Does it overlap with the companion read-only servers
      (`schwab-marketdata-mcp`, `polygon-news-mcp`, `sec-edgar-mcp`)?**
      yfinance-mcp deliberately fills the *gaps* those leave; a tool that
      duplicates one of them is unlikely to be accepted.

## Terms-of-Service note

yfinance scrapes an undocumented Yahoo Finance endpoint; using it is a
**gray area** under Yahoo's Terms of Service (see `docs/SECURITY.md`).
New tools must keep call volume low and must not enable bulk / commercial
redistribution of Yahoo data.

## Alternatives considered

Did you consider doing this via one of the companion servers or a
client-side skill instead of a server-side tool? If so, what's the gap?

## Additional context

Link to upstream `yfinance` docs, related issues, or example agent
transcripts demonstrating the gap.
