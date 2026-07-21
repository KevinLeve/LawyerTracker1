"""
config_service.py

A tiny key/value store (backed by the `app_config` table) for settings
the user changes at runtime from the Settings screen - currently just
the KevinOCR folder path. Kept separate from `config/settings.py`,
which holds compile-time defaults (paths, URLs, timeouts) that aren't
meant to be edited through the UI.
"""
from __future__ import annotations

from typing import Optional

from database import get_connection
from app_utils.logger import get_logger

logger = get_logger(__name__)


class ConfigService:
    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT value FROM app_config WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else default

    def set(self, key: str, value: str) -> None:
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO app_config (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (key, value),
            )
            logger.info("Config updated: %s", key)
