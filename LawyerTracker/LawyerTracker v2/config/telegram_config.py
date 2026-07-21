"""
telegram_config.py

Resolves the Telegram bot's own identity - the Bot Token and Bot
Username. This is the ONE app-owner secret that every advocate's copy
of LawyerTracker shares; it is never entered, edited, or shown through
the UI, and it is never written to the app's SQLite database (which
only ever holds the per-advocate Chat ID/username/display name once
they connect).

Token precedence:

  1. The TELEGRAM_BOT_TOKEN environment variable, if set.
  2. Otherwise, a `telegram_config.json` file stored alongside the
     application (project root), e.g.:

         { "bot_token": "123456789:AAFF..." }

If neither is present, `get_bot_token()` returns None and every
Telegram feature (Connect, Verify, Test, scheduled sends) reports a
clear "not configured on this installation" error instead of
crashing - this is expected on a machine the app owner hasn't set up
yet, not a bug.

BOT_USERNAME is not a secret (it's the public @handle used to build
the t.me deep link), so it's a plain constant here rather than
something loaded from the token sources above.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Optional

from config.settings import settings
from app_utils.logger import get_logger

logger = get_logger(__name__)

_ENV_VAR = "TELEGRAM_BOT_TOKEN"
_CONFIG_FILENAME = "telegram_config.json"

# Public bot handle - safe to hardcode, used only to build
# https://t.me/<BOT_USERNAME> for the "Connect Telegram" button.
BOT_USERNAME = "lawyertracker_notifications_bot"


@lru_cache(maxsize=1)
def get_bot_token() -> Optional[str]:
    """
    Returns the bot token, or None if it isn't configured anywhere.
    Cached after the first successful/unsuccessful lookup for the life
    of the process - this is read on every send, so we don't want to
    hit disk each time, and the token isn't expected to change while
    the app is running.
    """
    env_token = os.environ.get(_ENV_VAR, "").strip()
    if env_token:
        logger.info("Telegram bot token loaded from %s environment variable.", _ENV_VAR)
        return env_token

    config_path = settings.base_dir / _CONFIG_FILENAME
    if not config_path.exists():
        logger.warning(
            "Telegram bot token not found: no %s environment variable and no %s at %s.",
            _ENV_VAR, _CONFIG_FILENAME, config_path,
        )
        return None

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        token = (data.get("bot_token") or "").strip()
    except (OSError, ValueError) as exc:
        logger.error("Failed to read %s: %s", config_path, exc)
        return None

    if not token:
        logger.warning("%s exists but has no 'bot_token' value.", config_path)
        return None

    logger.info("Telegram bot token loaded from %s.", _CONFIG_FILENAME)
    return token
