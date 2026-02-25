from __future__ import annotations

import logging


DEFAULT_LOG_LEVEL = logging.INFO
DEFAULT_LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"


def configure_logging(
    level: int = DEFAULT_LOG_LEVEL,
    fmt: str = DEFAULT_LOG_FORMAT,
) -> None:
    """
    Configure application logging.

    This preserves the current behavior by delegating to `logging.basicConfig`
    with the same defaults previously defined in `main.py`.
    """
    logging.basicConfig(level=level, format=fmt)
