"""
telegram_service.py

Thin wrapper around Telegram's Bot API `sendMessage` endpoint. This is
the ONLY module that knows an HTTP call is involved - everything else
(reminder_logic, reminder_scheduler, settings_screen) just calls
`send_message(token, chat_id, text)` and gets back a simple result.

Design decision: no `python-telegram-bot` dependency. Sending a message
is a single POST request, and `requests` is already a project
dependency - pulling in a whole bot framework for one HTTP call would
be unnecessary weight, and it also keeps this trivial to port to
Flutter later (just another HTTP POST from Dart).

Never raises. Network failures, invalid tokens, and Telegram-side
errors are all reported back as `(False, <reason>)` so callers (the
scheduler, the UI) never have to wrap this in their own try/except to
stay alive.
"""
from __future__ import annotations

from typing import Optional

import requests

from app_utils.logger import get_logger

logger = get_logger(__name__)

_API_BASE = "https://api.telegram.org"
_TIMEOUT_SECONDS = 15


class TelegramService:
    def send_message(
        self, bot_token: str, chat_id: str, text: str
    ) -> tuple[bool, Optional[str]]:
        """
        Send `text` to `chat_id` via the bot identified by `bot_token`.

        Returns (True, None) on success, or (False, reason) on any
        failure - missing config, no internet, invalid token/chat id,
        or a non-200 response from Telegram. Never raises.
        """
        if not bot_token or not chat_id:
            reason = "Telegram bot token or chat ID is not configured."
            logger.warning(reason)
            return False, reason

        url = f"{_API_BASE}/bot{bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text}

        try:
            response = requests.post(url, json=payload, timeout=_TIMEOUT_SECONDS)
        except requests.exceptions.RequestException as exc:
            reason = f"Network error while contacting Telegram: {exc}"
            logger.error(reason)
            return False, reason

        if response.status_code == 200:
            body = response.json()
            if body.get("ok"):
                logger.info("Telegram reminder sent to chat_id=%s", chat_id)
                return True, None
            reason = f"Telegram API rejected the message: {body.get('description', 'unknown error')}"
            logger.error(reason)
            return False, reason

        try:
            description = response.json().get("description", response.text)
        except ValueError:
            description = response.text
        reason = f"Telegram API returned HTTP {response.status_code}: {description}"
        logger.error(reason)
        return False, reason
