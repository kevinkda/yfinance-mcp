"""Shared helpers for ``yfinance_mcp.tools`` modules.

Every tool entrypoint follows the same shape:
  1. Validate input with a Pydantic schema.
  2. Acquire the process-wide :class:`YFinanceClient`.
  3. ``await`` the allow-listed yfinance call (wrapped in a thread).
  4. Normalise the pandas frame / dict into JSON-serialisable rows.
  5. Best-effort persist to the DuckDB cache.
  6. Return a dict with ``ok`` + ``_cache_status``.

The client is injectable (``set_client`` / ``reset_client_singleton``) so the
Phase 3 / batch-4 test campaign can swap in a fake factory and reach 100%
coverage with zero network calls.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from ..client import YFinanceClient, YFinanceError

log = logging.getLogger(__name__)

_CLIENT_SINGLETON: YFinanceClient | None = None


def get_client() -> YFinanceClient:
    """Return the process-wide :class:`YFinanceClient` (lazy)."""
    global _CLIENT_SINGLETON
    if _CLIENT_SINGLETON is None:
        _CLIENT_SINGLETON = YFinanceClient()
    return _CLIENT_SINGLETON


def set_client(client: YFinanceClient) -> None:
    """Test / DI hook: install a specific client (e.g. with a fake factory)."""
    global _CLIENT_SINGLETON
    _CLIENT_SINGLETON = client


def reset_client_singleton() -> None:
    """Test hook: drop the cached client."""
    global _CLIENT_SINGLETON
    _CLIENT_SINGLETON = None


# ---------------------------------------------------------------------------
# Frame / value normalisation
# ---------------------------------------------------------------------------


def jsonify(value: Any) -> Any:
    """Coerce a yfinance/pandas value into a JSON-serialisable scalar.

    Handles the common yfinance return quirks: numpy scalars, pandas
    Timestamps, NaN/NaT, and Timedelta. Anything unrecognised is stringified
    so the tool never raises a serialisation error back to the MCP host.
    """
    if value is None:
        return None
    # NaN / inf -> None (JSON has no NaN).
    if isinstance(value, float):
        return None if (math.isnan(value) or math.isinf(value)) else value
    if isinstance(value, (str, int, bool)):
        return value
    # numpy scalars expose .item(); pandas Timestamp/Timedelta expose isoformat/str.
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return jsonify(item())
        except (ValueError, TypeError):
            pass
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        try:
            return iso()
        except (ValueError, TypeError):
            pass
    return str(value)


def frame_is_empty(frame: Any) -> bool:
    """True if a pandas DataFrame/Series is None or empty (no rows)."""
    if frame is None:
        return True
    empty = getattr(frame, "empty", None)
    if isinstance(empty, bool):
        return empty
    try:
        return len(frame) == 0
    except TypeError:
        return False


def dataframe_to_records(frame: Any) -> list[dict[str, Any]]:
    """Convert a pandas DataFrame to a list of JSON-safe row dicts.

    The DataFrame index is preserved under an ``index`` key (stringified)
    because yfinance frequently puts the meaningful axis (dates / line-item
    names) on the index rather than a column.
    """
    if frame_is_empty(frame):
        return []
    records: list[dict[str, Any]] = []
    to_dict = getattr(frame, "to_dict", None)
    columns = getattr(frame, "columns", None)
    index = getattr(frame, "index", None)
    if to_dict is None or columns is None or index is None:
        return []
    col_list = list(columns)
    for idx in index:
        row: dict[str, Any] = {"index": jsonify(idx)}
        for col in col_list:
            try:
                row[str(col)] = jsonify(frame.at[idx, col])
            except (KeyError, ValueError, TypeError):
                row[str(col)] = None
        records.append(row)
    return records


def series_to_records(series: Any, *, key_name: str, value_name: str) -> list[dict[str, Any]]:
    """Convert a pandas Series (index -> scalar) to a list of row dicts."""
    if frame_is_empty(series):
        return []
    items = getattr(series, "items", None)
    if items is None:
        return []
    return [{key_name: jsonify(k), value_name: jsonify(v)} for k, v in series.items()]


def error_payload(exc: YFinanceError, symbol: str) -> dict[str, Any]:
    """Standard error envelope shared by every tool."""
    return {
        "ok": False,
        "symbol": symbol,
        "error": {"reason": exc.reason, "detail": exc.detail},
        "_cache_status": "skipped:error",
    }


__all__ = [
    "dataframe_to_records",
    "error_payload",
    "frame_is_empty",
    "get_client",
    "jsonify",
    "reset_client_singleton",
    "series_to_records",
    "set_client",
]
