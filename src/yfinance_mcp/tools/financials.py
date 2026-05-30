"""``get_financial_statements`` — income-statement line items for a symbol.

Wraps ``yfinance.Ticker.income_stmt`` (annual) and
``Ticker.quarterly_income_stmt`` (quarterly). Both return a pandas
DataFrame whose **index** is the line-item name (e.g. ``Total Revenue``,
``Net Income``) and whose **columns** are period-end dates.

We surface the raw normalised frame under ``income_statement`` and also a
flattened ``(period_end, line_item, value)`` long form under ``rows`` that
mirrors the cache schema — the long form is easier for an LLM to scan.
"""

from __future__ import annotations

from typing import Any

from ..cache import get_cache
from ..client import YFinanceError
from ..models import GetFinancialStatementsInput
from ._common import dataframe_to_records, error_payload, get_client, jsonify

_METHOD_BY_PERIOD = {
    "annual": "income_stmt",
    "quarterly": "quarterly_income_stmt",
}


def _to_long_form(frame: Any) -> list[dict[str, Any]]:
    """Flatten the line-item-by-period DataFrame into long-form rows."""
    long_rows: list[dict[str, Any]] = []
    columns = getattr(frame, "columns", None)
    index = getattr(frame, "index", None)
    if columns is None or index is None:
        return long_rows
    for line_item in index:
        for period_end in columns:
            try:
                value = jsonify(frame.at[line_item, period_end])
            except (KeyError, ValueError, TypeError):
                value = None
            long_rows.append(
                {
                    "line_item": str(line_item),
                    "period_end": jsonify(period_end),
                    "value": value,
                }
            )
    return long_rows


async def get_financial_statements_impl(payload: dict[str, Any]) -> dict[str, Any]:
    """Fetch the income statement, persist a snapshot, return both forms."""
    args = GetFinancialStatementsInput.model_validate(payload)
    client = get_client()
    method = _METHOD_BY_PERIOD[args.period]

    try:
        frame = await client.call(args.symbol, method)
    except YFinanceError as exc:
        return error_payload(exc, args.symbol)

    wide = dataframe_to_records(frame)
    long_rows = _to_long_form(frame)

    cache_status = "skipped:disabled"
    cache = get_cache()
    if cache is not None:
        try:
            inserted = cache.write_financials(args.symbol, args.period, long_rows)
            cache_status = f"snapshot_written:{inserted}"
        except Exception as exc:  # pragma: no cover - defensive
            cache_status = f"skipped:error:{type(exc).__name__}"

    return {
        "ok": True,
        "symbol": args.symbol,
        "period": args.period,
        "income_statement": wide,
        "rows": long_rows,
        "count": len(long_rows),
        "_cache_status": cache_status,
    }
