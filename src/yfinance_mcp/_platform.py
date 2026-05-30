"""Cross-platform OS shims.

This module abstracts the small set of POSIX-vs-Windows differences this
project actually uses, so the rest of the codebase stays platform-neutral.

Tier A (best-effort) Windows support:
    * file permissions    - POSIX chmod where supported, no-op + warning on Windows
    * permission checks   - strict 0o600/0o700 on POSIX, "exists & readable" on Windows
    * XDG state root       - $XDG_STATE_HOME / %LOCALAPPDATA% / ~/.local/state

Tier B (production-grade ACL via pywin32) is intentionally NOT implemented
here.  When the project upgrades to Tier B, replace ``is_secure_perms`` and
``secure_chmod`` with real Windows ACL checks; everything else stays.
"""

from __future__ import annotations

import contextlib
import logging
import os
import stat
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Final

IS_WINDOWS: Final[bool] = sys.platform == "win32"
IS_MACOS: Final[bool] = sys.platform == "darwin"
IS_LINUX: Final[bool] = sys.platform.startswith("linux")

log = logging.getLogger("yfinance_mcp._platform")


# ---------------------------------------------------------------------------
# File permissions
# ---------------------------------------------------------------------------

#: 0o600 / 0o700 still drive the *intent*; on Windows we just log a warning.
_WIN_PERMS_WARNED: set[str] = set()


def secure_chmod(path: Path, mode: int) -> None:
    """Set restrictive permissions.  POSIX-strict; Windows best-effort no-op."""
    if IS_WINDOWS:  # pragma: no cover - windows-only branch
        # Tier A: rely on user-profile NTFS ACLs (default: only the owner +
        # admins have access to %LOCALAPPDATA%).  Tier B will add explicit ACL
        # hardening via pywin32.
        key = str(path)
        if key not in _WIN_PERMS_WARNED:
            _WIN_PERMS_WARNED.add(key)
            log.warning(
                "platform=windows chmod is no-op; relying on default NTFS ACL "
                "inherited from %%LOCALAPPDATA%%. path=%s mode=%o",
                path,
                mode,
            )
        return
    os.chmod(path, mode)


def secure_fchmod(fd: int, mode: int) -> None:
    """``fchmod`` equivalent.  POSIX-strict; Windows best-effort no-op."""
    if IS_WINDOWS:  # pragma: no cover - windows-only branch
        return
    os.fchmod(fd, mode)


def is_secure_perms(path: Path, expected: int) -> bool:
    """Return ``True`` iff *path* has restrictive perms equal to *expected*.

    POSIX: strict equality on ``stat.S_IMODE``.
    Windows: best-effort - returns ``True`` iff the file exists and is
    owner-readable (we cannot strictly check NTFS ACLs without ``pywin32``).
    Tier B should replace this with a real ACL check.
    """
    if not path.exists():
        return False
    if IS_WINDOWS:  # pragma: no cover - windows-only branch
        return os.access(path, os.R_OK)
    return stat.S_IMODE(path.lstat().st_mode) == expected


def file_mode(path: Path) -> int:
    """Return permission bits.  On Windows, returns ``0`` to signal "unknown".

    Callers MUST check :data:`IS_WINDOWS` before treating the result as
    comparable to ``0o600``.
    """
    if IS_WINDOWS:  # pragma: no cover - windows-only branch
        return 0
    return stat.S_IMODE(path.lstat().st_mode)


@contextlib.contextmanager
def restrictive_umask() -> Iterator[None]:
    """``umask(0o077)`` on POSIX; no-op on Windows."""
    if IS_WINDOWS:  # pragma: no cover - windows-only branch
        yield
        return
    old = os.umask(0o077)
    try:
        yield
    finally:
        os.umask(old)


# ---------------------------------------------------------------------------
# XDG / state directory
# ---------------------------------------------------------------------------


def state_root() -> Path:
    """Cross-platform state-directory root.

    Order of precedence:
        1. ``$XDG_STATE_HOME`` (always honored - lets advanced users override).
        2. Windows: ``%LOCALAPPDATA%`` (typically ``C:\\Users\\<u>\\AppData\\Local``).
        3. POSIX fallback: ``~/.local/state``.
    """
    raw = os.environ.get("XDG_STATE_HOME")
    if raw:
        return Path(raw).expanduser()
    if IS_WINDOWS:  # pragma: no cover - windows-only branch
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            return Path(local_app)
        return Path.home() / "AppData" / "Local"
    return Path.home() / ".local" / "state"


__all__ = [
    "IS_LINUX",
    "IS_MACOS",
    "IS_WINDOWS",
    "file_mode",
    "is_secure_perms",
    "restrictive_umask",
    "secure_chmod",
    "secure_fchmod",
    "state_root",
]
