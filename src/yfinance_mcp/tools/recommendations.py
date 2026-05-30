"""``get_analyst_recommendations`` — analyst ratings for a symbol.

Combines two yfinance surfaces:

* ``Ticker.recommendations_summary`` — a small DataFrame summarising the
  current strongBuy / buy / hold / sell / strongSell counts per period.
* ``Ticker.upgrades_downgrades`` — a DataFrame of individual rating-change
  events (firm, fromGrade, toGrade, action) indexed by date.

The upgrades/downgrades history is optional (``include_upgrades_downgrades``)
because it is a heavier second network call.
"""

from __future__ import annotations

from typing import Any

from ..cache import get_cache
from ..client import YFinanceError
from ..models import GetAnalystRecommendationsInput
from ._common import dataframe_to_records, error_payload, get_client, jsonify


def _upgrade_rows_to_cache(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cache_rows: list[dict[str, Any]] = []
    for rec in records:
        cache_rows.append(
            {
                "kind": "upgrade_downgrade",
                "firm": _pick(rec, "firm"),
                "to_grade": _pick(rec, "tograde", "to grade"),
                "from_grade": _pick(rec, "fromgrade", "from grade"),
                "action": _pick(rec, "action"),
                "rec_date": rec.get("index"),
            }
        )
    return cache_rows


def _summary_rows_to_cache(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"kind": "summary", "rec_date": rec.get("index")} for rec in records]


def _pick(rec: dict[str, Any], *names: str) -> Any:
    lowered = {k.lower(): v for k, v in rec.items()}
    for name in names:
        if name in lowered:
            return jsonify(lowered[name])
    return None


async def get_analyst_recommendations_impl(payload: dict[str, Any]) -> dict[str, Any]:
    """Fetch ratings summary (+ optional upgrades/downgrades), persist, return."""
    args = GetAnalystRecommendationsInput.model_validate(payload)
    client = get_client()

    try:
        summary_frame = await client.call(args.symbol, "recommendations_summary")
    except YFinanceError as exc:
        return error_payload(exc, args.symbol)

    summary_rows = dataframe_to_records(summary_frame)

    upgrades_rows: list[dict[str, Any]] = []
    if args.include_upgrades_downgrades:
        try:
            upgrades_frame = await client.call(args.symbol, "upgrades_downgrades")
            upgrades_rows = dataframe_to_records(upgrades_frame)
        except YFinanceError:
            # Summary already succeeded; degrade gracefully on the second call.
            upgrades_rows = []

    cache_status = "skipped:disabled"
    cache = get_cache()
    if cache is not None:
        try:
            cache_rows = _summary_rows_to_cache(summary_rows) + _upgrade_rows_to_cache(upgrades_rows)
            inserted = cache.write_recommendations(args.symbol, cache_rows)
            cache_status = f"snapshot_written:{inserted}"
        except Exception as exc:  # pragma: no cover - defensive
            cache_status = f"skipped:error:{type(exc).__name__}"

    return {
        "ok": True,
        "symbol": args.symbol,
        "recommendations_summary": summary_rows,
        "upgrades_downgrades": upgrades_rows,
        "count": len(summary_rows) + len(upgrades_rows),
        "_cache_status": cache_status,
    }
