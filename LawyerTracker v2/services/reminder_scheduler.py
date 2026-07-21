"""
reminder_scheduler.py

The ONLY part of this feature that is Python-thread-specific. Runs the
flow from the spec on a background daemon thread:

    Load Reminder Time -> Sleep Until Next Check -> Reminder Time Reached
    -> Generate Message -> Send Telegram -> Update last_reminder_sent
    -> Calculate Tomorrow's Reminder -> Sleep Again

If this were ported to Flutter, only this file's job (deciding *when*
to wake up) would be replaced by WorkManager / flutter_local_notifications;
`reminder_logic.py`'s message-building and timing rules stay identical.

Design decisions:
  - A `threading.Event` is used instead of plain `time.sleep(seconds)`
    for the long wait, so the thread wakes up immediately (rather than
    up to a day later) when the user changes settings or clicks
    "Send Reminder Now" - `wake()` sets the event, the loop clears it
    and recomputes.
  - The wait is chunked (checked every few seconds against the event)
    so `stop()` on app close doesn't hang waiting for a full day-long
    sleep to finish.
  - The whole cycle body is wrapped in try/except: a Telegram outage,
    a network error, or any unexpected bug logs and retries after a
    short backoff instead of killing the thread or the app.
"""
from __future__ import annotations

import threading
import time
from datetime import date, datetime

from app_utils.logger import get_logger
from config import telegram_config
from services import reminder_logic
from services.telegram_service import TelegramService

logger = get_logger(__name__)

_WAIT_CHUNK_SECONDS = 5
_ERROR_BACKOFF_SECONDS = 60


class ReminderScheduler:
    """
    Owns one background thread for the app's lifetime. Started once
    from ui/app.py after all services exist; stopped once on app close.
    """

    def __init__(self, config_service, profile_service, telegram_service: TelegramService | None = None):
        self.config_service = config_service
        self.profile_service = profile_service
        self.telegram_service = telegram_service or TelegramService()

        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="ReminderScheduler")
        self._thread.start()
        logger.info("Reminder scheduler started.")

    def stop(self, timeout: float = 3.0) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        logger.info("Reminder scheduler stopped.")

    def wake(self) -> None:
        """Call after Settings are saved so a new reminder_time takes effect immediately."""
        self._wake_event.set()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._cycle_once()
            except Exception:
                logger.exception("Reminder scheduler cycle failed; will retry after backoff.")
                self._sleep_interruptible(_ERROR_BACKOFF_SECONDS)

    def _cycle_once(self) -> None:
        settings = reminder_logic.load_settings(self.config_service)

        if not settings.enabled:
            # Nothing to schedule while disabled - just wait to be woken
            # (e.g. when the user enables it and saves) or poll slowly.
            self._sleep_interruptible(_WAIT_CHUNK_SECONDS * 12)
            return

        target = reminder_logic.next_fire_datetime(settings.reminder_time)
        self._sleep_until(target)

        if self._stop_event.is_set():
            return

        # Re-read settings in case they changed while sleeping (e.g. got disabled).
        settings = reminder_logic.load_settings(self.config_service)
        if not settings.enabled:
            return

        now = datetime.now()
        if reminder_logic.already_sent_today(settings.last_reminder_sent, today=now.date()):
            # Already handled today (e.g. app restarted right after sending).
            # Sleep past this exact minute so we don't spin-fire repeatedly.
            self._sleep_interruptible(_WAIT_CHUNK_SECONDS * 12)
            return

        self.send_reminder_now(reason="scheduled")

    # ------------------------------------------------------------------
    # Sending (shared by the scheduled path and "Send Reminder Now")
    # ------------------------------------------------------------------

    def send_reminder_now(self, *, reason: str = "manual") -> tuple[bool, str]:
        """
        Generate + send today's reminder immediately. Used by both the
        scheduled cycle and the Settings screen's "Send Reminder Now"
        test button. Only the scheduled path's caller updates
        last_reminder_sent as part of _cycle_once's contract - actually,
        to keep "duplicate prevention" correct regardless of caller, we
        only stamp last_reminder_sent when reason == "scheduled".
        """
        settings = reminder_logic.load_settings(self.config_service)

        bot_token = telegram_config.get_bot_token()
        if not bot_token:
            msg = "Telegram bot is not configured on this installation."
            logger.warning(msg)
            return False, msg

        if not settings.chat_id:
            msg = "No Telegram account connected yet."
            logger.warning(msg)
            return False, msg

        profile = self.profile_service.get_profile()
        cases = reminder_logic.get_cases_due_tomorrow()
        message = reminder_logic.build_reminder_message(profile.advocate_name, cases)

        success, error = self.telegram_service.send_message(
            bot_token, settings.chat_id, message
        )

        if success and reason == "scheduled":
            reminder_logic.mark_sent_today(self.config_service)
            logger.info("Scheduled reminder sent (%d hearing(s) tomorrow).", len(cases))

        return success, (error or "Sent.")

    # ------------------------------------------------------------------
    # Sleep helpers
    # ------------------------------------------------------------------

    def _sleep_until(self, target: datetime) -> None:
        while not self._stop_event.is_set():
            remaining = (target - datetime.now()).total_seconds()
            if remaining <= 0:
                return
            if self._wake_event.wait(timeout=min(_WAIT_CHUNK_SECONDS, remaining)):
                # Woken early (settings changed) - recompute the target
                # from fresh settings rather than keep waiting on a
                # possibly-stale one.
                self._wake_event.clear()
                fresh = reminder_logic.load_settings(self.config_service)
                if not fresh.enabled:
                    return
                target = reminder_logic.next_fire_datetime(fresh.reminder_time)

    def _sleep_interruptible(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while not self._stop_event.is_set():
            remaining = end - time.monotonic()
            if remaining <= 0:
                return
            if self._wake_event.wait(timeout=min(_WAIT_CHUNK_SECONDS, remaining)):
                self._wake_event.clear()
                return
