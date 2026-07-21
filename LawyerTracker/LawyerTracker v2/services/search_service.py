"""
search_service.py

Orchestrates search + auto-save. Two things changed based on real usage
feedback:

1. Results are saved automatically - the advocate reviews and deletes
   anything that isn't theirs from the "My Cases" screen afterward,
   rather than clicking Save on each row one at a time.
2. Advocate/case-number search only returns summary fields (case
   number, parties, advocate) - CNR, stage, and next hearing date are
   only available from the case-detail page. `enrich_and_save_all()`
   fetches the detail for every result and merges it in before saving,
   so "My Cases" always has the full picture rather than dashes.

Saving is an upsert keyed on CNR (via the partial unique index in the
schema) so re-running the same search doesn't create duplicate rows -
it just refreshes the stage/hearing-date on the existing one.
"""
from __future__ import annotations

from typing import Callable, Optional

from api.ecourts_client import EcourtsClient
from api.parser import parse_advocate_search_results, parse_case_history
from database import get_connection
from models.case import Case
from models.enums import SearchType
from models.search_record import SearchRecord
from app_utils.exceptions import DatabaseError
from app_utils.logger import get_logger

logger = get_logger(__name__)

ProgressCallback = Optional[Callable[[int, int], None]]


class SearchService:
    def __init__(self, client: EcourtsClient) -> None:
        self._client = client

    # ------------------------------------------------------------------
    # Search execution - returns SUMMARY cases (not yet enriched/saved)
    # ------------------------------------------------------------------

    def search_advocate(
        self,
        advocate_name: str,
        captcha_text: str,
        state_code: str,
        dist_code: str,
        court_complex_code: str,
        case_status: str = "Pending",
    ) -> list[Case]:
        response = self._client.search_by_advocate_name(
            advocate_name, captcha_text, state_code, dist_code, court_complex_code,
            case_status=case_status,
        )
        cases = parse_advocate_search_results(response)

        search_id = self._save_search_record(
            SearchRecord(
                search_type=SearchType.ADVOCATE,
                query_text=advocate_name,
                state_code=state_code,
                dist_code=dist_code,
                court_complex_code=court_complex_code,
                case_status=case_status.upper() if case_status != "Both" else "",
            )
        )
        for case in cases:
            case.search_id = search_id
            # "Both" mixes pending/disposed rows with no reliable way to
            # tell which is which from the table alone, so we leave it
            # unknown rather than mislabeling. Run separate Pending /
            # Disposed searches if you need the status tagged per case.
            case.case_status = case_status.upper() if case_status != "Both" else ""
        return cases

    def search_cnr(self, cnr_number: str, captcha_text: str) -> Case:
        response = self._client.search_by_cnr(cnr_number, captcha_text)
        case = parse_case_history(response)

        search_id = self._save_search_record(
            SearchRecord(search_type=SearchType.CNR, query_text=cnr_number)
        )
        case.search_id = search_id
        return case

    def search_case_number(
        self,
        case_type: str,
        case_number: str,
        case_year: str,
        captcha_text: str,
        state_code: str,
        dist_code: str,
        court_complex_code: str,
        case_status: str = "Pending",
    ) -> list[Case]:
        response = self._client.search_by_case_number(
            case_type, case_number, case_year, captcha_text,
            state_code, dist_code, court_complex_code,
        )
        cases = parse_advocate_search_results(response)  # same table shape

        search_id = self._save_search_record(
            SearchRecord(
                search_type=SearchType.CASE_NUMBER,
                query_text=f"{case_type} {case_number}/{case_year}",
                state_code=state_code,
                dist_code=dist_code,
                court_complex_code=court_complex_code,
                case_status=case_status.upper() if case_status != "Both" else "",
            )
        )
        for case in cases:
            case.search_id = search_id
            case.case_status = case_status.upper() if case_status != "Both" else ""
        return cases

    def fetch_case_detail(self, case: Case) -> Case:
        """Given a summary Case (from a search results row), fetch full details."""
        view_args = case.extra.get("view_args")
        response = self._client.fetch_case_history(view_args)
        detail = parse_case_history(response)
        return self._merge_detail_into_summary(case, detail)

    @staticmethod
    def _merge_detail_into_summary(summary: Case, detail: Case) -> Case:
        """
        The detail page doesn't repeat everything the search row had
        (and vice versa) - merge, preferring detail fields when present
        and falling back to the summary's version otherwise.
        """
        detail.search_id = summary.search_id
        # An explicit Pending/Disposed search tells us the status
        # directly - trust that over inference. Only a "Both" search
        # (where summary.case_status is "") falls back to whatever the
        # detail page's own signals suggest (see parser.parse_case_history).
        if summary.case_status:
            detail.case_status = summary.case_status
        detail.case_number = detail.case_number or summary.case_number
        detail.petitioner = detail.petitioner or summary.petitioner
        detail.respondent = detail.respondent or summary.respondent
        detail.petitioner_advocate = detail.petitioner_advocate or summary.petitioner_advocate
        detail.extra = {**summary.extra, **detail.extra}
        return detail

    # ------------------------------------------------------------------
    # Auto-save with enrichment (used right after a search completes)
    # ------------------------------------------------------------------

    def enrich_and_save_all(
        self,
        cases: list[Case],
        on_progress: ProgressCallback = None,
        on_case_ready: Optional[Callable[[int, Case], None]] = None,
    ) -> list[Case]:
        """
        For each summary case: fetch its full detail (CNR, stage, next
        hearing date) if it has a fetchable link, then save/upsert it.
        Cases without a `view_args` link (shouldn't normally happen) are
        saved as-is.

        `on_progress(done, total)` fires after each case for a simple
        progress bar. `on_case_ready(index, case)` fires with the fully
        enriched+saved case at its original list position, so the UI
        can update that specific row in place instead of waiting for
        the whole batch - this can be slow for a large result set since
        it's one HTTP request per case, and showing results immediately
        with rows filling in as they're ready beats a blank screen.
        """
        total = len(cases)
        saved: list[Case] = []
        for i, case in enumerate(cases):
            try:
                if case.extra.get("view_args"):
                    case = self.fetch_case_detail(case)
            except Exception:
                logger.exception("Detail fetch failed for %s; saving summary fields only.",
                                 case.display_title())
            try:
                self.save_case(case)
                saved.append(case)
            except Exception:
                logger.exception("Failed to save case %s; skipping.", case.display_title())
            if on_case_ready:
                on_case_ready(i, case)
            if on_progress:
                on_progress(i + 1, total)
        return saved

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_search_record(self, record: SearchRecord) -> Optional[int]:
        try:
            with get_connection() as conn:
                cur = conn.execute(
                    """INSERT INTO searches (search_type, query_text, state_code,
                                              dist_code, court_complex_code, case_status)
                       VALUES (:search_type, :query_text, :state_code,
                               :dist_code, :court_complex_code, :case_status)""",
                    record.to_row(),
                )
                return cur.lastrowid
        except DatabaseError:
            logger.error("Could not save search history record; continuing without it.")
            return None  # search history is best-effort, shouldn't block the search itself

    def save_case(self, case: Case) -> int:
        """
        Save (or update, if a case with the same CNR already exists) a
        case. Returns the row id. Cases without a CNR are always
        inserted fresh, since we can't reliably dedupe them.
        """
        row = case.to_row()
        with get_connection() as conn:
            if case.cnr:
                cur = conn.execute(
                    """INSERT INTO cases (search_id, cnr, case_number, case_type, filing_number,
                            filing_date, registration_number, registration_date, petitioner,
                            respondent, petitioner_advocate, respondent_advocate, case_stage,
                            case_status, next_hearing_date, next_hearing_iso, court_name, judge,
                            raw_json)
                       VALUES (:search_id, :cnr, :case_number, :case_type, :filing_number,
                            :filing_date, :registration_number, :registration_date, :petitioner,
                            :respondent, :petitioner_advocate, :respondent_advocate, :case_stage,
                            :case_status, :next_hearing_date, :next_hearing_iso, :court_name,
                            :judge, :raw_json)
                       ON CONFLICT(cnr) WHERE cnr != '' DO UPDATE SET
                            search_id = excluded.search_id,
                            case_number = excluded.case_number,
                            case_type = excluded.case_type,
                            filing_number = excluded.filing_number,
                            filing_date = excluded.filing_date,
                            registration_number = excluded.registration_number,
                            registration_date = excluded.registration_date,
                            petitioner = excluded.petitioner,
                            respondent = excluded.respondent,
                            petitioner_advocate = excluded.petitioner_advocate,
                            respondent_advocate = excluded.respondent_advocate,
                            case_stage = excluded.case_stage,
                            case_status = excluded.case_status,
                            next_hearing_date = excluded.next_hearing_date,
                            next_hearing_iso = excluded.next_hearing_iso,
                            court_name = excluded.court_name,
                            judge = excluded.judge,
                            raw_json = excluded.raw_json,
                            updated_at = datetime('now')
                       """,
                    row,
                )
                # lastrowid isn't reliable on an upsert path; look the row back up.
                updated = conn.execute("SELECT id FROM cases WHERE cnr = ?", (case.cnr,)).fetchone()
                case_id = updated["id"]
            else:
                cur = conn.execute(
                    """INSERT INTO cases (search_id, cnr, case_number, case_type, filing_number,
                            filing_date, registration_number, registration_date, petitioner,
                            respondent, petitioner_advocate, respondent_advocate, case_stage,
                            case_status, next_hearing_date, next_hearing_iso, court_name, judge,
                            raw_json)
                       VALUES (:search_id, :cnr, :case_number, :case_type, :filing_number,
                            :filing_date, :registration_number, :registration_date, :petitioner,
                            :respondent, :petitioner_advocate, :respondent_advocate, :case_stage,
                            :case_status, :next_hearing_date, :next_hearing_iso, :court_name,
                            :judge, :raw_json)""",
                    row,
                )
                case_id = cur.lastrowid
            logger.info("Saved case id=%s (%s)", case_id, case.display_title())
            return case_id
