"""
onboarding_screen.py

Shown once, on first launch (before a Profile exists). Collects the
advocate's name and their primary practicing court (state/district/
complex), which then prefill every search form afterward so they're
not re-selecting the same court on every single search.

This is a single-advocate desktop app - there's no login, no accounts,
just this one-time setup.
"""
from __future__ import annotations

import customtkinter as ctk

from models.profile import Profile
from ui import theme
from ui.widgets.location_picker import LocationPicker
from app_utils.logger import get_logger

logger = get_logger(__name__)


class OnboardingScreen(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        card = ctk.CTkFrame(self, width=520, corner_radius=theme.CARD_RADIUS)
        card.grid(row=0, column=0, pady=40)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text="\u2696", font=ctk.CTkFont(size=36), text_color=theme.COLOR_ACCENT,
        ).grid(row=0, column=0, padx=40, pady=(36, 8), sticky="w")

        ctk.CTkLabel(
            card, text="Welcome to LawyerTracker", font=theme.font_heading(),
        ).grid(row=1, column=0, padx=40, pady=(0, 4), sticky="w")

        ctk.CTkLabel(
            card,
            text="Quick one-time setup - tell us your name and the court you "
                 "primarily practice in, and every search will be pre-filled "
                 "with it from now on.",
            wraplength=440, justify="left", text_color=theme.COLOR_MUTED, font=theme.font_body(),
        ).grid(row=2, column=0, padx=40, pady=(0, 24), sticky="w")

        ctk.CTkLabel(card, text="Your Name", font=theme.font_subheading()).grid(
            row=3, column=0, padx=40, sticky="w"
        )
        self.name_entry = ctk.CTkEntry(card, placeholder_text="e.g. R. Kumar", width=440, height=36)
        self.name_entry.grid(row=4, column=0, padx=40, pady=(6, 22), sticky="w")

        ctk.CTkLabel(card, text="Primary Court You Practice In", font=theme.font_subheading()).grid(
            row=5, column=0, padx=40, sticky="w"
        )
        self.location_picker = LocationPicker(
            card, self.app.location_service, on_error=self.app.show_error
        )
        self.location_picker.grid(row=6, column=0, padx=40, pady=(6, 28), sticky="ew")

        ctk.CTkButton(
            card, text="Get Started", command=self._submit, width=180, height=38,
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=7, column=0, padx=40, pady=(0, 36), sticky="w")

    def _submit(self) -> None:
        name = self.name_entry.get().strip()
        if not name:
            self.app.show_error("Name required", "Please enter your name.")
            return
        location = self.location_picker.get_selection_full()
        if not location:
            self.app.show_error(
                "Court required", "Please select the state, district, and court complex."
            )
            return

        profile = Profile(
            advocate_name=name,
            default_state_code=location["state_code"], default_state_name=location["state_name"],
            default_dist_code=location["dist_code"], default_dist_name=location["dist_name"],
            default_court_complex_code=location["court_complex_code"],
            default_court_complex_name=location["court_complex_name"],
        )
        self.app.profile_service.save_profile(profile)
        self.app.profile = profile
        logger.info("Onboarding complete for %s", name)
        self.app.on_onboarding_complete()
