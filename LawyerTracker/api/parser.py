"""
parser.py

All HTML/JSON -> Python parsing for eCourts portal responses lives here,
kept separate from `ecourts_client.py` (which only does HTTP). This
separation means: if the portal's HTML structure changes, we only touch
this file, and we can unit-test parsing against saved HTML fixtures
without making a single network call.
"""
from __future__ import annotations

import ast
import json
import re
from typing import Any, Optional

from bs4 import BeautifulSoup

from models.case import Case
from app_utils.logger import get_logger

logger = get_logger(__name__)


def clean_text(value: str) -> str:
    """Collapse whitespace/non-breaking-spaces the portal's HTML is full of."""
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def parse_options(response_text: str) -> list[dict[str, str]]:
    """
    Parse the district/court-complex AJAX response into a list of
    {code, name} dicts.

    Verified against real captures: `fillDistrict` returns
    `{"dist_list": "<option value=30 >Ariyalur</option>..."}` and
    `fillcomplex` returns `{"complex_list": "<option value=1100026@...>
    District Court Complex, Pudukkottai</option>...", "status": 1}` -
    i.e. JSON envelopes containing an HTML fragment, not raw HTML. We
    unwrap the JSON first; if that fails (e.g. a fixture with just the
    raw fragment), we fall back to treating the input as HTML directly.
    """
    html = response_text
    try:
        payload = json.loads(response_text)
        html = payload.get("dist_list") or payload.get("complex_list") or response_text
    except (json.JSONDecodeError, TypeError):
        pass

    soup = BeautifulSoup(html, "lxml")
    options = []
    for opt in soup.find_all("option"):
        raw_value = (opt.get("value") or "").strip()
        # Court-complex values look like "1100026@2,5,6,7,8@N" - the
        # portal's own JS splits on "@" and only submits the first
        # segment as court_complex_code (confirmed against
        # full_tracker.py's plain "1100026" usage), so we do the same.
        code = raw_value.split("@")[0].strip()
        name = clean_text(opt.get_text())
        if code and code != "0":
            options.append({"code": code, "name": name})
    return options


def parse_advocate_search_results(response_json: dict[str, Any]) -> list[Case]:
    """
    Parse the JSON returned by `?p=casestatus/submitAdvName`.

    The portal returns a JSON object where the case list is embedded as
    an HTML table under a key such as "Data" (exact key can vary by
    portal version) - we defensively search likely keys.
    """
    html_fragment = (
        response_json.get("Data")
        or response_json.get("data")
        or response_json.get("adv_data")
        or ""
    )
    if not html_fragment:
        logger.warning("Advocate search response had no recognizable case-list field: %s",
                        list(response_json.keys()))
        return []

    return _extract_cases_from_table_html(html_fragment)


def _extract_cases_from_table_html(html_fragment: str) -> list[Case]:
    soup = BeautifulSoup(html_fragment, "lxml")
    cases: list[Case] = []

    for row in soup.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 4:
            continue

        case_number = clean_text(cols[1].get_text(" ", strip=True))
        parties = clean_text(cols[2].get_text(" ", strip=True))
        advocate = clean_text(cols[3].get_text(" ", strip=True))

        view_link = row.find("a")
        onclick = ""
        if view_link:
            onclick = view_link.get("onclick") or view_link.get("onClick") or ""
            onclick = onclick.replace('\\"', '"').strip('"').strip("'")

        view_args: Optional[tuple] = None
        if "viewHistory" in onclick:
            m = re.search(r"viewHistory\((.*?)\)", onclick)
            if m:
                try:
                    view_args = ast.literal_eval("(" + m.group(1) + ")")
                except (ValueError, SyntaxError):
                    view_args = None

        petitioner, respondent = "", ""
        # The portal separates parties with "<br>Vs</br>", which after
        # text-flattening sometimes collapses to "...Branch VsAbinaya"
        # (no space before the respondent name). A plain " Vs " split
        # misses that case, so split on whitespace + "Vs" + optional
        # whitespace, followed by the start of the next party's name
        # (an uppercase letter).
        vs_split = re.split(r"\s+Vs\s*(?=[A-Z])", parties, maxsplit=1)
        if len(vs_split) == 2:
            petitioner, respondent = (p.strip() for p in vs_split)
        else:
            petitioner = parties

        case = Case(
            case_number=case_number,
            petitioner=petitioner,
            respondent=respondent,
            petitioner_advocate=advocate,
            extra={"view_args": list(view_args) if view_args else None},
        )
        cases.append(case)

    return cases


