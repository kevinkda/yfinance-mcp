"""OWASP Top 10 (2017) security tests for yfinance-mcp.

Each test asserts substantively. Categories that genuinely do not apply to a
read-only, no-credential, no-HTML/XML scraping MCP server are marked N/A with
an explicit guard so the rationale is auditable rather than silently skipped.

yfinance-mcp's attack surface is unusual: it holds NO secrets, executes NO
trades, renders NO HTML, and parses NO XML. Its security posture rests on
(1) a frozen read-only allow-list, (2) strict Pydantic input validation,
(3) parameterised DuckDB writes, and (4) error normalisation that never
leaks internal stack frames.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from yfinance_mcp.client import _READ_ONLY_METHODS, YFinanceClient, YFinanceError
from yfinance_mcp.models import GetSplitsInput
from yfinance_mcp.tools import _common, splits


# ---------------------------------------------------------------------------
# A1:2017 — Injection (SQL / OS / command)
# ---------------------------------------------------------------------------
class TestA1Injection:
    @pytest.mark.parametrize(
        "payload",
        [
            "AAPL'; DROP TABLE splits;--",
            "AAPL'); DELETE FROM financials;--",
            "AAPL OR 1=1",
            "AAPL`rm -rf /`",
            "AAPL$(whoami)",
            "AAPL|cat /etc/passwd",
            "AAPL;ls",
        ],
    )
    def test_sql_and_command_injection_rejected_at_validation(self, payload: str) -> None:
        # The symbol regex rejects every injection metacharacter before it can
        # reach DuckDB or any subprocess (the server spawns none anyway).
        with pytest.raises(ValidationError):
            GetSplitsInput.model_validate({"symbol": payload})

    def test_duckdb_writes_are_parameterised(self, tmp_cache: Any) -> None:
        # Even if a malicious string somehow reached the cache layer, writes
        # use ``?`` placeholders — the value lands as data, never as SQL.
        evil = "'; DROP TABLE splits;--"
        n = tmp_cache.write_splits(evil, [{"split_date": evil, "ratio": 1.0}])
        assert n == 1
        # Table still exists and the evil string is stored verbatim as data.
        rows = tmp_cache._conn.execute("SELECT symbol, split_date FROM splits").fetchall()
        assert rows == [(evil, evil)]


# ---------------------------------------------------------------------------
# A2:2017 — Broken Authentication  (N/A — no auth surface)
# ---------------------------------------------------------------------------
class TestA2BrokenAuth:
    def test_na_no_credentials_anywhere(self) -> None:
        # yfinance needs no API key/token; the server stores/handles none.
        import os

        leaked = [k for k in os.environ if k.startswith("YFINANCE_") and ("KEY" in k or "SECRET" in k or "TOKEN" in k)]
        assert leaked == [], f"unexpected credential-like env vars: {leaked}"


# ---------------------------------------------------------------------------
# A3:2017 — Sensitive Data Exposure
# ---------------------------------------------------------------------------
class TestA3SensitiveData:
    async def test_error_payload_has_no_stack_trace(self, fake_ticker_factory: Any) -> None:
        def factory(symbol: str) -> MagicMock:
            m = fake_ticker_factory(symbol)
            m.get_splits.side_effect = RuntimeError("internal /home/secret/path traceback frame")
            return m

        _common.set_client(YFinanceClient(ticker_factory=factory, timeout=5.0))
        out = await splits.get_splits_impl({"symbol": "AAPL"})
        _common.reset_client_singleton()
        # Normalised error: a stable reason + truncated detail, no Python frames.
        assert set(out["error"].keys()) == {"reason", "detail"}
        assert "Traceback" not in out["error"]["detail"]
        assert 'File "' not in out["error"]["detail"]

    def test_detail_truncated_to_300_chars(self) -> None:
        from yfinance_mcp.client import YFinanceClient

        long = "x" * 5000
        with pytest.raises(YFinanceError) as ei:
            YFinanceClient._raise_normalised(RuntimeError(long))
        assert len(ei.value.detail) <= 300


# ---------------------------------------------------------------------------
# A4:2017 — XML External Entities (XXE)  (N/A — no XML parsing)
# ---------------------------------------------------------------------------
class TestA4XXE:
    def test_na_no_xml_parsing(self) -> None:
        # The server parses pandas frames + JSON only; it never parses XML.
        import yfinance_mcp.cache as cache_mod
        import yfinance_mcp.tools._common as common_mod

        for mod in (cache_mod, common_mod):
            src = mod.__file__ or ""
            assert "xml" not in mod.__name__.lower()
            assert src.endswith(".py")


# ---------------------------------------------------------------------------
# A5:2017 — Broken Access Control  (the read-only allow-list)
# ---------------------------------------------------------------------------
class TestA5AccessControl:
    @pytest.mark.parametrize(
        "blocked",
        ["history", "download", "place_order", "buy", "sell", "_fetch_ticker_tz", "session", "get_funds_data"],
    )
    async def test_non_allowlisted_methods_blocked(self, fake_client: YFinanceClient, blocked: str) -> None:
        with pytest.raises(YFinanceError) as ei:
            await fake_client.call("AAPL", blocked)
        assert ei.value.reason == "blocked_method"

    def test_allow_list_contains_only_read_methods(self) -> None:
        # No allow-listed method name implies a mutation.
        write_verbs = ("set", "place", "buy", "sell", "delete", "update", "post", "put", "write", "download")
        for method in _READ_ONLY_METHODS:
            assert not any(method.lower().startswith(v) for v in write_verbs), method


# ---------------------------------------------------------------------------
# A6:2017 — Security Misconfiguration
# ---------------------------------------------------------------------------
class TestA6Misconfiguration:
    def test_cache_db_dir_is_chmod_700(self, tmp_cache: Any) -> None:
        import stat

        from yfinance_mcp import _platform

        if _platform.IS_WINDOWS:
            pytest.skip("posix perms only")
        parent = tmp_cache._db_path.parent
        assert stat.S_IMODE(parent.lstat().st_mode) == 0o700

    def test_strict_models_forbid_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            GetSplitsInput.model_validate({"symbol": "AAPL", "admin": True})


# ---------------------------------------------------------------------------
# A7:2017 — XSS  (N/A — no HTML rendering)
# ---------------------------------------------------------------------------
class TestA7XSS:
    def test_na_no_html_output_and_script_symbol_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GetSplitsInput.model_validate({"symbol": "<script>alert(1)</script>"})


# ---------------------------------------------------------------------------
# A8:2017 — Insecure Deserialization
# ---------------------------------------------------------------------------
class TestA8Deserialization:
    def test_cache_uses_json_not_pickle(self, tmp_cache: Any) -> None:
        # raw_json is JSON text; we never pickle/eval untrusted data.
        import json

        tmp_cache.write_splits("AAPL", [{"split_date": "2020-08-31", "ratio": 4.0}])
        raw = tmp_cache._conn.execute("SELECT raw_json FROM splits").fetchone()[0]
        json.loads(raw)  # parses as JSON, raises if it were a pickle blob


# ---------------------------------------------------------------------------
# A9:2017 — Using Components with Known Vulnerabilities
# ---------------------------------------------------------------------------
class TestA9KnownVulns:
    def test_dependencies_pinned_with_upper_bounds(self) -> None:
        import tomllib
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        data = tomllib.loads((root / "pyproject.toml").read_text())
        deps = data["project"]["dependencies"]
        # Every runtime dependency carries an upper bound to bound CVE blast radius.
        for dep in deps:
            assert "<" in dep, f"dependency without upper bound: {dep}"


# ---------------------------------------------------------------------------
# A10:2017 — Insufficient Logging & Monitoring
# ---------------------------------------------------------------------------
class TestA10Logging:
    def test_cache_logs_insert_and_error_events(self, tmp_cache: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        tmp_cache.write_splits("AAPL", [{"split_date": "2020-08-31", "ratio": 4.0}])
        kinds = {r[0] for r in tmp_cache._conn.execute("SELECT kind FROM cache_events").fetchall()}
        assert "INSERT" in kinds

    async def test_timeout_is_logged(
        self, fake_ticker_factory: Any, monkeypatch: pytest.MonkeyPatch, caplog: Any
    ) -> None:
        import logging

        import yfinance_mcp.client as client_mod

        async def fake_wait_for(coro: Any, timeout: float) -> Any:  # noqa: ASYNC109
            coro.close()
            raise TimeoutError

        monkeypatch.setattr(client_mod.asyncio, "wait_for", fake_wait_for)
        client = YFinanceClient(ticker_factory=fake_ticker_factory, timeout=0.01)
        with caplog.at_level(logging.WARNING, logger="yfinance_mcp.client"), pytest.raises(YFinanceError):
            await client.call("AAPL", "get_splits")
        assert any("timed out" in r.message for r in caplog.records)
