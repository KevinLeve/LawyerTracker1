"""
app.py

Main application window. Owns:
  - The single EcourtsClient / service instances (shared session state -
    e.g. CAPTCHA cookies must persist across screens).
  - The one-time onboarding flow (advocate name + primary court), shown
    before anything else if no Profile exists yet.
  - A sidebar for navigation between Search / My Cases / Settings, with
    active-screen highlighting and a profile card.
  - A content area that swaps between screen frames.

Design decision: screens are plain CTkFrame subclasses that receive the
`app` (this class) in their constructor, so they can call
`self.app.show_screen(...)` to navigate and reach `self.app.<service>`
for data - this avoids passing a long chain of callbacks through every
screen constructor.
"""
from __future__ import annotations

import customtkinter as ctk

from api.ecourts_client import EcourtsClient
from config import settings
from database import init_database
from models.profile import Profile
from services.captcha_service import CaptchaService
from services.config_service import ConfigService
from services.history_service import HistoryService
from services.location_service import LocationService
from services.profile_service import ProfileService
from services.search_service import SearchService
from services.telegram_service import TelegramService
from services.reminder_scheduler import ReminderScheduler
from ui import theme
from ui.screens.captcha_screen import CaptchaScreen
from ui.screens.home_screen import HomeScreen
from ui.screens.my_cases_screen import MyCasesScreen
from ui.screens.onboarding_screen import OnboardingScreen
from ui.screens.results_screen import ResultsScreen
from ui.screens.settings_screen import SettingsScreen
from app_utils.logger import get_logger

logger = get_logger(__name__)

_NAV_ITEMS = [
    ("\u2315", "Search", "home"),        # compass-ish glyph
    ("\u2696", "My Cases", "my_cases"),  # scales
    ("\u2699", "Settings", "settings"),  # gear
]


class LawyerTrackerApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        theme_path = settings.base_dir / settings.color_theme
        ctk.set_default_color_theme(str(theme_path))
        ctk.set_appearance_mode(settings.appearance_mode)

        self.title(f"{settings.app_name}")
        self.geometry(f"{settings.window_width}x{settings.window_height}")
        self.minsize(900, 600)

        # Defensive: ensure schema exists even if something constructs
        # this window without going through main.py first.
        init_database()

        # Shared backend state - one client/session for the app's lifetime.
        self.client = EcourtsClient()
        self.location_service = LocationService(self.client)
        self.config_service = ConfigService()
        self.captcha_service = CaptchaService(self.client, self.config_service)
        self.search_service = SearchService(self.client)
        self.history_service = HistoryService()
        self.profile_service = ProfileService()
        self.profile: Profile = self.profile_service.get_profile()
        self.telegram_service = TelegramService()
        self.reminder_scheduler = ReminderScheduler(
            config_service=self.config_service,
            profile_service=self.profile_service,
            telegram_service=self.telegram_service,
        )

        # Holds the search form's chosen params between the Home screen
        # and the CAPTCHA screen, since the search isn't actually
        # submitted until the CAPTCHA is confirmed.
        self.pending_search: dict = {}
        # Holds the most recent results so the Results screen can be
        # rebuilt when navigated back to.
        self.last_results: list = []
        # True right after a search hands off raw (un-enriched) results
        # to Results, before its background enrichment pass has run.
        self.results_need_enrichment: bool = False
        self._active_nav_key: str = "home"
        self._nav_buttons: dict[str, ctk.CTkButton] = {}

        self._build_layout()
        self.screens: dict[str, ctk.CTkFrame] = {}
        self._register_screens()

        if self.profile.is_complete():
            self._update_profile_card()
            self.show_screen("home")
        else:
            self.sidebar.grid_remove()
            self.show_screen("onboarding")

        # Runs silently for the app's lifetime; never blocks the UI thread.
        self.reminder_scheduler.start()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self) -> None:
        self.reminder_scheduler.stop()
        self.destroy()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=210, corner_radius=0, border_width=0)
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_rowconfigure(5, weight=1)

        brand_row = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand_row.grid(row=0, column=0, padx=20, pady=(24, 4), sticky="w")
        ctk.CTkLabel(
            brand_row, text="\u2696", font=ctk.CTkFont(size=20), text_color=theme.COLOR_ACCENT,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            brand_row, text=settings.app_name, font=theme.font_subheading(),
        ).pack(side="left")

        for i, (icon, label, key) in enumerate(_NAV_ITEMS, start=1):
            btn = ctk.CTkButton(
                self.sidebar, text=f"{icon}   {label}", anchor="w",
                fg_color="transparent", text_color=("#1B1E27", "#E7E9EE"),
                hover_color=("#ECEEF1", "#242835"),
                command=lambda k=key: self.show_screen(k),
            )
            btn.grid(row=i, column=0, padx=14, pady=3, sticky="ew")
            self._nav_buttons[key] = btn

        # Profile card, pinned to the bottom of the sidebar.
        self.profile_card = ctk.CTkFrame(self.sidebar, fg_color=("#ECEEF1", "#20242F"))
        self.profile_card.grid(row=6, column=0, padx=14, pady=(8, 20), sticky="ew")
        self.profile_card.grid_columnconfigure(1, weight=1)

        self.avatar_label = ctk.CTkLabel(
            self.profile_card, text="", width=36, height=36, corner_radius=18,
            fg_color=theme.COLOR_ACCENT, text_color="#FFFFFF", font=theme.font_subheading(),
        )
        self.avatar_label.grid(row=0, column=0, rowspan=2, padx=(10, 8), pady=10)

        self.profile_name_label = ctk.CTkLabel(
            self.profile_card, text="", font=ctk.CTkFont(size=12, weight="bold"), anchor="w"
        )
        self.profile_name_label.grid(row=0, column=1, sticky="ew", pady=(10, 0))

        self.profile_court_label = ctk.CTkLabel(
            self.profile_card, text="", font=theme.font_small(),
            text_color=theme.COLOR_MUTED, anchor="w", justify="left",
        )
        self.profile_court_label.grid(row=1, column=1, sticky="ew", pady=(0, 10))

        self.content = ctk.CTkFrame(self, corner_radius=0, border_width=0, fg_color=("#F3F4F6", "#14171F"))
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

    def _register_screens(self) -> None:
        self.screens["onboarding"] = OnboardingScreen(self.content, self)
        self.screens["home"] = HomeScreen(self.content, self)
        self.screens["captcha"] = CaptchaScreen(self.content, self)
        self.screens["results"] = ResultsScreen(self.content, self)
        self.screens["my_cases"] = MyCasesScreen(self.content, self)
        self.screens["settings"] = SettingsScreen(self.content, self)

        for screen in self.screens.values():
            screen.grid(row=0, column=0, sticky="nsew")

    # ------------------------------------------------------------------
    # Onboarding
    # ------------------------------------------------------------------

    def on_onboarding_complete(self) -> None:
        self.sidebar.grid()
        self._update_profile_card()
        self.screens["home"].refresh_profile_defaults()
        self.show_screen("home")

    def _update_profile_card(self) -> None:
        name = self.profile.advocate_name
        if not name:
            return
        initials = "".join(part[0].upper() for part in name.split() if part)[:2] or "?"
        self.avatar_label.configure(text=initials)
        self.profile_name_label.configure(text=f"Adv. {name}")
        court = self.profile.default_court_complex_name or "No default court set"
        self.profile_court_label.configure(text=court)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def show_screen(self, key: str) -> None:
        screen = self.screens.get(key)
        if screen is None:
            logger.error("Tried to show unknown screen: %s", key)
            return
        if hasattr(screen, "on_show"):
            screen.on_show()
        screen.tkraise()
        self._set_active_nav(key)
        logger.info("Navigated to screen: %s", key)

    def _set_active_nav(self, key: str) -> None:
        # CAPTCHA and Results are steps within the Search flow, not
        # separate destinations - keep "Search" highlighted for both.
        nav_key = "home" if key in ("captcha", "results") else key
        self._active_nav_key = nav_key
        for candidate_key, btn in self._nav_buttons.items():
            if candidate_key == nav_key:
                btn.configure(fg_color=("#E1E7F5", "#232C42"), text_color=theme.COLOR_ACCENT)
            else:
                btn.configure(fg_color="transparent", text_color=("#1B1E27", "#E7E9EE"))

    def show_results(self, results: list, needs_enrichment: bool = False) -> None:
        self.last_results = results
        self.results_need_enrichment = needs_enrichment
        self.show_screen("results")

    def show_error(self, title: str, message: str) -> None:
        """Simple modal message dialog, used by every screen for errors and confirmations."""
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.geometry("440x200")
        dialog.grab_set()
        ctk.CTkLabel(
            dialog, text=message, wraplength=390, justify="left", font=theme.font_body(),
        ).pack(padx=24, pady=24, fill="both", expand=True)
        ctk.CTkButton(dialog, text="OK", command=dialog.destroy, width=100).pack(pady=(0, 24))
