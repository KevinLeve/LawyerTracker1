"""
search_record.py

`SearchRecord` represents one search performed by the user (what they
searched for, and where). Stored in the `searches` table and used to
populate the "search history" screen and to link found cases back to
the query that found them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from models.enums import SearchType


@dataclass
class SearchRecord:
    id: Optional[int] = None
    search_type: SearchType = SearchType.CNR
    query_text: str = ""
    state_code: str = ""
    dist_code: str = ""
    court_complex_code: str = ""
    case_status: str = ""
    created_at: str = ""

    def to_row(self) -> dict[str, Any]:
        return {
            "search_type": self.search_type.value,
            "query_text": self.query_text,
            "state_code": self.state_code,
            "dist_code": self.dist_code,
            "court_complex_code": self.court_complex_code,
            "case_status": self.case_status,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "SearchRecord":
        return cls(
            id=row["id"],
            search_type=SearchType(row["search_type"]),
            query_text=row["query_text"],
            state_code=row["state_code"] or "",
            dist_code=row["dist_code"] or "",
            court_complex_code=row["court_complex_code"] or "",
            case_status=row["case_status"] or "",
            created_at=row["created_at"],
        )
