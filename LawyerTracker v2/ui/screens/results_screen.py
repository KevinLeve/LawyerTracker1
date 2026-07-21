"""
results_screen.py

Shows search results immediately - before anything has been saved or
enriched with full case detail. Fetching each case's CNR/stage/next
hearing date and saving it to the database happens in the background
right after that, with rows updating in place as each one finishes,
rather than making the advocate wait on a blocking "Saving..." screen
before they see anything at all.
"""
from __future__ import annotations

import threading

import customtkinter as ctk

from models.case import Case
from ui import theme
from ui.widgets.case_detail_view import show_case_detail_dialog
from ui.widgets.case_table import CaseTable
from app_utils.logger import get_logger

logger = get_logger(__name__)


class ResultsScreen(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._enriching = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=theme.SPACE_LG, pady=(theme.SPACE_LG, 4))
        header.grid_columnconfigure(0, weight=1)

        self.title_label = ctk.CTkLabel(header, text="Results", font=theme.font_heading())
        self.title_label.grid(row=0, column=0, sticky="w")

        button_row = ctk.CTkFrame(header, fg_color="transparent")
        button_row.grid(row=0, column=1, sticky="e")
        ctk.CTkButton(
            button_row, text="View My Cases", fg_color="transparent", border_width=1,
            border_color=("#C7CAD1", "#39404F"), text_color=("#1B1E27", "#E7E9EE"),
            hover_color=("#ECEEF1", "#242835"),
            command=lambda: self.app.show_screen("my_cases"),
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            button_row, text="New Search", command=lambda: self.app.show_screen("home"),
        ).pack(side="left")

        status_row = ctk.CTkFrame(self, fg_color="transparent")
        status_row.grid(row=1, column=0, sticky="ew", padx=theme.SPACE_LG, pady=(0, 8))
        status_row.grid_columnconfigure(0, weight=1)

        self.banner_label = ctk.CTkLabel(
            status_row, text="", text_color=theme.COLOR_MUTED, anchor="w", justify="left",
            font=theme.font_body(),
        )
        self.banner_label.grid(row=0, column=0, sticky="w")

        self.progress_bar = ctk.CTkProgressBar(status_row, height=6, width=220)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.progress_bar.grid_remove()

        self.table = CaseTable(self, on_view=self._view_detail, on_delete=self._delete_case)
        self.table.grid(row=2, column=0, sticky="nsew", padx=theme.SPACE_LG, pady=(0, theme.SPACE_LG))

    def on_show(self) -> None:
        results: list[Case] = self.app.last_results
        self.title_label.configure(text=f"Results ({len(results)})")
        self.table.set_cases(results)

        if self.app.results_need_enrichment and not self._enriching:
            self.app.results_need_enrichment = False
            self._start_background_enrichment(results)
        elif not self.app.results_need_enrichment:
            self._show_saved_banner(len(results))

    # ------------------------------------------------------------------
    # Background enrichment: fetch full detail + save, row by row
    # ------------------------------------------------------------------

    def _start_background_enrichment(self, results: list[Case]) -> None:
        self._enriching = True
        total = len(results)
        self.progress_bar.set(0)
        self.progress_bar.grid()
        self.banner_label.configure(
            text=f"Fetching details and saving 0/{total} cases...", text_color=theme.COLOR_MUTED
        )

        def on_case_ready(index: int, case: Case) -> None:
            self.after(0, self._apply_enriched_case, index, case)

        def on_progress(done: int, total_: int) -> None:
            self.after(0, self._update_progress, done, total_)

        def worker():
            self.app.search_service.enrich_and_save_all(
                results, on_progress=on_progress, on_case_ready=on_case_ready
            )
            self.after(0, self._finish_enrichment, total)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_enriched_case(self, index: int, case: Case) -> None:
        # Only apply if we're still looking at the same result set
        # (the advocate could have started a new search in the meantime).
        if index < len(self.app.last_results):
            self.app.last_results[index] = case
            self.table.set_cases(self.app.last_results)

    def _update_progress(self, done: int, total: int) -> None:
        self.progress_bar.set(done / total if total else 0)
        self.banner_label.configure(text=f"Fetching details and saving {done}/{total} cases...")

    def _finish_enrichment(self, total: int) -> None:
        self._enriching = False
        self.progress_bar.grid_remove()
        self._show_saved_banner(total)

    def _show_saved_banner(self, total: int) -> None:
        self.banner_label.configure(
            text=f"\u2713 All {total} case(s) saved to My Cases. Delete any that aren't yours "
                 "below or from the My Cases screen.",
            text_color=theme.COLOR_SUCCESS,
        )

    # ------------------------------------------------------------------
    # Row actions
    # ------------------------------------------------------------------

    def _delete_case(self, case: Case) -> None:
        if case.id is None:
            return
        self.app.history_service.delete_case(case.id)
        self.app.last_results = [c for c in self.app.last_results if c.id != case.id]
        self.table.set_cases(self.app.last_results)
        self.title_label.configure(text=f"Results ({len(self.app.last_results)})")

    def _view_detail(self, case: Case) -> None:
        # Already-enriched cases have their full detail on hand already.
        if case.cnr or not case.extra.get("view_args"):
            show_case_detail_dialog(self, self.app, case, on_delete=self._delete_case)
            return

        def worker():
            try:
                detail = self.app.search_service.fetch_case_detail(case)
            except Exception as exc:
                logger.exception("Failed to fetch case detail.")
                # Capture the message now - see the matching comment in
                # captcha_screen.py's _fetch_captcha_worker for why.
                error_message = str(exc)
                self.after(0, lambda: self.app.show_error("Could not load detail", error_message))
                return
            self.after(0, lambda: show_case_detail_dialog(self, self.app, detail, on_delete=self._delete_case))

        threading.Thread(target=worker, daemon=True).start()
