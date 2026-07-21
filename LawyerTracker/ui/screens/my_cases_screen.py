"""
my_cases_screen.py

Three tabs, all backed by the local database (no network calls):

  - Dashboard: upcoming hearings, soonest first - the "what do I need
    to prepare for" view, plus quick stat cards.
  - All My Cases: every saved case in a proper table, filterable by
    status (Pending/Disposed), with Delete for anything that isn't the
    advocate's (auto-saved results can include noise from a broad
    advocate-name search).
  - Search History: past searches (query + location), read-only.
"""
from __future__ import annotations

import customtkinter as ctk

from models.case import Case
from models.search_record import SearchRecord
from ui import theme
from ui.widgets.case_detail_view import show_case_detail_dialog
from ui.widgets.case_table import CaseTable
from app_utils.logger import get_logger

logger = get_logger(__name__)

_STATUS_FILTERS = ["All", "Pending", "Disposed", "Unknown"]


class MyCasesScreen(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="w", padx=theme.SPACE_LG, pady=(theme.SPACE_LG, theme.SPACE_SM))
        ctk.CTkLabel(header, text="My Cases", font=theme.font_heading()).pack(anchor="w")

        self.tabview = ctk.CTkTabview(self, corner_radius=theme.CARD_RADIUS)
        self.tabview.grid(
            row=1, column=0, sticky="nsew", padx=theme.SPACE_LG, pady=(0, theme.SPACE_LG)
        )
        self.tabview.add("Dashboard")
        self.tabview.add("All My Cases")
        self.tabview.add("Search History")

        self._build_dashboard_tab(self.tabview.tab("Dashboard"))
        self._build_all_cases_tab(self.tabview.tab("All My Cases"))
        self._build_history_tab(self.tabview.tab("Search History"))

    def on_show(self) -> None:
        self._reload_dashboard()
        self._reload_all_cases()
        self._reload_history()

    # ------------------------------------------------------------------
    # Dashboard: stat cards + upcoming hearings, date-wise
    # ------------------------------------------------------------------

    def _build_dashboard_tab(self, tab) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(2, weight=1)

        self.stats_row = ctk.CTkFrame(tab, fg_color="transparent")
        self.stats_row.grid(row=0, column=0, sticky="ew", pady=(12, 16))
        self.stat_cards: dict[str, dict] = {}
        for key, label in [("total", "Total Cases"), ("pending", "Pending"),
                            ("disposed", "Disposed"), ("upcoming", "Upcoming Hearings"),
                            ("unknown", "Needs Review")]:
            card = ctk.CTkFrame(self.stats_row, corner_radius=theme.CARD_RADIUS, width=150, height=76)
            card.pack(side="left", padx=(0, 12))
            card.grid_propagate(False)
            value_label = ctk.CTkLabel(card, text="0", font=ctk.CTkFont(size=24, weight="bold"))
            value_label.pack(anchor="w", padx=16, pady=(14, 0))
            ctk.CTkLabel(card, text=label, font=theme.font_small(), text_color=theme.COLOR_MUTED).pack(
                anchor="w", padx=16, pady=(0, 12)
            )
            self.stat_cards[key] = value_label

        ctk.CTkLabel(
            tab, text="Upcoming Hearings (soonest first)", font=theme.font_subheading()
        ).grid(row=1, column=0, sticky="w", pady=(4, 8))

        self.upcoming_table = CaseTable(tab, on_view=self._view_case)
        self.upcoming_table.grid(row=2, column=0, sticky="nsew")

    def _reload_dashboard(self) -> None:
        all_cases = self.app.history_service.list_cases_for_dashboard()
        upcoming = self.app.history_service.list_cases_for_dashboard(upcoming_only=True)
        pending = [c for c in all_cases if c.case_status == "PENDING"]
        disposed = [c for c in all_cases if c.case_status == "DISPOSED"]
        unknown = [c for c in all_cases if not c.case_status]

        self.stat_cards["total"].configure(text=str(len(all_cases)))
        self.stat_cards["pending"].configure(text=str(len(pending)))
        self.stat_cards["disposed"].configure(text=str(len(disposed)))
        self.stat_cards["upcoming"].configure(text=str(len(upcoming)))
        self.stat_cards["unknown"].configure(text=str(len(unknown)))

        self.upcoming_table.set_cases(upcoming[:25])

    # ------------------------------------------------------------------
    # All My Cases: full table, filterable, deletable
    # ------------------------------------------------------------------

    def _build_all_cases_tab(self, tab) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        filter_row = ctk.CTkFrame(tab, fg_color="transparent")
        filter_row.grid(row=0, column=0, sticky="w", pady=(12, 8))
        ctk.CTkLabel(filter_row, text="Filter:", font=theme.font_body()).pack(side="left", padx=(0, 8))
        self.status_filter = ctk.CTkSegmentedButton(
            filter_row, values=_STATUS_FILTERS, command=lambda _v: self._reload_all_cases()
        )
        self.status_filter.set("All")
        self.status_filter.pack(side="left")

        self.all_cases_table = CaseTable(tab, on_view=self._view_case, on_delete=self._delete_case)
        self.all_cases_table.grid(row=1, column=0, sticky="nsew")

    def _reload_all_cases(self) -> None:
        status = self.status_filter.get()
        if status == "All":
            cases = self.app.history_service.list_cases_for_dashboard()
        elif status == "Unknown":
            cases = [c for c in self.app.history_service.list_cases_for_dashboard() if not c.case_status]
        else:
            cases = self.app.history_service.list_cases_for_dashboard(status_filter=status.upper())
        self.all_cases_table.set_cases(cases)

    def _delete_case(self, case: Case) -> None:
        if case.id is None:
            return
        self.app.history_service.delete_case(case.id)
        logger.info("Deleted case id=%s from My Cases.", case.id)
        self._reload_dashboard()
        self._reload_all_cases()

    def _view_case(self, case: Case) -> None:
        show_case_detail_dialog(self, self.app, case, on_delete=self._delete_case)

    # ------------------------------------------------------------------
    # Search history
    # ------------------------------------------------------------------

    def _build_history_tab(self, tab) -> None:
        self.history_list = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self.history_list.pack(fill="both", expand=True, pady=(12, 0))

    def _reload_history(self) -> None:
        for w in self.history_list.winfo_children():
            w.destroy()
        records = self.app.history_service.list_search_history()
        if not records:
            ctk.CTkLabel(
                self.history_list, text="No search history yet.", text_color=theme.COLOR_MUTED
            ).pack(pady=24)
            return
        for record in records:
            self._build_history_row(record)

    def _build_history_row(self, record: SearchRecord) -> None:
        row = ctk.CTkFrame(self.history_list)
        row.pack(fill="x", pady=4)
        type_labels = {"cnr": "CNR", "advocate": "Advocate", "case_number": "Case Number"}
        badge_text = type_labels.get(record.search_type.value, record.search_type.value)
        status = f"  \u00b7  {record.case_status.title()}" if record.case_status else ""
        text = f"{badge_text}{status}   \u2014   {record.query_text}"
        ctk.CTkLabel(row, text=text, anchor="w", font=theme.font_body()).pack(
            side="left", padx=14, pady=10, fill="x", expand=True
        )
        ctk.CTkLabel(
            row, text=record.created_at, anchor="e", font=theme.font_small(), text_color=theme.COLOR_MUTED,
        ).pack(side="right", padx=14)
