"""``get_earnings_calendar`` — upcoming / past earnings dates for a symbol.

Wraps ``yfinance.Ticker.get_earnings_dates(limit=...)``, which returns a
pandas DataFrame indexed by earnings datetime with columns such as
``EPS Estimate``, ``Reported EPS``, and ``Surprise(%)``.
"""

from __future__ import annotations

from typing import Any

from ..cache import get_cache
from ..client import YFinanceError
from ..models import GetEarningsCalendarInput
from ._common import dataframe_to_records, error_payload, get_client, jsonify


def _to_cache_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map normalised DataFrame rows to the cache's column names.

    yfinance column labels drift across versions, so we look them up
    defensively by their stable prefixes rather than exact strings.
    """
    cache_rows: list[dict[str, Any]] = []
    for rec in records:
        eps_estimate = _find(rec, "eps estimate")
        reported_eps = _find(rec, "reported eps")
        surprise = _find(rec, "surprise")
        cache_rows.append(
            {
                "earnings_date": rec.get("index"),
                "eps_estimate": eps_estimate,
                "reported_eps": reported_eps,
                "surprise_pct": surprise,
            }
        )
    return cache_rows


def _find(rec: dict[str, Any], prefix: str) -> Any:
    for key, value in rec.items():
        if key.lower().startswith(prefix):
            return jsonify(value)
    return None


async def get_earnings_calendar_impl(payload: dict[str, Any]) -> dict[str, Any]:
    """Fetch earnings dates, persist a snapshot, return the rows."""
    args = GetEarningsCalendarInput.model_validate(payload)
    client = get_client()

    try:
        frame = await client.call(args.symbol, "get_earnings_dates", limit=args.limit)
    except YFinanceError as exc:
        return error_payload(exc, args.symbol)

    rows = dataframe_to_records(frame)

    cache_status = "skipped:disabled"
    cache = get_cache()
    if cache is not None:
        try:
            inserted = cache.write_earnings_calendar(args.symbol, _to_cache_rows(rows))
            cache_status = f"snapshot_written:{inserted}"
        except Exception as exc:  # pragma: no cover - defensive
            cache_status = f"skipped:error:{type(exc).__name__}"

    return {
        "ok": True,
        "symbol": args.symbol,
        "earnings_dates": rows,
        "count": len(rows),
        "_cache_status": cache_status,
    }
