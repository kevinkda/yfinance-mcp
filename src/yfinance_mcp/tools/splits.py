"""``get_splits`` — historical stock-split events for a symbol.

Wraps ``yfinance.Ticker.get_splits()``, which returns a pandas Series
indexed by split date with the split ratio as the value (e.g. a 4-for-1
split is ``4.0``).
"""

from __future__ import annotations

from typing import Any

from ..cache import get_cache
from ..client import YFinanceError
from ..models import GetSplitsInput
from ._common import error_payload, get_client, series_to_records


async def get_splits_impl(payload: dict[str, Any]) -> dict[str, Any]:
    """Fetch split history, persist a snapshot, return the rows."""
    args = GetSplitsInput.model_validate(payload)
    client = get_client()

    try:
        series = await client.call(args.symbol, "get_splits")
    except YFinanceError as exc:
        return error_payload(exc, args.symbol)

    rows = series_to_records(series, key_name="split_date", value_name="ratio")

    cache_status = "skipped:disabled"
    cache = get_cache()
    if cache is not None:
        try:
            inserted = cache.write_splits(args.symbol, rows)
            cache_status = f"snapshot_written:{inserted}"
        except Exception as exc:  # pragma: no cover - defensive
            cache_status = f"skipped:error:{type(exc).__name__}"

    return {
        "ok": True,
        "symbol": args.symbol,
        "splits": rows,
        "count": len(rows),
        "_cache_status": cache_status,
    }
