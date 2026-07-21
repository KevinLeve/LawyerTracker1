"""
home_screen.py

Search entry point: three tabs (CNR / Advocate Name / Case Number).
Filling a tab and clicking its Search button stores the chosen params
in `app.pending_search` and navigates to the CAPTCHA screen - nothing
is sent to eCourts yet, since a CAPTCHA has to be solved first.

Advocate name and location default to the advocate's profile (set once
during onboarding) so they don't have to re-pick their own court every
time - both stay editable in case they're searching a different court.
"""
from __future__ import annotations

import customtkinter as ctk

from models.enums import SearchType
from ui import theme
from ui.widgets.location_picker import LocationPicker
from app_utils.logger import get_logger

logger = get_logger(__name__)

_STATUS_OPTIONS = ["Pending", "Disposed", "Both"]


class HomeScreen(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=theme.SPACE_LG, pady=(theme.SPACE_LG, theme.SPACE_SM))
        header.grid_columnconfigure(0, weight=1)

        title_col = ctk.CTkFrame(header, fg_color="transparent")
        title_col.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(title_col, text="Search Case Status", font=theme.font_heading()).pack(anchor="w")
        ctk.CTkLabel(
            title_col, text="Look up a case by CNR, advocate name, or case number.",
            font=theme.font_body(), text_color=theme.COLOR_MUTED,
        ).pack(anchor="w", pady=(2, 0))

        method_col = ctk.CTkFrame(header, fg_color="transparent")
        method_col.grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(method_col, text="CAPTCHA Method", font=theme.font_small(), text_color=theme.COLOR_MUTED).pack(
            anchor="e"
        )
        self.captcha_method = ctk.CTkOptionMenu(
            method_col, values=["Manual", "OCR-assisted (KevinOCR)"], width=200,
        )
        self.captcha_method.set("Manual")
        self.captcha_method.pack(anchor="e", pady=(2, 0))

        self.tabview = ctk.CTkTabview(self, corner_radius=theme.CARD_RADIUS)
        self.tabview.grid(
            row=1, column=0, sticky="nsew", padx=theme.SPACE_LG, pady=(0, theme.SPACE_LG)
        )
        self.tabview.add("CNR Number")
        self.tabview.add("Advocate Name")
        self.tabview.add("Case Number")

        self._build_cnr_tab(self.tabview.tab("CNR Number"))
        self._build_advocate_tab(self.tabview.tab("Advocate Name"))
        self._build_case_number_tab(self.tabview.tab("Case Number"))

    def _profile_location_defaults(self) -> dict[str, str]:
        p = self.app.profile
        return {
            "state_name": p.default_state_name,
            "dist_name": p.default_dist_name,
            "court_complex_name": p.default_court_complex_name,
        }

    def refresh_profile_defaults(self) -> None:
        """
        Called right after onboarding completes, since this screen was
        already built (with an empty Profile) before that happened.
        Only fills fields that are still blank, so it won't clobber
        anything the user has already typed.
        """
        if not self.advocate_entry.get().strip() and self.app.profile.advocate_name:
            self.advocate_entry.insert(0, self.app.profile.advocate_name)
        defaults = self._profile_location_defaults()
        self.advocate_location.apply_initial(defaults)
        self.case_number_location.apply_initial(defaults)

    def _selected_captcha_mode(self) -> str:
        from models.enums import CaptchaMode
        return (CaptchaMode.OCR_ASSISTED if "OCR" in self.captcha_method.get()
                else CaptchaMode.MANUAL).value

    @staticmethod
    def _hint(tab, text: str, row: int) -> None:
        ctk.CTkLabel(
            tab, text=text, font=theme.font_small(), text_color=theme.COLOR_MUTED,
            anchor="w", justify="left",
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 4))

    # ------------------------------------------------------------------
    # CNR tab
    # ------------------------------------------------------------------

    def _build_cnr_tab(self, tab) -> None:
        tab.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(tab, text="CNR Number", font=theme.font_subheading()).grid(
            row=0, column=0, sticky="w", padx=8, pady=(16, 0)
        )
        self.cnr_entry = ctk.CTkEntry(tab, placeholder_text="e.g. TNCH010012342024", height=36)
        self.cnr_entry.grid(row=1, column=0, sticky="ew", padx=8, pady=(6, 4))
        self._hint(tab, "The 16-character case number ID printed on eCourts case pages.", 2)

        ctk.CTkButton(
            tab, text="Search", command=self._submit_cnr, width=140, height=36,
        ).grid(row=3, column=0, sticky="w", padx=8, pady=16)

    def _submit_cnr(self) -> None:
        cnr = self.cnr_entry.get().strip()
        if not cnr:
            self.app.show_error("Missing CNR", "Please enter a CNR number.")
            return
        self.app.pending_search = {
            "type": SearchType.CNR,
            "params": {"cnr_number": cnr},
            "captcha_mode": self._selected_captcha_mode(),
        }
        self.app.show_screen("captcha")

    # ------------------------------------------------------------------
    # Advocate tab
    # ------------------------------------------------------------------

    def _build_advocate_tab(self, tab) -> None:
        tab.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(tab, text="Advocate Name", font=theme.font_subheading()).grid(
            row=0, column=0, sticky="w", padx=8, pady=(16, 0)
        )
        self.advocate_entry = ctk.CTkEntry(tab, placeholder_text="e.g. R. Kumar", height=36)
        self.advocate_entry.grid(row=1, column=0, sticky="ew", padx=8, pady=(6, 12))
        if self.app.profile.advocate_name:
            self.advocate_entry.insert(0, self.app.profile.advocate_name)

        ctk.CTkLabel(tab, text="Court", font=theme.font_subheading()).grid(
            row=2, column=0, sticky="w", padx=8
        )
        self.advocate_location = LocationPicker(
            tab, self.app.location_service, on_error=self.app.show_error,
            initial=self._profile_location_defaults(),
        )
        self.advocate_location.grid(row=3, column=0, sticky="ew", padx=8, pady=(6, 12))

        ctk.CTkLabel(tab, text="Case Status", font=theme.font_subheading()).grid(
            row=4, column=0, sticky="w", padx=8
        )
        self.advocate_status = ctk.CTkSegmentedButton(tab, values=_STATUS_OPTIONS)
        self.advocate_status.set("Pending")
        self.advocate_status.grid(row=5, column=0, sticky="w", padx=8, pady=(6, 4))
        self._hint(
            tab, "\"Both\" tags each result Pending/Disposed automatically from its case "
                 "detail page. This is inferred (not stated outright by the portal), so "
                 "double-check anything that matters for a filing deadline.", 6,
        )

        ctk.CTkButton(
            tab, text="Search", command=self._submit_advocate, width=140, height=36,
        ).grid(row=7, column=0, sticky="w", padx=8, pady=16)

    def _submit_advocate(self) -> None:
        name = self.advocate_entry.get().strip()
        if not name:
            self.app.show_error("Missing name", "Please enter an advocate name.")
            return
        location = self.advocate_location.get_selection()
        if not location:
            self.app.show_error(
                "Incomplete location", "Please select state, district, and court complex."
            )
            return
        self.app.pending_search = {
            "type": SearchType.ADVOCATE,
            "params": {
                "advocate_name": name,
                "case_status": self.advocate_status.get(),
                **location,
            },
            "captcha_mode": self._selected_captcha_mode(),
        }
        self.app.show_screen("captcha")

    # ------------------------------------------------------------------
    # Case Number tab
    # ------------------------------------------------------------------

    def _build_case_number_tab(self, tab) -> None:
        tab.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(tab, text="Case Type", font=theme.font_subheading()).grid(
            row=0, column=0, sticky="w", padx=8, pady=(16, 0)
        )
        self.case_type_entry = ctk.CTkEntry(tab, placeholder_text="e.g. C.C.", height=36)
        self.case_type_entry.grid(row=1, column=0, sticky="ew", padx=8, pady=(6, 12))

        ctk.CTkLabel(tab, text="Case Year", font=theme.font_subheading()).grid(
            row=0, column=1, sticky="w", padx=8, pady=(16, 0)
        )
        self.case_year_entry = ctk.CTkEntry(tab, placeholder_text="e.g. 2024", height=36)
        self.case_year_entry.grid(row=1, column=1, sticky="ew", padx=8, pady=(6, 12))

        ctk.CTkLabel(tab, text="Case Number", font=theme.font_subheading()).grid(
            row=2, column=0, sticky="w", padx=8
        )
        self.case_number_entry = ctk.CTkEntry(tab, placeholder_text="e.g. 1234", height=36)
        self.case_number_entry.grid(row=3, column=0, columnspan=2, sticky="ew", padx=8, pady=(6, 12))

        ctk.CTkLabel(tab, text="Court", font=theme.font_subheading()).grid(
            row=4, column=0, sticky="w", padx=8
        )
        self.case_number_location = LocationPicker(
            tab, self.app.location_service, on_error=self.app.show_error,
            initial=self._profile_location_defaults(),
        )
        self.case_number_location.grid(row=5, column=0, columnspan=2, sticky="ew", padx=8, pady=(6, 12))

        ctk.CTkLabel(tab, text="Case Status", font=theme.font_subheading()).grid(
            row=6, column=0, sticky="w", padx=8
        )
        self.case_number_status = ctk.CTkSegmentedButton(tab, values=_STATUS_OPTIONS)
        self.case_number_status.set("Pending")
        self.case_number_status.grid(row=7, column=0, sticky="w", padx=8, pady=(6, 12))

        ctk.CTkButton(
            tab, text="Search", command=self._submit_case_number, width=140, height=36,
        ).grid(row=8, column=0, sticky="w", padx=8, pady=16)

    def _submit_case_number(self) -> None:
        case_type = self.case_type_entry.get().strip()
        case_year = self.case_year_entry.get().strip()
        case_number = self.case_number_entry.get().strip()
        if not (case_type and case_year and case_number):
            self.app.show_error(
                "Missing fields", "Please fill in case type, number, and year."
            )
            return
        location = self.case_number_location.get_selection()
        if not location:
            self.app.show_error(
                "Incomplete location", "Please select state, district, and court complex."
            )
            return
        self.app.pending_search = {
            "type": SearchType.CASE_NUMBER,
            "params": {
                "case_type": case_type,
                "case_number": case_number,
                "case_year": case_year,
                "case_status": self.case_number_status.get(),
                **location,
            },
            "captcha_mode": self._selected_captcha_mode(),
        }
        self.app.show_screen("captcha")
