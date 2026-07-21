"""
settings_screen.py

Shows where the app's data lives, lets the advocate update their name/
default court, and - this is how OCR gets "set up" - a Browse button
that points the app at a local KevinOCR folder with no code editing
required. Nothing here can auto-submit a CAPTCHA; this only controls
whether the Suggest button on the CAPTCHA screen has anything to offer.
"""
from __future__ import annotations

import threading
from tkinter import filedialog

import customtkinter as ctk

from config import settings
from models.profile import Profile
from services import reminder_logic
from ui import theme
from app_utils.logger import get_logger

logger = get_logger(__name__)

_KEVINOCR_CONFIG_KEY = "kevinocr_dir"


class SettingsScreen(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text="Settings", font=theme.font_heading()
        ).grid(row=0, column=0, sticky="w", padx=theme.SPACE_LG, pady=(theme.SPACE_LG, theme.SPACE_MD))

        self._build_profile_section()
        self._build_ocr_section()
        self._build_reminder_section()
        self._build_info_section()
        self._build_actions_section()

    # ------------------------------------------------------------------
    # Profile
    # ------------------------------------------------------------------

    def _build_profile_section(self) -> None:
        frame = ctk.CTkFrame(self, corner_radius=theme.CARD_RADIUS)
        frame.grid(row=1, column=0, sticky="ew", padx=theme.SPACE_LG, pady=(0, 16))
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="Your Profile", font=theme.font_subheading()).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 8)
        )

        ctk.CTkLabel(frame, text="Name").grid(row=1, column=0, sticky="w", padx=12, pady=6)
        self.name_entry = ctk.CTkEntry(frame, width=300)
        self.name_entry.grid(row=1, column=1, sticky="w", padx=12, pady=6)

        self.court_label = ctk.CTkLabel(frame, text="", text_color=theme.COLOR_MUTED, justify="left")
        self.court_label.grid(row=2, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 8))

        ctk.CTkButton(
            frame, text="Save Name", width=120, command=self._save_name
        ).grid(row=3, column=0, sticky="w", padx=12, pady=(0, 12))
        ctk.CTkLabel(
            frame, text="(To change your default court, redo it from the search screen's "
                        "location picker - it's just used to prefill, not locked in.)",
            text_color=theme.COLOR_MUTED, font=ctk.CTkFont(size=11),
        ).grid(row=3, column=1, sticky="w", padx=12, pady=(0, 12))

    def _save_name(self) -> None:
        name = self.name_entry.get().strip()
        if not name:
            self.app.show_error("Name required", "Please enter your name.")
            return
        profile = self.app.profile_service.get_profile()
        profile.advocate_name = name
        self.app.profile_service.save_profile(profile)
        self.app.profile = profile
        self.app._update_greeting()
        self.app.show_error("Saved", "Your name has been updated.")

    # ------------------------------------------------------------------
    # KevinOCR setup
    # ------------------------------------------------------------------

    def _build_ocr_section(self) -> None:
        frame = ctk.CTkFrame(self, corner_radius=theme.CARD_RADIUS)
        frame.grid(row=2, column=0, sticky="ew", padx=theme.SPACE_LG, pady=(0, 16))
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="CAPTCHA OCR Assist (KevinOCR)", font=theme.font_subheading()).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(12, 4)
        )
        ctk.CTkLabel(
            frame,
            text="Point this at your KevinOCR project folder (the one containing ocr/engine.py) "
                 "to enable the 'OCR-assisted' mode on the CAPTCHA screen. It only pre-fills a "
                 "suggestion - you still review and click Submit yourself. Leave unset to use "
                 "manual entry only.",
            text_color=theme.COLOR_MUTED, wraplength=560, justify="left",
        ).grid(row=1, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 10))

        self.ocr_path_entry = ctk.CTkEntry(frame, width=380, placeholder_text="(not set)")
        self.ocr_path_entry.grid(row=2, column=0, columnspan=2, sticky="ew", padx=(12, 6), pady=(0, 8))

        ctk.CTkButton(frame, text="Browse...", width=100, command=self._browse_ocr_dir).grid(
            row=2, column=2, sticky="w", padx=(0, 12), pady=(0, 8)
        )

        button_row = ctk.CTkFrame(frame, fg_color="transparent")
        button_row.grid(row=3, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 12))
        ctk.CTkButton(button_row, text="Save", width=100, command=self._save_ocr_dir).pack(
            side="left", padx=(0, 8)
        )
        self.ocr_status_label = ctk.CTkLabel(button_row, text="Checking...")
        self.ocr_status_label.pack(side="left")

    def _browse_ocr_dir(self) -> None:
        path = filedialog.askdirectory(title="Select your KevinOCR project folder")
        if path:
            self.ocr_path_entry.delete(0, "end")
            self.ocr_path_entry.insert(0, path)

    def _save_ocr_dir(self) -> None:
        path = self.ocr_path_entry.get().strip()
        self.app.config_service.set(_KEVINOCR_CONFIG_KEY, path)
        available = self.app.captcha_service.ocr_available()
        self.ocr_status_label.configure(
            text="Available" if available else "Folder set, but ocr/engine.py wasn't importable "
                                                 "from it - check the path."
        )
        if available:
            self.app.show_error("Saved", "KevinOCR is now available on the CAPTCHA screen.")

    # ------------------------------------------------------------------
    # Telegram Reminder
    # ------------------------------------------------------------------

    def _build_reminder_section(self) -> None:
        frame = ctk.CTkFrame(self, corner_radius=theme.CARD_RADIUS)
        frame.grid(row=3, column=0, sticky="ew", padx=theme.SPACE_LG, pady=(0, 16))
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="Telegram Reminder", font=theme.font_subheading()).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(12, 4)
        )
        ctk.CTkLabel(
            frame,
            text="Sends a daily Telegram message listing tomorrow's hearings from your "
                 "saved cases. Only works while LawyerTracker is running.",
            text_color=theme.COLOR_MUTED, wraplength=560, justify="left",
        ).grid(row=1, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 10))

        self.reminder_enabled_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            frame, text="Enable Telegram Reminder", variable=self.reminder_enabled_var,
        ).grid(row=2, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 10))

        ctk.CTkLabel(frame, text="Bot Token").grid(row=3, column=0, sticky="w", padx=12, pady=6)
        self.bot_token_entry = ctk.CTkEntry(frame, width=380, show="*", placeholder_text="123456:ABC-DEF...")
        self.bot_token_entry.grid(row=3, column=1, columnspan=2, sticky="ew", padx=(0, 12), pady=6)

        ctk.CTkLabel(frame, text="Chat ID").grid(row=4, column=0, sticky="w", padx=12, pady=6)
        self.chat_id_entry = ctk.CTkEntry(frame, width=380, placeholder_text="e.g. 123456789")
        self.chat_id_entry.grid(row=4, column=1, columnspan=2, sticky="ew", padx=(0, 12), pady=6)

        ctk.CTkLabel(frame, text="Reminder Time").grid(row=5, column=0, sticky="w", padx=12, pady=6)
        self.reminder_time_entry = ctk.CTkEntry(frame, width=100, placeholder_text="HH:MM")
        self.reminder_time_entry.grid(row=5, column=1, sticky="w", padx=(0, 12), pady=6)
        ctk.CTkLabel(
            frame, text="24-hour, e.g. 20:00", text_color=theme.COLOR_MUTED, font=ctk.CTkFont(size=11),
        ).grid(row=5, column=2, sticky="w", pady=6)

        button_row = ctk.CTkFrame(frame, fg_color="transparent")
        button_row.grid(row=6, column=0, columnspan=3, sticky="w", padx=12, pady=(4, 6))
        ctk.CTkButton(button_row, text="Save Settings", width=120, command=self._save_reminder_settings).pack(
            side="left", padx=(0, 8)
        )
        self.test_telegram_button = ctk.CTkButton(
            button_row, text="Test Telegram", width=120, command=self._test_telegram
        )
        self.test_telegram_button.pack(side="left", padx=(0, 8))
        self.send_now_button = ctk.CTkButton(
            button_row, text="Send Reminder Now", width=150, command=self._send_reminder_now
        )
        self.send_now_button.pack(side="left")

        self.reminder_status_label = ctk.CTkLabel(frame, text="", text_color=theme.COLOR_MUTED)
        self.reminder_status_label.grid(row=7, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 12))

    def _current_reminder_fields(self) -> tuple[bool, str, str, str]:
        return (
            bool(self.reminder_enabled_var.get()),
            self.bot_token_entry.get().strip(),
            self.chat_id_entry.get().strip(),
            self.reminder_time_entry.get().strip() or reminder_logic.DEFAULT_REMINDER_TIME,
        )

    def _save_reminder_settings(self) -> None:
        enabled, bot_token, chat_id, reminder_time = self._current_reminder_fields()
        hour_min = reminder_time.split(":")
        if len(hour_min) != 2 or not all(part.isdigit() for part in hour_min):
            self.app.show_error("Invalid time", "Reminder Time must be in HH:MM 24-hour format, e.g. 20:00.")
            return

        reminder_logic.save_settings(
            self.app.config_service, enabled=enabled, bot_token=bot_token,
            chat_id=chat_id, reminder_time=reminder_time,
        )
        # Wake the background scheduler so a new time/enabled state takes
        # effect immediately instead of after its current long sleep ends.
        self.app.reminder_scheduler.wake()
        self.reminder_status_label.configure(text="Settings saved.")

    def _set_reminder_buttons_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.test_telegram_button.configure(state=state)
        self.send_now_button.configure(state=state)

    def _test_telegram(self) -> None:
        _, bot_token, chat_id, _ = self._current_reminder_fields()
        if not bot_token or not chat_id:
            self.app.show_error("Missing details", "Enter both Bot Token and Chat ID first.")
            return

        self._set_reminder_buttons_busy(True)
        self.reminder_status_label.configure(text="Sending test message...")

        def worker() -> None:
            success, detail = self.app.telegram_service.send_message(
                bot_token, chat_id, "🔔 LawyerTracker test message. Your Telegram reminder is set up correctly."
            )
            self.after(0, self._on_reminder_action_done, success, detail)

        threading.Thread(target=worker, daemon=True).start()

    def _send_reminder_now(self) -> None:
        _, bot_token, chat_id, _ = self._current_reminder_fields()
        if not bot_token or not chat_id:
            self.app.show_error("Missing details", "Enter both Bot Token and Chat ID first.")
            return

        self._set_reminder_buttons_busy(True)
        self.reminder_status_label.configure(text="Generating and sending reminder...")

        def worker() -> None:
            # Uses whatever is currently saved (Save Settings first if the
            # token/chat id fields were just changed) - this button is for
            # testing the real send path, including message generation.
            success, detail = self.app.reminder_scheduler.send_reminder_now(reason="manual")
            self.after(0, self._on_reminder_action_done, success, detail)

        threading.Thread(target=worker, daemon=True).start()

    def _on_reminder_action_done(self, success: bool, detail: str) -> None:
        self._set_reminder_buttons_busy(False)
        self.reminder_status_label.configure(text=detail if not success else "Sent successfully.")
        if not success:
            self.app.show_error("Telegram send failed", detail)

    # ------------------------------------------------------------------
    # App info
    # ------------------------------------------------------------------

    def _build_info_section(self) -> None:
        frame = ctk.CTkFrame(self, corner_radius=theme.CARD_RADIUS)
        frame.grid(row=4, column=0, sticky="ew", padx=theme.SPACE_LG, pady=(0, 16))
        frame.grid_columnconfigure(1, weight=1)

        rows = [
            ("App version", f"{settings.app_name} v{settings.app_version}"),
            ("Database file", str(settings.db_path)),
            ("Log file", str(settings.log_file)),
            ("eCourts portal", settings.ecourts_base_url),
        ]
        for i, (label, value) in enumerate(rows):
            ctk.CTkLabel(frame, text=label, font=theme.font_subheading()).grid(
                row=i, column=0, sticky="w", padx=12, pady=6
            )
            ctk.CTkLabel(frame, text=value, anchor="w").grid(
                row=i, column=1, sticky="w", padx=12, pady=6
            )

    def _build_actions_section(self) -> None:
        actions_frame = ctk.CTkFrame(self, fg_color="transparent")
        actions_frame.grid(row=5, column=0, sticky="w", padx=theme.SPACE_LG, pady=8)

        ctk.CTkButton(
            actions_frame, text="Clear Search History", command=self._clear_history,
        ).pack(side="left", padx=(0, 8))

    def _clear_history(self) -> None:
        self.app.history_service.clear_search_history()
        self.app.show_error("Done", "Search history cleared.")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_show(self) -> None:
        profile: Profile = self.app.profile_service.get_profile()
        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, profile.advocate_name)
        self.court_label.configure(
            text=f"Default court: {profile.default_court_complex_name or '-'}, "
                 f"{profile.default_dist_name or '-'}, {profile.default_state_name or '-'}"
        )

        current_path = self.app.config_service.get(_KEVINOCR_CONFIG_KEY) or ""
        self.ocr_path_entry.delete(0, "end")
        self.ocr_path_entry.insert(0, current_path)

        available = self.app.captcha_service.ocr_available()
        self.ocr_status_label.configure(
            text="Available" if available else "Not available (manual entry only)"
        )

        reminder_settings = reminder_logic.load_settings(self.app.config_service)
        self.reminder_enabled_var.set(reminder_settings.enabled)
        self.bot_token_entry.delete(0, "end")
        self.bot_token_entry.insert(0, reminder_settings.bot_token)
        self.chat_id_entry.delete(0, "end")
        self.chat_id_entry.insert(0, reminder_settings.chat_id)
        self.reminder_time_entry.delete(0, "end")
        self.reminder_time_entry.insert(0, reminder_settings.reminder_time)
        self.reminder_status_label.configure(text="")
