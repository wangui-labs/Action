# src/pipeline/__init__.py
"""
Pipeline package init. Configures logging once, on first import.

No other module should call logging.basicConfig() or add handlers.
All pipeline modules use:

    import logging
    log = logging.getLogger(__name__)
"""
from __future__ import annotations

import logging
import sys

from src.pipeline.settings import (
    LOG_DIR, LOG_FILE, LOG_LEVEL, LOG_FORMAT, LOG_DATEFMT,
)

_CONFIGURED = False


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    pkg = logging.getLogger("src.pipeline")
    pkg.setLevel(LOG_LEVEL)
    pkg.propagate = False

    fmt = logging.Formatter(LOG_FORMAT, LOG_DATEFMT)

    fh = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    fh.setFormatter(fmt)
    pkg.addHandler(fh)

    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    pkg.addHandler(sh)

    _CONFIGURED = True


_configure()

__all__: list[str] = []