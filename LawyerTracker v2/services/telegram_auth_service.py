"""
telegram_auth_service.py

Everything involved in turning "advocate clicks Connect Telegram" into
a known Chat ID, with no manual copy-pasting. This is the ONLY module
that knows *how* an advocate's Telegram account gets identified -
reminder_logic, reminder_scheduler, and the Settings screen just call
`get_connect_url()` and `verify_connection()` and work with the
`ConnectedAccount` they get back.

Version 1 implementation: identify the account via `getUpdates()` -
the advocate presses START on the bot, which creates a message
Telegram is holding for us to fetch. `verify_connection()` fetches it,
pulls the chat id/name/username off it, and then immediately
re-calls `getUpdates()` with an `offset` past that update's id so
Telegram forgets it - otherwise a *future* advocate's "Verify
Connection" (or this same advocate reconnecting later) could read the
same old /start message instead of their own.

Deliberately NOT using a persistent `offset` stored anywhere: each
Verify Connection click is independent and only ever wants "whatever
is the newest unread update right now," so nothing here needs to
survive an app restart. This also keeps the whole thing swappable
later (e.g. for a webhook-based v2) without reminder_logic or the UI
needing to change - they only ever see `ConnectedAccount` or an error
string.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import requests

from config import telegram_config
from app_utils.logger import get_logger

logger = get_logger(__name__)

_API_BASE = "https://api.telegram.org"
_TIMEOUT_SECONDS = 15

_NOT_CONFIGURED_MESSAGE = (
    "Telegram isn't configured on this installation yet. "
    "Please contact the LawyerTracker developer."
)
_NO_START_YET_MESSAGE = (
    "We couldn't find a message from you yet. Please make sure you opened Telegram "
    "and pressed START on the bot, then click Verify Connection again."
)


@dataclass
class ConnectedAccount:
    chat_id: str
    display_name: str
    username: str  # without the leading "@"; may be "" if the user has no Telegram username


class TelegramAuthService:
    def is_configured(self) -> bool:
        """Whether an app-owner bot token is available at all."""
        return bool(telegram_config.get_bot_token())

    def get_connect_url(self) -> str:
        """The t.me deep link 'Connect Telegram' should open."""
        return f"https://t.me/{telegram_config.BOT_USERNAME}"

    def verify_connection(self) -> tuple[bool, Optional[ConnectedAccount], Optional[str]]:
        """
        Looks for the advocate's most recent message to the bot (they
        should have just pressed START) and, if found, returns their
        account details and clears it from Telegram's update queue.

        Returns (True, ConnectedAccount, None) on success, or
        (False, None, reason) otherwise. Never raises.
        """
        token = telegram_config.get_bot_token()
        if not token:
            logger.warning("Verify Connection attempted with no bot token configured.")
            return False, None, _NOT_CONFIGURED_MESSAGE

        url = f"{_API_BASE}/bot{token}/getUpdates"
        try:
            response = requests.get(url, timeout=_TIMEOUT_SECONDS)
        except requests.exceptions.RequestException as exc:
            reason = f"Network error while contacting Telegram: {exc}"
            logger.error(reason)
            return False, None, reason

        if response.status_code != 200:
            try:
                description = response.json().get("description", response.text)
            except ValueError:
                description = response.text
            reason = f"Telegram API returned HTTP {response.status_code}: {description}"
            logger.error(reason)
            return False, None, reason

        body = response.json()
        if not body.get("ok"):
            reason = f"Telegram API rejected the request: {body.get('description', 'unknown error')}"
            logger.error(reason)
            return False, None, reason

        results = body.get("result", [])
        if not results:
            logger.info("Verify Connection: no pending updates yet.")
            return False, None, _NO_START_YET_MESSAGE

        latest = results[-1]
        update_id = latest.get("update_id")
        message = latest.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")

        if chat_id is None:
            logger.warning("Verify Connection: latest update had no usable chat id: %r", latest)
            return False, None, _NO_START_YET_MESSAGE

        first_name = (chat.get("first_name") or "").strip()
        last_name = (chat.get("last_name") or "").strip()
        display_name = " ".join(part for part in (first_name, last_name) if part) or "Telegram User"
        username = (chat.get("username") or "").strip()

        account = ConnectedAccount(chat_id=str(chat_id), display_name=display_name, username=username)

        if update_id is not None:
            self._clear_updates(token, update_id)

        logger.info("Telegram account connected: chat_id=%s username=%s", account.chat_id, username)
        return True, account, None

    def _clear_updates(self, token: str, last_update_id: int) -> None:
        """
        Acknowledges every update up to and including `last_update_id`
        so Telegram stops returning it. A plain GET with the `offset`
        parameter is how the Bot API's getUpdates confirms receipt -
        no separate "ack" endpoint exists. Best-effort: if this fails,
        we've still connected successfully, so we only log a warning
        rather than surfacing an error to the advocate.
        """
        url = f"{_API_BASE}/bot{token}/getUpdates"
        try:
            requests.get(url, params={"offset": last_update_id + 1}, timeout=_TIMEOUT_SECONDS)
        except requests.exceptions.RequestException as exc:
            logger.warning("Failed to clear Telegram update queue after connecting: %s", exc)
