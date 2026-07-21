"""
reminder_logic.py

All the DECISIONS and TEXT GENERATION for the Telegram reminder
feature, with no threading and no Tkinter in this file. This is the
"business logic" layer your brief asks to keep portable to a future
Flutter build: a Flutter/Dart port only needs to reimplement
`reminder_scheduler.py`'s sleep-loop (WorkManager instead of a Python
thread) and call equivalent logic - the rules for "what does the
message say" and "is it time yet" don't change.

Everything here reads/writes through the existing `app_config`
key/value table via ConfigService, so no schema changes were needed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from database import get_connection
from models.case import Case
from app_utils.logger import get_logger

logger = get_logger(__name__)

# --- app_config keys ---------------------------------------------------
# Note: there is deliberately no KEY_BOT_TOKEN here. The bot token is an
# app-owner secret loaded via config/telegram_config.py (env var or
# telegram_config.json) - it never touches this per-advocate SQLite
# table, and the UI never reads or writes it.
KEY_ENABLED = "telegram_enabled"
KEY_CHAT_ID = "telegram_chat_id"
KEY_TG_DISPLAY_NAME = "telegram_display_name"
KEY_TG_USERNAME = "telegram_username"
KEY_REMINDER_TIME = "reminder_time"          # "HH:MM", 24-hour
KEY_LAST_SENT = "last_reminder_sent"         # "YYYY-MM-DD"

DEFAULT_REMINDER_TIME = "20:00"


@dataclass
class ReminderSettings:
    enabled: bool
    chat_id: str
    tg_display_name: str
    tg_username: str
    reminder_time: str        # "HH:MM"
    last_reminder_sent: str   # "YYYY-MM-DD" or ""

    @property
    def is_connected(self) -> bool:
        return bool(self.chat_id)


# ------------------------------------------------------------------
# Settings persistence (reuses the existing app_config table)
# ------------------------------------------------------------------

def load_settings(config_service) -> ReminderSettings:
    return ReminderSettings(
        enabled=config_service.get(KEY_ENABLED, "0") == "1",
        chat_id=config_service.get(KEY_CHAT_ID, "") or "",
        tg_display_name=config_service.get(KEY_TG_DISPLAY_NAME, "") or "",
        tg_username=config_service.get(KEY_TG_USERNAME, "") or "",
        reminder_time=config_service.get(KEY_REMINDER_TIME, DEFAULT_REMINDER_TIME) or DEFAULT_REMINDER_TIME,
        last_reminder_sent=config_service.get(KEY_LAST_SENT, "") or "",
    )


def save_prefs(config_service, *, enabled: bool, reminder_time: str) -> None:
    """Saves the advocate-editable prefs: enabled + reminder time. Never touches the connection fields."""
    config_service.set(KEY_ENABLED, "1" if enabled else "0")
    config_service.set(KEY_REMINDER_TIME, reminder_time.strip())
    logger.info("Reminder prefs saved (enabled=%s, time=%s)", enabled, reminder_time)


def save_connection(config_service, *, chat_id: str, display_name: str, username: str) -> None:
    """Persists a newly-verified Telegram account. Called once, right after Verify Connection succeeds."""
    config_service.set(KEY_CHAT_ID, chat_id)
    config_service.set(KEY_TG_DISPLAY_NAME, display_name)
    config_service.set(KEY_TG_USERNAME, username)
    logger.info("Telegram account connection saved (chat_id=%s).", chat_id)


def clear_connection(config_service) -> None:
    """Disconnects: removes the chat id/username/display name and turns reminders off."""
    config_service.set(KEY_CHAT_ID, "")
    config_service.set(KEY_TG_DISPLAY_NAME, "")
    config_service.set(KEY_TG_USERNAME, "")
    config_service.set(KEY_ENABLED, "0")
    logger.info("Telegram account disconnected.")


def mark_sent_today(config_service, *, on: Optional[date] = None) -> None:
    day = (on or date.today()).isoformat()
    config_service.set(KEY_LAST_SENT, day)


# ------------------------------------------------------------------
# Timing decisions
# ------------------------------------------------------------------

def parse_reminder_time(reminder_time: str) -> tuple[int, int]:
    """Parse 'HH:MM' -> (hour, minute). Falls back to the default on bad input."""
    try:
        hour_str, minute_str = reminder_time.strip().split(":")
        hour, minute = int(hour_str), int(minute_str)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    except (ValueError, AttributeError):
        pass
    logger.warning("Invalid reminder_time %r, falling back to default.", reminder_time)
    hour_str, minute_str = DEFAULT_REMINDER_TIME.split(":")
    return int(hour_str), int(minute_str)


def next_fire_datetime(reminder_time: str, *, now: Optional[datetime] = None) -> datetime:
    """
    Next wall-clock moment the reminder should fire: today at
    reminder_time if that's still in the future, otherwise tomorrow at
    reminder_time.
    """
    now = now or datetime.now()
    hour, minute = parse_reminder_time(reminder_time)
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def already_sent_today(last_reminder_sent: str, *, today: Optional[date] = None) -> bool:
    today = today or date.today()
    return last_reminder_sent == today.isoformat()


# ------------------------------------------------------------------
# Data: cases due tomorrow
# ------------------------------------------------------------------

def get_cases_due_tomorrow(*, today: Optional[date] = None) -> list[Case]:
    tomorrow = (today or date.today()) + timedelta(days=1)
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM cases WHERE next_hearing_iso = ? ORDER BY court_name, case_number",
            (tomorrow.isoformat(),),
        ).fetchall()
        return [Case.from_row(row) for row in rows]


# ------------------------------------------------------------------
# Message generation - exact formats from the spec
# ------------------------------------------------------------------

_DIVIDER = "━━━━━━━━━━━━━━━━━━━━━━"


def _greeting() -> str:
    # "Good Evening" is what the spec's sample shows; the reminder is a
    # once-a-day evening-style message regardless of the exact hour configured.
    return "Good Evening"


def _tomorrow_display(today: Optional[date] = None) -> str:
    tomorrow = (today or date.today()) + timedelta(days=1)
    return tomorrow.strftime("%d %B %Y")


def build_reminder_message(advocate_name: str, cases: list[Case], *, today: Optional[date] = None) -> str:
    name = advocate_name or "Advocate"
    tomorrow_str = _tomorrow_display(today)

    if not cases:
        return (
            "🔔 LawyerTracker Reminder\n\n"
            f"{_greeting()}, Adv. {name}.\n\n"
            "You have no hearings scheduled for tomorrow.\n\n"
            f"{_DIVIDER}\n\n"
            "No cases matched tomorrow's date from your locally saved records.\n\n"
            "If you recently refreshed or added new cases, please open LawyerTracker "
            "and verify the latest official eCourts status.\n\n"
            "Have a productive day.\n\n"
            "Regards,\n"
            "LawyerTracker"
        )

    lines = [
        "🔔 LawyerTracker Reminder",
        "",
        f"{_greeting()}, Adv. {name}.",
        "",
        f"Tomorrow you have {len(cases)} hearing(s).",
        "",
        _DIVIDER,
    ]

    courts = set()
    for i, case in enumerate(cases, start=1):
        title = f"{case.petitioner or '?'} vs {case.respondent or '?'}"
        courts.add(case.court_name or "")
        lines += [
            "",
            f"📂 CASE {i}",
            "",
            "Case No:",
            case.case_number or case.cnr or "-",
            "",
            "Title:",
            title,
            "",
            "Court:",
            case.court_name or "-",
            "",
            "Stage:",
            case.case_stage or "-",
            "",
            "Hearing Date:",
            tomorrow_str,
            "",
            _DIVIDER,
        ]

    courts.discard("")
    lines += [
        "",
        "📊 Tomorrow Summary",
        "",
        "⚖ Hearings :",
        str(len(cases)),
        "",
        "🏛 Courts :",
        str(len(courts) or 1),
        "",
        "--------------------------------",
        "",
        "⚠ Reminder generated from your locally saved cases.",
        "",
        "Please refresh LawyerTracker before attending court because hearing dates, "
        "stage or case status may have changed on the official eCourts portal.",
        "",
        "Regards,",
        "LawyerTracker",
    ]
    return "\n".join(lines)
