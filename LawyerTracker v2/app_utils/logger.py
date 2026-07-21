"""
logger.py

Provides a single `get_logger(name)` function that every module calls to
get a configured logger, e.g.:

    from app_utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("District list loaded")

Design decision: Python's logging module is a singleton registry keyed by
name, so calling `logging.getLogger(__name__)` in every file already gives
each module its own named logger (e.g. "services.search_service"). What we
add here is the *configuration* (log format, file handler, console handler)
applied once at import time, so every module's logger automatically writes
to both the console and logs/app.log without repeating setup code.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from config import settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def _configure_root_logger() -> None:
    """Attach console + rotating file handlers to the root logger, once."""
    global _configured
    if _configured:
        return

    root = logging.getLogger()
    root.setLevel(settings.log_level)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    # Rotate at 1 MB, keep 3 backups, so logs/app.log doesn't grow forever.
    file_handler = RotatingFileHandler(
        settings.log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger, configuring app-wide handlers on first call."""
    _configure_root_logger()
    return logging.getLogger(name)
