"""
history_service.py

CRUD operations for reopening saved cases, browsing search history, and
managing favourites - all local, no network calls. This is what powers
"Allow reopening saved cases without performing another search."
"""
from __future__ import annotations

from database import get_connection
from models.case import Case
from models.search_record import SearchRecord
from app_utils.logger import get_logger

logger = get_logger(__name__)


class HistoryService:
    # ------------------------------------------------------------------
    # Saved cases
    # ------------------------------------------------------------------

    def list_saved_cases(self, limit: int = 200) -> list[Case]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM cases ORDER BY saved_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [Case.from_row(row) for row in rows]

    def list_cases_for_dashboard(
        self, status_filter: str = "", upcoming_only: bool = False
    ) -> list[Case]:
        """
        Powers the My Cases table: sorted by next hearing date (soonest
        first), cases with no parseable hearing date pushed to the end,
        optionally filtered to a single status or to only upcoming
        hearings (today onward).
        """
        from datetime import date

        query = "SELECT * FROM cases WHERE 1=1"
        params: list = []
        if status_filter:
            query += " AND case_status = ?"
            params.append(status_filter)
        if upcoming_only:
            query += " AND next_hearing_iso >= ?"
            params.append(date.today().isoformat())
        query += " ORDER BY (next_hearing_iso = '' OR next_hearing_iso IS NULL), next_hearing_iso ASC"

        with get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [Case.from_row(row) for row in rows]

    def get_case(self, case_id: int) -> Case | None:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
            return Case.from_row(row) if row else None

    def delete_case(self, case_id: int) -> None:
        with get_connection() as conn:
            conn.execute("DELETE FROM cases WHERE id = ?", (case_id,))
            logger.info("Deleted saved case id=%s", case_id)

    # ------------------------------------------------------------------
    # Search history
    # ------------------------------------------------------------------

    def list_search_history(self, limit: int = 100) -> list[SearchRecord]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM searches ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [SearchRecord.from_row(row) for row in rows]

    def clear_search_history(self) -> None:
        with get_connection() as conn:
            conn.execute("DELETE FROM searches")
            logger.info("Search history cleared.")

    # ------------------------------------------------------------------
    # Favourites
    # ------------------------------------------------------------------

    def add_favourite(self, case_id: int) -> None:
        with get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO favourites (case_id) VALUES (?)", (case_id,)
            )
            logger.info("Marked case id=%s as favourite.", case_id)

    def remove_favourite(self, case_id: int) -> None:
        with get_connection() as conn:
            conn.execute("DELETE FROM favourites WHERE case_id = ?", (case_id,))

    def list_favourites(self) -> list[Case]:
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT cases.* FROM cases
                   JOIN favourites ON favourites.case_id = cases.id
                   ORDER BY favourites.added_at DESC"""
            ).fetchall()
            return [Case.from_row(row) for row in rows]

    def is_favourite(self, case_id: int) -> bool:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM favourites WHERE case_id = ?", (case_id,)
            ).fetchone()
            return row is not None
