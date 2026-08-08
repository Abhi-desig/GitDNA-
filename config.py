"""Environment loading.

A ten-line .env reader instead of a fifth dependency. Values already present in
the real environment win, so deploys can set GITHUB_TOKEN normally.
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_PATH = Path(__file__).with_name(".env")
_loaded = False


def load_env() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    if not _ENV_PATH.exists():
        return
    for raw in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def github_token() -> str | None:
    load_env()
    return os.environ.get("GITHUB_TOKEN") or None
