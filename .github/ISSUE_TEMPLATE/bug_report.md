---
name: Bug report
about: Something is broken or returns unexpected output.
title: "bug: <short summary>"
labels: ["bug"]
---

## Environment

| Field | Value |
| ----- | ----- |
| OS (and version) | e.g. macOS 14.5 (arm64) / Ubuntu 22.04 (x86_64) / Windows 11 23H2 |
| Python | output of `python --version` |
| `uv` | output of `uv --version` |
| `mcp` (Python SDK) | output of `uv pip show mcp \| grep Version` |
| `yfinance` | output of `uv pip show yfinance \| grep Version` |
| `yfinance-mcp` (this server) | git commit hash + tag |
| MCP host (Cursor / Claude Code / etc.) | host name + version |

## Reproduction steps

1. ...
2. ...
3. ...

Include the exact tool input you sent, e.g.:

```json
{
  "name": "get_splits",
  "arguments": {"symbol": "AAPL"}
}
```

## Expected behavior

What you expected to see in the response or in the MCP host UI.

## Actual behavior

What you actually saw — JSON response, exception, or hung tool call.

> **Note on yfinance flakiness.** yfinance scrapes an undocumented Yahoo
> Finance endpoint. Empty results, `429 Too Many Requests`, or schema
> drift are frequently upstream issues, not bugs in this server. Before
> filing, confirm the same symbol returns data with a bare
> `python -c "import yfinance; print(yfinance.Ticker('AAPL').get_splits())"`.

## Logs

Paste relevant lines from stderr / the host-redirected log file.

```text
<paste log here>
```

## Additional context

- Did this start after a specific commit or version bump (especially a
  `yfinance` bump)?
- Does it reproduce after a clean `uv sync --extra dev`?
- Is it specific to one symbol, one market, or one MCP host?
