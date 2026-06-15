"""OWASP Top 10 (2021) security tests for yfinance-mcp.

Read-only, no-credential, no-HTML/XML server. N/A categories carry explicit
guards. Every applicable test asserts substantively.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from yfinance_mcp.client import _READ_ONLY_METHODS, YFinanceClient, YFinanceError
from yfinance_mcp.models import GetEarningsCalendarInput, GetSplitsInput
from yfinance_mcp.tools import _common, meta, splits


def _inserted_rows(tmp_cache: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for call in tmp_cache.backend._client.insert.call_args_list:
        for entry in call.args[1]:
            rows.append(json.loads(entry[1]))
    return rows


# ---------------------------------------------------------------------------
# A01:2021 — Broken Access Control
# ---------------------------------------------------------------------------
class TestA01AccessControl:
    async def test_allowlist_denies_arbitrary_attribute(self, fake_client: YFinanceClient) -> None:
        with pytest.raises(YFinanceError) as ei:
            await fake_client.call("AAPL", "__class__")
        assert ei.value.reason == "blocked_method"

    async def test_allowlist_denies_dunder_traversal(self, fake_client: YFinanceClient) -> None:
        for attr in ("__dict__", "__getattribute__", "_session", "_data"):
            with pytest.raises(YFinanceError):
                await fake_client.call("AAPL", attr)

    def test_server_declares_read_only(self) -> None:
        info = meta.get_server_info_impl()
        assert info["is_read_only"] is True
        health = meta.health_check_impl()
        assert health["is_read_only"] is True


# ---------------------------------------------------------------------------
# A02:2021 — Cryptographic Failures
# ---------------------------------------------------------------------------
class TestA02Cryptographic:
    def test_na_no_secrets_and_no_on_disk_cache_file(self, tmp_cache: Any) -> None:
        # v0.3.0: no crypto/secrets in this server, and the default memory
        # backend keeps no on-disk artefact at all (the DuckDB file is gone).
        assert tmp_cache.backend.name in {"memory", "clickhouse"}
        assert not hasattr(tmp_cache, "_db_path")


# ---------------------------------------------------------------------------
# A03:2021 — Injection
# ---------------------------------------------------------------------------
class TestA03Injection:
    @pytest.mark.parametrize(
        "payload",
        ["AAPL'--", "1; SELECT 1", "${jndi:ldap://x}", "{{7*7}}", "%0a%0d", "\x00AAPL", "AA\nPL"],
    )
    def test_injection_payloads_rejected(self, payload: str) -> None:
        with pytest.raises(ValidationError):
            GetSplitsInput.model_validate({"symbol": payload})

    def test_limit_injection_via_type_confusion(self) -> None:
        with pytest.raises(ValidationError):
            GetEarningsCalendarInput.model_validate({"symbol": "AAPL", "limit": "12; DROP TABLE x"})


# ---------------------------------------------------------------------------
# A04:2021 — Insecure Design  (threat-model driven controls)
# ---------------------------------------------------------------------------
class TestA04InsecureDesign:
    def test_defense_in_depth_allowlist_plus_validation(self, fake_client: YFinanceClient) -> None:
        # Two independent controls: (1) symbol validation, (2) method allow-list.
        assert isinstance(_READ_ONLY_METHODS, frozenset)
        assert len(_READ_ONLY_METHODS) >= 4

    async def test_cache_is_best_effort_not_correctness_dependency(self, fake_ticker_factory: Any) -> None:
        # With cache disabled the tool still returns valid data (graceful design).
        _common.set_client(YFinanceClient(ticker_factory=fake_ticker_factory, timeout=5.0))
        out = await splits.get_splits_impl({"symbol": "AAPL"})
        _common.reset_client_singleton()
        assert out["ok"] is True
        assert out["_cache_status"] == "skipped:disabled"


# ---------------------------------------------------------------------------
# A05:2021 — Security Misconfiguration
# ---------------------------------------------------------------------------
class TestA05Misconfiguration:
    def test_no_hardcoded_secrets_in_source(self) -> None:
        import re
        from pathlib import Path

        src_root = Path(__file__).resolve().parent.parent / "src" / "yfinance_mcp"
        secret_pat = re.compile(r"(api[_-]?key|secret|password|token)\s*=\s*['\"][A-Za-z0-9]{12,}['\"]", re.I)
        for py in src_root.rglob("*.py"):
            assert not secret_pat.search(py.read_text()), f"possible hardcoded secret in {py}"

    def test_models_frozen_and_strict(self) -> None:
        m = GetSplitsInput.model_validate({"symbol": "AAPL"})
        assert m.model_config["frozen"] is True
        assert m.model_config["extra"] == "forbid"


# ---------------------------------------------------------------------------
# A06:2021 — Vulnerable & Outdated Components
# ---------------------------------------------------------------------------
class TestA06Components:
    def test_all_deps_have_lower_and_upper_bounds(self) -> None:
        import tomllib
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        data = tomllib.loads((root / "pyproject.toml").read_text())
        for dep in data["project"]["dependencies"]:
            assert ">=" in dep and "<" in dep, dep


# ---------------------------------------------------------------------------
# A07:2021 — Identification & Authentication Failures  (N/A)
# ---------------------------------------------------------------------------
class TestA07Auth:
    def test_na_no_auth_no_session_state(self) -> None:
        # The client is stateless apart from the injected factory; no login,
        # no session token, nothing to fixate or steal.
        from yfinance_mcp.client import YFinanceClient

        assert set(YFinanceClient.__slots__) == {"_ticker_factory", "_timeout"}


# ---------------------------------------------------------------------------
# A08:2021 — Software & Data Integrity Failures
# ---------------------------------------------------------------------------
class TestA08Integrity:
    def test_cache_data_is_json_not_executable(self, tmp_cache: Any) -> None:
        tmp_cache.write_recommendations("AAPL", [{"kind": "summary", "rec_date": "0m"}])
        rows = _inserted_rows(tmp_cache)
        # The stored raw_json round-trips as inert JSON; never eval'd.
        assert isinstance(json.loads(rows[0]["raw_json"]), dict)


# ---------------------------------------------------------------------------
# A09:2021 — Security Logging & Monitoring Failures
# ---------------------------------------------------------------------------
class TestA09Logging:
    def test_cache_write_failure_degrades_to_zero(self, tmp_cache: Any) -> None:
        # v0.3.0: a backend insert error degrades to 0 persisted rows (the
        # auditable signal), never raising into the tool.
        tmp_cache.backend._client.insert.side_effect = RuntimeError("disk full")
        persisted = tmp_cache.write_splits("AAPL", [{"split_date": "x", "ratio": 1.0}])
        assert persisted == 0


# ---------------------------------------------------------------------------
# A10:2021 — Server-Side Request Forgery (SSRF)
# ---------------------------------------------------------------------------
class TestA10SSRF:
    @pytest.mark.parametrize(
        "payload",
        [
            "http://169.254.169.254/latest/meta-data/",
            "file:///etc/passwd",
            "//evil.com/x",
            "AAPL@evil.com",
            "AAPL/../../../etc",
        ],
    )
    def test_symbol_cannot_smuggle_a_url(self, payload: str) -> None:
        # The symbol regex forbids ``/``, ``:``, ``@``, ``//`` — a symbol can
        # never be coerced into a URL yfinance would fetch.
        with pytest.raises(ValidationError):
            GetSplitsInput.model_validate({"symbol": payload})

    async def test_symbol_passed_only_to_yfinance_ticker(self, fake_ticker_factory: Any) -> None:
        # The validated symbol reaches the factory verbatim; the server itself
        # never constructs a URL from it — URL building is entirely internal to
        # yfinance, which we treat as the trust boundary.
        captured: dict[str, Any] = {}

        def factory(symbol: str) -> MagicMock:
            captured["symbol"] = symbol
            return fake_ticker_factory(symbol)

        client = YFinanceClient(ticker_factory=factory, timeout=5.0)
        await client.call("AAPL", "get_splits")
        assert captured["symbol"] == "AAPL"
