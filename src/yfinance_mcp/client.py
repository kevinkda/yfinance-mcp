"""yfinance API client wrapper with a read-only method allow-list.

This wraps :class:`yfinance.Ticker` behind a narrow async surface so the
rest of the codebase never touches yfinance directly. Three reasons:

1. **Read-only allow-list.** yfinance's ``Ticker`` is read-only by nature
   (it scrapes data; it cannot place trades), but we still gate access to
   a frozen :data:`_READ_ONLY_METHODS` set so a future refactor cannot
   accidentally start calling some new mutating helper yfinance might add.
   Any non-allow-listed attribute raises :class:`NotImplementedError`.

2. **Sync -> async.** yfinance is fully synchronous and does blocking
   network I/O. We wrap every call in :func:`asyncio.to_thread` so the MCP
   event loop is never blocked.

3. **Error normalisation.** yfinance raises a grab-bag of exceptions
   (``requests`` errors, ``KeyError``, ``ValueError``, empty frames). We
   funnel them into a single :class:`YFinanceError` with a stable
   ``reason`` string callers can branch on.

Testability (for the Phase 3 / batch-4 100%-coverage campaign):
    :class:`YFinanceClient` takes an injectable ``ticker_factory`` so tests
    can pass a fake that returns canned frames with **zero network calls**.
    The default factory is :class:`yfinance.Ticker`.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from typing import Any, Final

log = logging.getLogger(__name__)

#: Default per-call timeout (seconds) for the to_thread-wrapped yfinance call.
_DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0
_ENV_TIMEOUT: Final[str] = "YFINANCE_TIMEOUT_SECONDS"

# ---------------------------------------------------------------------------
# Read-only method allow-list — every entry is a read-only yfinance Ticker
# method/attribute this server intends to call. Keep alphabetised.
# ---------------------------------------------------------------------------
_READ_ONLY_METHODS: frozenset[str] = frozenset(
    {
        "get_calendar",
        "get_earnings_dates",
        "get_recommendations",
        "get_splits",
        "income_stmt",
        "quarterly_income_stmt",
        "recommendations_summary",
        "upgrades_downgrades",
    }
)

#: A ``ticker_factory`` takes a symbol and returns an object exposing the
#: allow-listed read-only yfinance ``Ticker`` surface.
TickerFactory = Callable[[str], Any]


class YFinanceError(RuntimeError):
    """Normalised yfinance failure.

    Attributes:
        reason: stable, branchable reason string — one of
            ``"not_found"`` (symbol resolved to no data),
            ``"rate_limited"`` (Yahoo returned 429 / throttled),
            ``"timeout"`` (call exceeded the configured timeout),
            ``"upstream_error"`` (any other yfinance / network failure),
            ``"blocked_method"`` (attempt to use a non-allow-listed method).
        detail: short human-readable detail (already truncated).
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"[{reason}] {detail}")
        self.reason = reason
        self.detail = detail


def _default_ticker_factory(symbol: str) -> Any:
    # Local import keeps yfinance (heavy, with import-time side effects) out
    # of the module import path until a real call is made — and lets tests
    # inject a fake factory without importing yfinance at all.
    import yfinance

    return yfinance.Ticker(symbol)


def _timeout_seconds() -> float:
    raw = os.environ.get(_ENV_TIMEOUT, "").strip()
    if not raw:
        return _DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_TIMEOUT_SECONDS
    return value if value > 0 else _DEFAULT_TIMEOUT_SECONDS


class YFinanceClient:
    """Thin async wrapper enforcing a read-only yfinance allow-list.

    Construct once per process and reuse. Stateless apart from the injected
    ``ticker_factory``, so it is safe to share across concurrent tool calls
    (each call builds its own ``Ticker`` via the factory).
    """

    __slots__ = ("_ticker_factory", "_timeout")

    def __init__(
        self,
        ticker_factory: TickerFactory | None = None,
        timeout: float | None = None,
    ) -> None:
        self._ticker_factory: TickerFactory = ticker_factory or _default_ticker_factory
        self._timeout: float = timeout if timeout is not None else _timeout_seconds()

    async def call(self, symbol: str, method: str, *args: Any, **kwargs: Any) -> Any:
        """Invoke an allow-listed read-only yfinance method on *symbol*.

        ``method`` may be either a zero-arg property (e.g. ``income_stmt``)
        or a callable method (e.g. ``get_splits``). The wrapper inspects the
        resolved attribute and calls it iff it is callable.

        Raises :class:`YFinanceError` with a normalised ``reason`` on any
        failure (including a non-allow-listed ``method``).
        """
        if method not in _READ_ONLY_METHODS:
            raise YFinanceError(
                "blocked_method",
                f"{method!r} is not in the read-only allow-list; see src/yfinance_mcp/client.py.",
            )

        def _invoke() -> Any:
            ticker = self._ticker_factory(symbol)
            attr = getattr(ticker, method)
            return attr(*args, **kwargs) if callable(attr) else attr

        try:
            return await asyncio.wait_for(asyncio.to_thread(_invoke), timeout=self._timeout)
        except TimeoutError as exc:
            log.warning("yfinance call timed out: symbol=%s method=%s", symbol, method)
            raise YFinanceError("timeout", f"call exceeded {self._timeout}s") from exc
        except YFinanceError:
            raise
        except Exception as exc:
            return self._raise_normalised(exc)

    @staticmethod
    def _raise_normalised(exc: Exception) -> Any:
        text = str(exc).lower()
        if "429" in text or "too many requests" in text or "rate limit" in text:
            raise YFinanceError("rate_limited", str(exc)[:300]) from exc
        if "not found" in text or "no data found" in text or "delisted" in text or "404" in text:
            raise YFinanceError("not_found", str(exc)[:300]) from exc
        raise YFinanceError("upstream_error", str(exc)[:300]) from exc


__all__ = ["YFinanceClient", "YFinanceError"]
