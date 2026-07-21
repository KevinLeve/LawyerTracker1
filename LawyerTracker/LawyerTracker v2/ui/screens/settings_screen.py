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
import webbrowser
from tkinter import filedialog

import customtkinter as ctk

from config import settings, telegram_config
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
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frame, text="Telegram Reminder", font=theme.font_subheading()).grid(
            row=0, column=0, sticky="w", padx=12, pady=(12, 4)
        )

        # Everything below the title is rebuilt by _render_reminder_body()
        # each time the connection state changes (not connected -> awaiting
        # START -> connected), so this card only ever shows what's relevant
        # to the advocate's current step - never a Bot Token or Chat ID field.
        self.reminder_body = ctk.CTkFrame(frame, fg_color="transparent")
        self.reminder_body.grid(row=1, column=0, sticky="ew", padx=0, pady=(0, 8))
        self.reminder_body.grid_columnconfigure(0, weight=1)

        self._tg_state = "not_connected"  # "not_connected" | "awaiting_start" | "connected"
        self._tg_busy = False

    def _clear_reminder_body(self) -> None:
        for child in self.reminder_body.winfo_children():
            child.destroy()

    def _render_reminder_body(self) -> None:
        if self._tg_state == "connected":
            self._render_connected_view()
        elif self._tg_state == "awaiting_start":
            self._render_awaiting_start_view()
        else:
            self._render_not_connected_view()

    # -- Step 1: Not Connected -----------------------------------------

    def _render_not_connected_view(self) -> None:
        self._clear_reminder_body()
        body = self.reminder_body

        ctk.CTkLabel(
            body, text="❌ Not Connected", text_color=theme.COLOR_MUTED,
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(0, 4))

        ctk.CTkLabel(
            body,
            text="This feature sends daily Telegram reminders of tomorrow's hearings.",
            text_color=theme.COLOR_MUTED, wraplength=560, justify="left",
        ).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 10))

        connect_button = ctk.CTkButton(body, text="Connect Telegram", width=160, command=self._on_connect_telegram)
        connect_button.grid(row=2, column=0, sticky="w", padx=12, pady=(0, 12))

        if not self.app.telegram_auth_service.is_configured():
            connect_button.configure(state="disabled")
            ctk.CTkLabel(
                body, text="Telegram isn't set up on this installation yet - contact the developer.",
                text_color=theme.COLOR_MUTED, font=ctk.CTkFont(size=11), wraplength=560, justify="left",
            ).grid(row=3, column=0, sticky="w", padx=12, pady=(0, 12))

    def _on_connect_telegram(self) -> None:
        webbrowser.open(self.app.telegram_auth_service.get_connect_url())
        self._tg_state = "awaiting_start"
        self._render_reminder_body()

    # -- Step 2: Awaiting the advocate to press START -------------------

    def _render_awaiting_start_view(self) -> None:
        self._clear_reminder_body()
        body = self.reminder_body

        ctk.CTkLabel(
            body,
            text="Telegram has been opened.\nPlease press START on the bot.\n"
                 "Then return here and click Verify Connection.",
            justify="left",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(0, 10))

        self.verify_button = ctk.CTkButton(
            body, text="Verify Connection", width=160, command=self._on_verify_connection
        )
        self.verify_button.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 8))

        self.reminder_status_label = ctk.CTkLabel(body, text="", text_color=theme.COLOR_MUTED, wraplength=560, justify="left")
        self.reminder_status_label.grid(row=2, column=0, sticky="w", padx=12, pady=(0, 12))

    def _on_verify_connection(self) -> None:
        if self._tg_busy:
            return
        self._tg_busy = True
        self.verify_button.configure(state="disabled")
        self.reminder_status_label.configure(text="Checking Telegram...")

        def worker() -> None:
            success, account, error = self.app.telegram_auth_service.verify_connection()
            self.after(0, self._on_verify_done, success, account, error)

        threading.Thread(target=worker, daemon=True).start()

    def _on_verify_done(self, success: bool, account, error) -> None:
        self._tg_busy = False
        if not success:
            self.verify_button.configure(state="normal")
            self.reminder_status_label.configure(text=error or "Verification failed. Please try again.")
            return

        reminder_logic.save_connection(
            self.app.config_service, chat_id=account.chat_id,
            display_name=account.display_name, username=account.username,
        )
        self._tg_state = "connected"
        self._render_reminder_body()

    # -- Step 3: Connected ------------------------------------------------

    def _render_connected_view(self) -> None:
        self._clear_reminder_body()
        body = self.reminder_body
        reminder_settings = reminder_logic.load_settings(self.app.config_service)

        ctk.CTkLabel(body, text="🟢 Connected", text_color=theme.COLOR_SUCCESS).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 8)
        )

        ctk.CTkLabel(body, text="Telegram Account", text_color=theme.COLOR_MUTED, font=ctk.CTkFont(size=11)).grid(
            row=1, column=0, sticky="w", padx=12
        )
        ctk.CTkLabel(body, text=reminder_settings.tg_display_name or "-").grid(
            row=2, column=0, sticky="w", padx=12, pady=(0, 8)
        )

        ctk.CTkLabel(body, text="Username", text_color=theme.COLOR_MUTED, font=ctk.CTkFont(size=11)).grid(
            row=1, column=1, sticky="w", padx=12
        )
        ctk.CTkLabel(
            body, text=f"@{reminder_settings.tg_username}" if reminder_settings.tg_username else "-"
        ).grid(row=2, column=1, sticky="w", padx=12, pady=(0, 8))

        ctk.CTkLabel(body, text="Reminder Time").grid(row=3, column=0, sticky="w", padx=12, pady=6)
        time_row = ctk.CTkFrame(body, fg_color="transparent")
        time_row.grid(row=3, column=1, sticky="w", padx=12, pady=6)
        self.reminder_time_entry = ctk.CTkEntry(time_row, width=90, placeholder_text="HH:MM")
        self.reminder_time_entry.insert(0, reminder_settings.reminder_time)
        self.reminder_time_entry.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(time_row, text="24-hour, e.g. 20:00", text_color=theme.COLOR_MUTED, font=ctk.CTkFont(size=11)).pack(side="left")

        self.reminder_enabled_var = ctk.BooleanVar(value=reminder_settings.enabled)
        ctk.CTkCheckBox(
            body, text="Enable Telegram Reminder", variable=self.reminder_enabled_var,
            command=self._save_reminder_prefs,
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=12, pady=(4, 10))

        button_row = ctk.CTkFrame(body, fg_color="transparent")
        button_row.grid(row=5, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 6))
        ctk.CTkButton(button_row, text="Save Reminder Time", width=140, command=self._save_reminder_prefs).pack(
            side="left", padx=(0, 8)
        )
        self.test_telegram_button = ctk.CTkButton(
            button_row, text="Test Notification", width=140, command=self._test_telegram
        )
        self.test_telegram_button.pack(side="left", padx=(0, 8))
        self.disconnect_button = ctk.CTkButton(
            button_row, text="Disconnect", width=110,
            fg_color=theme.COLOR_DANGER_BG, text_color=theme.COLOR_DANGER,
            command=self._on_disconnect,
        )
        self.disconnect_button.pack(side="left")

        self.reminder_status_label = ctk.CTkLabel(body, text="", text_color=theme.COLOR_MUTED, wraplength=560, justify="left")
        self.reminder_status_label.grid(row=6, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 12))

    def _save_reminder_prefs(self) -> None:
        reminder_time = self.reminder_time_entry.get().strip() or reminder_logic.DEFAULT_REMINDER_TIME
        hour_min = reminder_time.split(":")
        if len(hour_min) != 2 or not all(part.isdigit() for part in hour_min):
            self.app.show_error("Invalid time", "Reminder Time must be in HH:MM 24-hour format, e.g. 20:00.")
            return

        reminder_logic.save_prefs(
            self.app.config_service, enabled=bool(self.reminder_enabled_var.get()), reminder_time=reminder_time,
        )
        # Wake the background scheduler so a new time/enabled state takes
        # effect immediately instead of after its current long sleep ends.
        self.app.reminder_scheduler.wake()
        self.reminder_status_label.configure(text="Saved.")

    def _set_reminder_buttons_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.test_telegram_button.configure(state=state)
        self.disconnect_button.configure(state=state)

    def _test_telegram(self) -> None:
        self._set_reminder_buttons_busy(True)
        self.reminder_status_label.configure(text="Sending test message...")

        test_message = (
            "🧪 LawyerTracker Test\n\n"
            "Telegram notifications are working correctly.\n\n"
            "No reminder will be missed while LawyerTracker is running.\n\n"
            "Regards,\nLawyerTracker"
        )

        def worker() -> None:
            reminder_settings = reminder_logic.load_settings(self.app.config_service)
            bot_token = telegram_config.get_bot_token()
            if not bot_token or not reminder_settings.chat_id:
                self.after(0, self._on_reminder_action_done, False, "Telegram isn't connected.")
                return
            success, detail = self.app.telegram_service.send_message(
                bot_token, reminder_settings.chat_id, test_message
            )
            self.after(0, self._on_reminder_action_done, success, detail)

        threading.Thread(target=worker, daemon=True).start()

    def _on_reminder_action_done(self, success: bool, detail: str) -> None:
        self._set_reminder_buttons_busy(False)
        self.reminder_status_label.configure(text=detail if not success else "Sent successfully.")
        if not success:
            self.app.show_error("Telegram send failed", detail)

    def _on_disconnect(self) -> None:
        reminder_logic.clear_connection(self.app.config_service)
        self.app.reminder_scheduler.wake()
        self._tg_state = "not_connected"
        self._render_reminder_body()

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
        self._tg_state = "connected" if reminder_settings.is_connected else "not_connected"
        self._render_reminder_body()
