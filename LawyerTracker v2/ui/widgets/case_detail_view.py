"""
case_detail_view.py

A structured case detail dialog: sections with proper label/value
grids and small tables, mirroring how the eCourts portal itself lays
out a case's detail page (Case Details, Case Status, Petitioner/
Respondent, Acts, FIR Details, Case History) - not a single scrolling
text dump. Shared by the Results and My Cases screens so both use the
exact same dialog rather than two near-duplicate ones.
"""
from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from models.case import Case
from ui import theme


def show_case_detail_dialog(master, app, case: Case, on_delete: Optional[Callable[[Case], None]] = None) -> None:
    dialog = ctk.CTkToplevel(master)
    dialog.title("Case Detail")
    dialog.geometry("620x680")
    dialog.grab_set()

    header = ctk.CTkFrame(dialog, fg_color="transparent")
    header.pack(fill="x", padx=24, pady=(20, 8))
    ctk.CTkLabel(
        header, text=case.display_title(), font=theme.font_subheading(), wraplength=540, justify="left",
    ).pack(anchor="w")
    badge_row = ctk.CTkFrame(header, fg_color="transparent")
    badge_row.pack(anchor="w", pady=(6, 0))
    theme.status_badge(badge_row, case.case_status).pack(side="left")
    if case.court_name:
        ctk.CTkLabel(
            badge_row, text=case.court_name, font=theme.font_small(), text_color=theme.COLOR_MUTED,
        ).pack(side="left", padx=(10, 0))

    scroll = ctk.CTkScrollableFrame(dialog, fg_color="transparent")
    scroll.pack(fill="both", expand=True, padx=24, pady=(4, 4))
    scroll.grid_columnconfigure(0, weight=1)

    row_index = [0]

    def next_row() -> int:
        row_index[0] += 1
        return row_index[0]

    _kv_section(scroll, "Case Details", [
        ("Case Type", case.case_type),
        ("Filing Number", case.filing_number),
        ("Filing Date", case.filing_date),
        ("Registration Number", case.registration_number),
        ("Registration Date", case.registration_date),
        ("CNR Number", case.cnr),
        ("e-Filing Number", case.extra.get("e_filing_number", "")),
        ("e-Filing Date", case.extra.get("e_filing_date", "")),
    ], next_row())

    status_pairs = [("First Hearing Date", case.extra.get("first_hearing_date", ""))]
    if case.case_status == "DISPOSED":
        status_pairs += [
            ("Decision Date", case.extra.get("decision_date", "")),
            ("Case Status", case.extra.get("case_status_text", "") or "Disposed"),
            ("Nature of Disposal", case.extra.get("nature_of_disposal", "")),
        ]
    else:
        status_pairs += [
            ("Next Hearing Date", case.next_hearing_date),
            ("Case Stage", case.case_stage),
            ("Sub Stage", case.extra.get("sub_stage", "")),
        ]
    status_pairs.append(("Court Number and Judge", case.judge))
    _kv_section(scroll, "Case Status", status_pairs, next_row())

    _kv_section(scroll, "Petitioner and Advocate", [
        ("Petitioner", case.petitioner),
        ("Advocate", case.petitioner_advocate),
    ], next_row())

    _kv_section(scroll, "Respondent and Advocate", [
        ("Respondent", case.respondent),
        ("Advocate", case.respondent_advocate),
    ], next_row())

    acts = case.extra.get("acts") or []
    if acts:
        _table_section(
            scroll, "Acts",
            ["Under Act(s)", "Under Section(s)"],
            [[a.get("act", ""), a.get("section", "")] for a in acts],
            next_row(),
        )

    fir_details = case.extra.get("fir_details") or {}
    if fir_details:
        _table_section(
            scroll, "FIR Details",
            ["Field", "Details"],
            [[k, v] for k, v in fir_details.items()],
            next_row(),
        )

    case_history = case.extra.get("case_history") or []
    if case_history:
        _table_section(
            scroll, "Case History",
            ["Judge", "Business Date", "Hearing Date", "Purpose"],
            [[h.get("judge", ""), h.get("business_date", ""), h.get("hearing_date", ""), h.get("purpose", "")]
             for h in case_history],
            next_row(),
        )

    if on_delete:
        ctk.CTkButton(
            dialog, text="Delete this case", fg_color=theme.COLOR_DANGER_BG, text_color=theme.COLOR_DANGER,
            hover_color=("#F6D3D3", "#452323"),
            command=lambda: (on_delete(case), dialog.destroy()),
        ).pack(pady=(4, 20))


def _section_card(parent, title: str, row: int) -> ctk.CTkFrame:
    card = ctk.CTkFrame(parent, corner_radius=theme.CARD_RADIUS)
    card.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    card.grid_columnconfigure((0, 1), weight=1)
    ctk.CTkLabel(card, text=title, font=theme.font_subheading()).grid(
        row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 6)
    )
    return card


def _kv_section(parent, title: str, pairs: list[tuple[str, str]], row: int) -> None:
    pairs = [(label, value) for label, value in pairs if value]
    if not pairs:
        return
    card = _section_card(parent, title, row)
    for i, (label, value) in enumerate(pairs, start=1):
        ctk.CTkLabel(
            card, text=label, font=theme.font_small(), text_color=theme.COLOR_MUTED, anchor="w",
        ).grid(row=i, column=0, sticky="nw", padx=(16, 8), pady=4)
        ctk.CTkLabel(
            card, text=value, font=theme.font_body(), anchor="w", justify="left", wraplength=380,
        ).grid(row=i, column=1, sticky="nw", padx=(0, 16), pady=4)
    ctk.CTkLabel(card, text="").grid(row=len(pairs) + 1, column=0, pady=(0, 4))  # bottom spacer


def _table_section(parent, title: str, headers: list[str], rows: list[list[str]], row: int) -> None:
    rows = [r for r in rows if any(cell for cell in r)]
    if not rows:
        return
    card = _section_card(parent, title, row)
    card.grid_columnconfigure(tuple(range(len(headers))), weight=1)

    header_row = ctk.CTkFrame(card, fg_color=("#ECEEF1", "#20242F"))
    header_row.grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 2))
    for i, h in enumerate(headers):
        header_row.grid_columnconfigure(i, weight=1)
        ctk.CTkLabel(
            header_row, text=h, font=theme.font_small(), text_color=theme.COLOR_MUTED, anchor="w",
        ).grid(row=0, column=i, padx=8, pady=6, sticky="w")

    for r_idx, data_row in enumerate(rows):
        bg = ("#FFFFFF", "#1B1F29") if r_idx % 2 == 0 else ("#F7F8FA", "#181B24")
        data_frame = ctk.CTkFrame(card, fg_color=bg)
        data_frame.grid(row=2 + r_idx, column=0, columnspan=2, sticky="ew", padx=16, pady=1)
        for i in range(len(headers)):
            data_frame.grid_columnconfigure(i, weight=1)
            value = data_row[i] if i < len(data_row) else ""
            ctk.CTkLabel(
                data_frame, text=value or "-", font=theme.font_body(), anchor="w", justify="left", wraplength=180,
            ).grid(row=0, column=i, padx=8, pady=6, sticky="w")

    ctk.CTkLabel(card, text="").grid(row=2 + len(rows), column=0, pady=(0, 4))  # bottom spacer
