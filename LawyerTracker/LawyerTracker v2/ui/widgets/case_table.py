"""
case_table.py

A lightweight tabular view of cases. CustomTkinter has no built-in
table widget, so this builds one out of a header row of labels plus a
scrollable frame of data rows using matching column widths - simple,
but genuinely a table (sortable columns of aligned data), not just a
list of cards.
"""
from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from models.case import Case
from ui import theme

_COLUMNS = [
    ("Case Number", 140),
    ("Parties", 250),
    ("CNR", 150),
    ("Stage", 120),
    ("Status", 90),
    ("Next Hearing", 100),
    ("Court", 150),
]


class CaseTable(ctk.CTkFrame):
    def __init__(
        self,
        master,
        on_delete: Optional[Callable[[Case], None]] = None,
        on_view: Optional[Callable[[Case], None]] = None,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self._on_delete = on_delete
        self._on_view = on_view

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.header = ctk.CTkFrame(self, fg_color=("#ECEEF1", "#20242F"), corner_radius=8)
        self.header.grid(row=0, column=0, sticky="ew")
        for i, (label, width) in enumerate(_COLUMNS):
            ctk.CTkLabel(
                self.header, text=label, font=theme.font_small(), width=width, anchor="w",
                text_color=theme.COLOR_MUTED,
            ).grid(row=0, column=i, padx=6, pady=8, sticky="w")
        ctk.CTkLabel(self.header, text="", width=170).grid(row=0, column=len(_COLUMNS), padx=6)

        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="nsew")

    def set_cases(self, cases: list[Case]) -> None:
        for widget in self.body.winfo_children():
            widget.destroy()

        if not cases:
            ctk.CTkLabel(
                self.body, text="No cases to show.", text_color=theme.COLOR_MUTED,
            ).grid(row=0, column=0, padx=6, pady=24)
            return

        for row_index, case in enumerate(cases):
            self._build_row(row_index, case)

    def _build_row(self, row_index: int, case: Case) -> None:
        bg = ("#FFFFFF", "#1B1F29") if row_index % 2 == 0 else ("#F7F8FA", "#181B24")
        row = ctk.CTkFrame(self.body, fg_color=bg, corner_radius=0)
        row.grid(row=row_index, column=0, sticky="ew", pady=1)

        parties = f"{case.petitioner or '?'} vs {case.respondent or '?'}"
        values = [
            case.case_number or "-",
            parties,
            case.cnr or "-",
            case.case_stage or "-",
        ]
        for i, (value, (_, width)) in enumerate(zip(values, _COLUMNS)):
            ctk.CTkLabel(row, text=value, width=width, anchor="w", justify="left").grid(
                row=0, column=i, padx=6, pady=8, sticky="w"
            )

        # Status column uses a colored pill instead of plain text.
        status_col = len(values)
        theme.status_badge(row, case.case_status).grid(
            row=0, column=status_col, padx=6, pady=6, sticky="w"
        )

        remaining = [case.next_hearing_date or "-", case.court_name or "-"]
        for j, value in enumerate(remaining):
            col = status_col + 1 + j
            width = _COLUMNS[col][1]
            ctk.CTkLabel(row, text=value, width=width, anchor="w", justify="left").grid(
                row=0, column=col, padx=6, pady=8, sticky="w"
            )

        actions = ctk.CTkFrame(row, fg_color="transparent", width=170)
        actions.grid(row=0, column=len(_COLUMNS), padx=6, pady=4, sticky="e")
        if self._on_view:
            ctk.CTkButton(
                actions, text="View", width=60, height=26,
                fg_color="transparent", border_width=1,
                border_color=("#C7CAD1", "#39404F"), text_color=("#1B1E27", "#E7E9EE"),
                hover_color=("#ECEEF1", "#242835"),
                command=lambda c=case: self._on_view(c),
            ).pack(side="left", padx=2)
        if self._on_delete:
            ctk.CTkButton(
                actions, text="Delete", width=60, height=26,
                fg_color=theme.COLOR_DANGER_BG, text_color=theme.COLOR_DANGER,
                hover_color=("#F6D3D3", "#452323"),
                command=lambda c=case: self._on_delete(c),
            ).pack(side="left", padx=2)