def _table_header_texts(table) -> list[str]:
    """
    Get header cell texts. Most tables wrap header cells in a <tr>
    inside (or instead of) <thead>, but the portal's "Case History"
    table puts <th> elements directly under <thead> with no <tr> at
    all (confirmed against a real capture) - so we check <thead> first
    and fall back to the first <tr> in the table.
    """
    thead = table.find("thead")
    if thead is not None:
        headers = [clean_text(c.get_text(" ")) for c in thead.find_all(["th", "td"])]
        if headers:
            return headers
    first_row = table.find("tr")
    if not first_row:
        return []
    return [clean_text(c.get_text(" ")) for c in first_row.find_all(["th", "td"])]


def _data_rows(table):
    """
    Return the rows that hold actual data, not header rows. Prefers
    <tbody>'s rows when present (the reliable case, since <thead> then
    unambiguously holds only headers); otherwise falls back to "all
    rows except the first" for tables with no explicit thead/tbody.
    """
    tbody = table.find("tbody")
    if tbody is not None:
        return tbody.find_all("tr")
    rows = table.find_all("tr")
    return rows[1:] if len(rows) > 1 else []


def _parse_kv_table(table) -> dict[str, str]:
    """
    Parse a table made of th/td pairs into a flat dict. Handles rows
    with either one pair (th, td) or two pairs (th, td, th, td) per
    row, both of which appear in the portal's Case Details/Case Status
    tables (e.g. "Case Stage" and "Sub Stage" share one row).
    """
    result: dict[str, str] = {}
    if table is None:
        return result
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        for i in range(0, len(cells) - 1, 2):
            key = clean_text(cells[i].get_text(" "))
            value = clean_text(cells[i + 1].get_text(" "))
            if key:
                result[key] = value
    return result


def _parse_rows_table(table, column_names: list[str]) -> list[dict[str, str]]:
    """Parse a table with a header row into a list of {column: value} dicts (header row itself skipped)."""
    if table is None:
        return []
    result = []
    for tr in _data_rows(table):
        cells = tr.find_all(["th", "td"])
        if not cells:
            continue
        entry = {name: clean_text(cell.get_text(" ")) for name, cell in zip(column_names, cells)}
        result.append(entry)
    return result


def _find_table_by_headers(tables, *must_contain: str):
    """Find the first table whose header row text contains all of the given substrings (case-insensitive)."""
    for table in tables:
        joined = " ".join(_table_header_texts(table)).lower()
        if all(needle.lower() in joined for needle in must_contain):
            return table
    return None


