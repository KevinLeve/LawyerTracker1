"""
location_picker.py

Reusable State -> District -> Court Complex cascade, used by both the
Advocate-search and Case-Number-search tabs on the Home screen (CNR
search doesn't need a location, since a CNR number is unique nationwide).

Design decision: each dropdown change triggers a background thread to
call the (network-bound) location service, so picking a state doesn't
freeze the UI while districts load. Results are marshalled back onto
the Tk main thread via `self.after(0, ...)`, since Tkinter widgets are
not thread-safe to touch directly from a worker thread.
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

import customtkinter as ctk

from services.location_service import LocationService
from app_utils.logger import get_logger

logger = get_logger(__name__)

_PLACEHOLDER = "Select..."


class LocationPicker(ctk.CTkFrame):
    def __init__(
        self,
        master,
        location_service: LocationService,
        on_error: Optional[Callable[[str, str], None]] = None,
        initial: Optional[dict[str, str]] = None,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self._service = location_service
        self._on_error = on_error or (lambda title, msg: None)
        # {"state_name":..., "dist_name":..., "court_complex_name":...} - best-effort
        # prefill from a saved profile; falls back to blank if the name
        # no longer matches an option (e.g. portal renamed something).
        self._initial = initial or {}

        self._states: list[dict[str, str]] = []
        self._districts: list[dict[str, str]] = []
        self._complexes: list[dict[str, str]] = []

        self.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkLabel(self, text="State").grid(row=0, column=0, sticky="w", padx=4)
        ctk.CTkLabel(self, text="District").grid(row=0, column=1, sticky="w", padx=4)
        ctk.CTkLabel(self, text="Court Complex").grid(row=0, column=2, sticky="w", padx=4)

        self.state_menu = ctk.CTkOptionMenu(
            self, values=[_PLACEHOLDER], command=self._on_state_selected
        )
        self.district_menu = ctk.CTkOptionMenu(
            self, values=[_PLACEHOLDER], command=self._on_district_selected, state="disabled"
        )
        self.complex_menu = ctk.CTkOptionMenu(
            self, values=[_PLACEHOLDER], state="disabled"
        )
        self.state_menu.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 8))
        self.district_menu.grid(row=1, column=1, sticky="ew", padx=4, pady=(0, 8))
        self.complex_menu.grid(row=1, column=2, sticky="ew", padx=4, pady=(0, 8))

        self._load_states()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_selection(self) -> Optional[dict[str, str]]:
        full = self.get_selection_full()
        if not full:
            return None
        return {
            "state_code": full["state_code"],
            "dist_code": full["dist_code"],
            "court_complex_code": full["court_complex_code"],
        }

    def get_selection_full(self) -> Optional[dict[str, str]]:
        """Returns codes AND display names for all three levels, or None if incomplete."""
        state = self._find(self._states, self.state_menu.get())
        district = self._find(self._districts, self.district_menu.get())
        complex_ = self._find(self._complexes, self.complex_menu.get())
        if not (state and district and complex_):
            return None
        return {
            "state_code": state["code"], "state_name": state["name"],
            "dist_code": district["code"], "dist_name": district["name"],
            "court_complex_code": complex_["code"], "court_complex_name": complex_["name"],
        }

    def apply_initial(self, initial: dict[str, str]) -> None:
        """
        Re-apply a prefill after construction - needed because a
        brand-new user's Profile doesn't exist yet when the Home screen
        (and its LocationPickers) are first built, only right after
        onboarding finishes. Safe to call any time states are loaded.
        """
        self._initial = initial
        state_name = initial.get("state_name")
        if state_name and any(s["name"] == state_name for s in self._states):
            self.state_menu.set(state_name)
            self._on_state_selected(state_name)

    # ------------------------------------------------------------------
    # State loading (static, but keep async for consistency / future-proofing)
    # ------------------------------------------------------------------

    def _load_states(self) -> None:
        try:
            self._states = self._service.get_states()
            names = [s["name"] for s in self._states]
            self.state_menu.configure(values=names or [_PLACEHOLDER])
            initial_state = self._initial.get("state_name")
            if initial_state and initial_state in names:
                self.state_menu.set(initial_state)
                self._on_state_selected(initial_state)
            elif names:
                self.state_menu.set(_PLACEHOLDER)
        except Exception:
            logger.exception("Failed to load state list.")
            self._on_error("Location error", "Could not load the list of states.")

    def _on_state_selected(self, _value: str) -> None:
        self.district_menu.configure(state="disabled", values=[_PLACEHOLDER])
        self.district_menu.set(_PLACEHOLDER)
        self.complex_menu.configure(state="disabled", values=[_PLACEHOLDER])
        self.complex_menu.set(_PLACEHOLDER)

        state = self._find(self._states, self.state_menu.get())
        if not state:
            return
        self.district_menu.configure(values=["Loading..."])
        self.district_menu.set("Loading...")

        threading.Thread(
            target=self._fetch_districts_worker, args=(state["code"],), daemon=True
        ).start()

    def _fetch_districts_worker(self, state_code: str) -> None:
        try:
            districts = self._service.get_districts(state_code)
        except Exception:
            logger.exception("Failed to load districts.")
            self.after(0, lambda: self._on_error(
                "Location error", "Could not load districts for the selected state."))
            self.after(0, lambda: self.district_menu.configure(values=[_PLACEHOLDER]))
            self.after(0, lambda: self.district_menu.set(_PLACEHOLDER))
            return
        self.after(0, self._apply_districts, districts)

    def _apply_districts(self, districts: list[dict[str, str]]) -> None:
        self._districts = districts
        names = [d["name"] for d in districts] or [_PLACEHOLDER]
        self.district_menu.configure(values=names, state="normal")
        initial_district = self._initial.get("dist_name")
        if initial_district and initial_district in names:
            self.district_menu.set(initial_district)
            self._on_district_selected(initial_district)
        else:
            self.district_menu.set(_PLACEHOLDER)

    def _on_district_selected(self, _value: str) -> None:
        self.complex_menu.configure(state="disabled", values=[_PLACEHOLDER])
        self.complex_menu.set(_PLACEHOLDER)

        state = self._find(self._states, self.state_menu.get())
        district = self._find(self._districts, self.district_menu.get())
        if not (state and district):
            return
        self.complex_menu.configure(values=["Loading..."])
        self.complex_menu.set("Loading...")

        threading.Thread(
            target=self._fetch_complexes_worker,
            args=(state["code"], district["code"]),
            daemon=True,
        ).start()

    def _fetch_complexes_worker(self, state_code: str, dist_code: str) -> None:
        try:
            complexes = self._service.get_court_complexes(state_code, dist_code)
        except Exception:
            logger.exception("Failed to load court complexes.")
            self.after(0, lambda: self._on_error(
                "Location error", "Could not load court complexes for the selected district."))
            self.after(0, lambda: self.complex_menu.configure(values=[_PLACEHOLDER]))
            self.after(0, lambda: self.complex_menu.set(_PLACEHOLDER))
            return
        self.after(0, self._apply_complexes, complexes)

    def _apply_complexes(self, complexes: list[dict[str, str]]) -> None:
        self._complexes = complexes
        names = [c["name"] for c in complexes] or [_PLACEHOLDER]
        self.complex_menu.configure(values=names, state="normal")
        initial_complex = self._initial.get("court_complex_name")
        if initial_complex and initial_complex in names:
            self.complex_menu.set(initial_complex)
        else:
            self.complex_menu.set(_PLACEHOLDER)

    @staticmethod
    def _find(options: list[dict[str, str]], name: str) -> Optional[dict[str, str]]:
        return next((o for o in options if o["name"] == name), None)
