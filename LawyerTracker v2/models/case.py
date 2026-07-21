"""
case.py

`Case` is the single shape that flows through the whole app: the parser
builds it from HTML, the database stores it, and the UI renders it.
Without this, every layer would invent its own dict keys and typos
between layers ("case_no" vs "caseNo") would only surface at runtime.

`to_row()` / `from_row()` convert to/from the flat dict shape the
database layer wants (matching the `cases` table columns), keeping SQL
details out of the dataclass itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional
import json


@dataclass
class Case:
    id: Optional[int] = None
    search_id: Optional[int] = None

    cnr: str = ""
    case_number: str = ""
    case_type: str = ""
    filing_number: str = ""
    filing_date: str = ""
    registration_number: str = ""
    registration_date: str = ""
    petitioner: str = ""
    respondent: str = ""
    petitioner_advocate: str = ""
    respondent_advocate: str = ""
    case_stage: str = ""
    case_status: str = ""          # "PENDING" | "DISPOSED" | "" (unknown)
    next_hearing_date: str = ""
    next_hearing_iso: str = ""     # parsed "YYYY-MM-DD" for sorting; "" if unparseable
    court_name: str = ""
    judge: str = ""

    # Anything the parser extracted that doesn't have a dedicated column
    # yet still gets kept, so we don't silently drop data as the site's
    # HTML structure evolves.
    extra: dict[str, Any] = field(default_factory=dict)

    def display_title(self) -> str:
        """Short label used in list views (results table, saved cases list)."""
        if self.case_number:
            return f"{self.case_number} — {self.petitioner or '?'} vs {self.respondent or '?'}"
        return self.cnr or "Untitled case"

    def to_row(self) -> dict[str, Any]:
        """Flatten to the column shape the `cases` table expects."""
        from app_utils.dates import parse_flexible_date

        return {
            "search_id": self.search_id,
            "cnr": self.cnr,
            "case_number": self.case_number,
            "case_type": self.case_type,
            "filing_number": self.filing_number,
            "filing_date": self.filing_date,
            "registration_number": self.registration_number,
            "registration_date": self.registration_date,
            "petitioner": self.petitioner,
            "respondent": self.respondent,
            "petitioner_advocate": self.petitioner_advocate,
            "respondent_advocate": self.respondent_advocate,
            "case_stage": self.case_stage,
            "case_status": self.case_status,
            "next_hearing_date": self.next_hearing_date,
            "next_hearing_iso": self.next_hearing_iso or parse_flexible_date(self.next_hearing_date) or "",
            "court_name": self.court_name,
            "judge": self.judge,
            "raw_json": json.dumps(self.extra, ensure_ascii=False),
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Case":
        """Rebuild a Case from a sqlite3.Row (or plain dict) fetched from `cases`."""
        raw = row["raw_json"] if "raw_json" in row.keys() else None
        extra = json.loads(raw) if raw else {}
        return cls(
            id=row["id"] if "id" in row.keys() else None,
            search_id=row["search_id"] if "search_id" in row.keys() else None,
            cnr=row["cnr"] or "",
            case_number=row["case_number"] or "",
            case_type=row["case_type"] or "",
            filing_number=row["filing_number"] or "",
            filing_date=row["filing_date"] or "",
            registration_number=row["registration_number"] or "",
            registration_date=row["registration_date"] or "",
            petitioner=row["petitioner"] or "",
            respondent=row["respondent"] or "",
            petitioner_advocate=row["petitioner_advocate"] or "",
            respondent_advocate=row["respondent_advocate"] or "",
            case_stage=row["case_stage"] or "",
            case_status=row["case_status"] or "",
            next_hearing_date=row["next_hearing_date"] or "",
            next_hearing_iso=row["next_hearing_iso"] or "",
            court_name=row["court_name"] or "",
            judge=row["judge"] or "",
            extra=extra,
        )