def parse_case_history(history_json: dict[str, Any]) -> Case:
    """
    Parse the JSON returned by `?p=home/viewHistory` (case detail view)
    into a fully-populated Case.

    Case Details / Case Status fields come from the portal's own
    key-value tables (tree-parsed, not text-regexed) - this is more
    robust than scraping flattened text and was confirmed against a
    real disposed-case screenshot: "Case Status" is a literal field in
    that table with a value like "Case disposed", which we now read
    directly as the primary signal instead of inferring it. Presence of
    "Decision Date"/"Nature of Disposal" vs. "Next Hearing Date" is kept
    as a fallback for the rare case that field is blank.

    Acts / FIR Details / Case History are parsed as their own
    structured tables (list of rows / dict), matching how the portal
    actually renders them, instead of a flat text blob to dump in a
    textbox. Court name and the Petitioner/Respondent party lists are
    still pulled from flattened text via regex, since that approach is
    already confirmed working against a real fixture and rewriting it
    isn't necessary for what changed here.
    """
    html = history_json.get("data_list", "")
    if not html:
        return Case()

    soup = BeautifulSoup(html, "lxml")
    text = clean_text(soup.get_text(" "))
    all_tables = soup.find_all("table")

    def pick(pattern: str) -> str:
        m = re.search(pattern, text, re.S | re.I)
        return clean_text(m.group(1)) if m else ""

    def split_party_advocate(section: str) -> tuple[str, str]:
        section = re.sub(r"^\d+\)\s*", "", section.strip())
        if "Advocate-" in section:
            name, _, advocate = section.partition("Advocate-")
            return clean_text(name), clean_text(advocate)
        return clean_text(section), ""

    petitioner_section = pick(r"Petitioner and Advocate (.*?) Respondent and Advocate")
    respondent_section = pick(r"Respondent and Advocate (.*?) Acts")
    petitioner_name, petitioner_advocate = split_party_advocate(petitioner_section)
    respondent_name, respondent_advocate = split_party_advocate(respondent_section)

    # Case Details table: has no header row of its own, just kv rows
    # (Case Type, Filing Number, Filing Date, Registration Number,
    # Registration Date, CNR Number, e-Filing Number, e-Filing Date).
    case_details_table = next(
        (t for t in all_tables if "Case Type" in _parse_kv_table(t)), None
    )
    case_details = _parse_kv_table(case_details_table)

    # Case Status table: identified by its CSS class in the confirmed
    # fixture, with a fallback lookup by content in case a different
    # court's template omits the class.
    case_status_table = soup.find("table", class_="case_status_table") or next(
        (t for t in all_tables if "Case Stage" in _parse_kv_table(t)
         or "First Hearing Date" in _parse_kv_table(t)), None
    )
    case_status = _parse_kv_table(case_status_table)

    cnr_raw = case_details.get("CNR Number", "")
    cnr = cnr_raw.split()[0] if cnr_raw else ""

    next_hearing_date = case_status.get("Next Hearing Date", "")
    decision_date = case_status.get("Decision Date", "")
    nature_of_disposal = case_status.get("Nature of Disposal", "")
    case_status_text = case_status.get("Case Status", "")

    if case_status_text:
        if "dispos" in case_status_text.lower():
            inferred_status = "DISPOSED"
        elif "pending" in case_status_text.lower():
            inferred_status = "PENDING"
        else:
            inferred_status = ""
    elif decision_date or nature_of_disposal:
        inferred_status = "DISPOSED"
    elif next_hearing_date:
        inferred_status = "PENDING"
    else:
        inferred_status = ""

    # Acts: "Under Act(s)" / "Under Section(s)" columns, possibly
    # several rows for multi-section cases.
    acts_table = _find_table_by_headers(all_tables, "Under Act")
    acts = _parse_rows_table(acts_table, ["act", "section"])

    # FIR Details: only present for criminal cases with a linked FIR -
    # a plain "Field" / "Details" key-value table.
    fir_table = _find_table_by_headers(all_tables, "Field", "Details")
    fir_rows = _parse_rows_table(fir_table, ["field", "value"])
    fir_details = {r["field"]: r["value"] for r in fir_rows if r.get("field")}

    # Case History: Judge / Business on Date / Hearing Date / Purpose
    # of Hearing - the actual hearing-by-hearing log.
    history_table = _find_table_by_headers(all_tables, "Judge", "Hearing Date")
    case_history = _parse_rows_table(
        history_table, ["judge", "business_date", "hearing_date", "purpose"]
    )

    return Case(
        court_name=pick(r"^(.*?) Case Details"),
        case_type=case_details.get("Case Type", ""),
        filing_number=case_details.get("Filing Number", ""),
        filing_date=case_details.get("Filing Date", ""),
        registration_number=case_details.get("Registration Number", ""),
        registration_date=case_details.get("Registration Date", ""),
        cnr=cnr,
        case_stage=case_status.get("Case Stage", ""),
        case_status=inferred_status,
        next_hearing_date=next_hearing_date,
        judge=case_status.get("Court Number and Judge", ""),
        petitioner=petitioner_name,
        respondent=respondent_name,
        petitioner_advocate=petitioner_advocate,
        respondent_advocate=respondent_advocate,
        extra={
            "sub_stage": case_status.get("Sub Stage", ""),
            "e_filing_number": case_details.get("e-Filing Number", ""),
            "e_filing_date": case_details.get("e-Filing Date", ""),
            "first_hearing_date": case_status.get("First Hearing Date", ""),
            "decision_date": decision_date,
            "nature_of_disposal": nature_of_disposal,
            "case_status_text": case_status_text,
            "acts": acts,
            "fir_details": fir_details,
            "case_history": case_history,
            "status_inferred": bool(not case_status_text and (decision_date or nature_of_disposal or next_hearing_date)),
        },
    )
