"""Process-bootstrap helper: load ``.env`` before any business import.

yfinance-mcp needs no credentials, but it does honor optional ``.env``
tuning knobs (cache controls, timeout, log level). Centralising the
``load_dotenv`` call here:

* avoids duplicate ``load_dotenv()`` calls drifting out of sync,
* keeps the import-order contract explicit (must run before any business
  import that reads ``os.environ``),
* makes the behaviour testable in isolation without spawning a subprocess.

Security contract:

* We **only** call :func:`dotenv.load_dotenv` with its default search
  algorithm (cwd -> parents) — we never accept a user-supplied path here,
  so there is no path-traversal surface.
* :func:`dotenv.load_dotenv` is a no-op if the package is missing or the
  file does not exist; both are tolerated silently because a host-injected
  env (e.g. Cursor ``mcp.json`` ``env``) is the recommended path and
  ``.env`` is only a developer fallback.
* We **never** raise from this helper — any failure must not prevent the
  server from starting if the host already provided the env vars.
* :data:`override` is **always** ``False`` so host-provided env vars take
  precedence over a stale developer ``.env``.
"""

from __future__ import annotations

import os
from typing import Final

#: Sentinel env var that tests assert on to confirm the loader actually ran.
_BOOTSTRAP_RAN_ENV: Final[str] = "YFINANCE_MCP_DOTENV_LOADED"


def bootstrap_dotenv() -> bool:
    """Load ``.env`` from the current working directory (or a parent).

    Returns ``True`` if ``python-dotenv`` was importable and its loader ran
    (regardless of whether a file was actually found), ``False`` if the
    optional dependency is missing.  Never raises.

    The function is **idempotent**: calling it multiple times is safe and
    will not overwrite env vars that the host already injected, because
    ``override=False`` is enforced.
    """
    # ``python-dotenv`` is a declared dependency in ``pyproject.toml`` but we
    # still guard the import so that an unusual install (e.g. running the raw
    # source tree without ``uv sync``) degrades to "fall back to host env"
    # instead of crashing the server before stdio is up.
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:
        return False

    # ``usecwd=True`` anchors the search at the **process** working directory,
    # not at the caller's source file.  In tests this keeps every test honest
    # about its cwd instead of walking up to the repo-root ``.env``.
    try:
        dotenv_path = find_dotenv(usecwd=True)
    except OSError:  # pragma: no cover - defensive: filesystem errors during search
        return True

    if dotenv_path:
        try:
            load_dotenv(dotenv_path=dotenv_path, override=False)
        except OSError:  # pragma: no cover - defensive: .env became unreadable mid-call
            pass

    os.environ.setdefault(_BOOTSTRAP_RAN_ENV, "1")
    return True


__all__ = ["bootstrap_dotenv"]
