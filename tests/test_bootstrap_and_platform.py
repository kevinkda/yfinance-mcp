"""bootstrap.py and _platform.py coverage (reused from schwab template)."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

import pytest

from yfinance_mcp import _platform, bootstrap


class TestBootstrap:
    def test_bootstrap_no_dotenv_file(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.chdir(tmp_path)
        os.environ.pop("YFINANCE_MCP_DOTENV_LOADED", None)
        assert bootstrap.bootstrap_dotenv() is True

    def test_bootstrap_with_dotenv_file(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("YFINANCE_MCP_TEST_VAR=hello\n")
        monkeypatch.delenv("YFINANCE_MCP_TEST_VAR", raising=False)
        os.environ.pop("YFINANCE_MCP_DOTENV_LOADED", None)
        assert bootstrap.bootstrap_dotenv() is True
        assert os.environ.get("YFINANCE_MCP_TEST_VAR") == "hello"
        os.environ.pop("YFINANCE_MCP_TEST_VAR", None)

    def test_bootstrap_override_false(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("YFINANCE_MCP_TEST_VAR=fromfile\n")
        monkeypatch.setenv("YFINANCE_MCP_TEST_VAR", "fromhost")
        bootstrap.bootstrap_dotenv()
        assert os.environ["YFINANCE_MCP_TEST_VAR"] == "fromhost"
        os.environ.pop("YFINANCE_MCP_TEST_VAR", None)

    def test_bootstrap_dotenv_missing_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import builtins

        real_import = builtins.__import__

        def fake_import(name: str, *a: Any, **k: Any) -> Any:
            if name == "dotenv":
                raise ImportError("no dotenv")
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert bootstrap.bootstrap_dotenv() is False


class TestPlatform:
    def test_state_root_xdg(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        assert _platform.state_root() == tmp_path

    def test_state_root_posix_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
        monkeypatch.setattr(_platform, "IS_WINDOWS", False)
        root = _platform.state_root()
        assert root.parts[-2:] == (".local", "state")

    @pytest.mark.posix_only
    def test_secure_chmod_posix(self, tmp_path: Path) -> None:
        if _platform.IS_WINDOWS:
            pytest.skip("posix only")
        f = tmp_path / "f"
        f.write_text("x")
        _platform.secure_chmod(f, 0o600)
        assert stat.S_IMODE(f.lstat().st_mode) == 0o600

    @pytest.mark.posix_only
    def test_secure_fchmod_posix(self, tmp_path: Path) -> None:
        if _platform.IS_WINDOWS:
            pytest.skip("posix only")
        f = tmp_path / "f"
        f.write_text("x")
        fd = os.open(f, os.O_RDONLY)
        try:
            _platform.secure_fchmod(fd, 0o600)
            assert stat.S_IMODE(f.lstat().st_mode) == 0o600
        finally:
            os.close(fd)

    @pytest.mark.posix_only
    def test_is_secure_perms(self, tmp_path: Path) -> None:
        if _platform.IS_WINDOWS:
            pytest.skip("posix only")
        f = tmp_path / "f"
        f.write_text("x")
        os.chmod(f, 0o600)
        assert _platform.is_secure_perms(f, 0o600) is True
        assert _platform.is_secure_perms(f, 0o644) is False

    def test_is_secure_perms_missing(self, tmp_path: Path) -> None:
        assert _platform.is_secure_perms(tmp_path / "nope", 0o600) is False

    @pytest.mark.posix_only
    def test_file_mode(self, tmp_path: Path) -> None:
        if _platform.IS_WINDOWS:
            pytest.skip("posix only")
        f = tmp_path / "f"
        f.write_text("x")
        os.chmod(f, 0o640)
        assert _platform.file_mode(f) == 0o640

    @pytest.mark.posix_only
    def test_restrictive_umask(self) -> None:
        if _platform.IS_WINDOWS:
            pytest.skip("posix only")
        before = os.umask(0o022)
        os.umask(before)
        with _platform.restrictive_umask():
            cur = os.umask(0o077)
            assert cur == 0o077
        after = os.umask(0o022)
        os.umask(after)
        assert after == before
