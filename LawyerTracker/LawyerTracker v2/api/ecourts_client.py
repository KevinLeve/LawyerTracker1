"""
ecourts_client.py

Thin HTTP client for the **public** eCourts case-status portal
(`services.ecourts.gov.in/ecourtindia_v6/`) - the same site a citizen or
advocate uses in a browser. This mirrors what your `full_tracker.py`,
`district_test.py`, `complex_test.py`, and `captcha_test.py` scripts were
already doing manually, just organized into one reusable class.

Deliberately NOT included: the reverse-engineered internal mobile-app API
documented in your `API_INVENTORY.md` (AES-encrypted request params,
extracted from the APK's bytecode). That approach impersonates the
official app using keys pulled out of its compiled code, which is a
different thing from automating a public web form - so it's left out.

Confidence levels of each method (see inline notes):
  - VERIFIED against your saved captures: session bootstrap, CAPTCHA
    fetch, district cascade, court-complex cascade, advocate-name search,
    case history/detail fetch.
  - UNVERIFIED / best-guess: CNR search and case-number search endpoints.
    I don't have a captured request/response for these two in the files
    you gave me, so the endpoint paths and field names below are modeled
    on the same portal's naming conventions but need to be tested against
    the live site and corrected if the real endpoint differs. They're
    isolated in their own methods so fixing them later doesn't ripple
    into the rest of the client.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import requests

from config import settings
from app_utils.exceptions import CaptchaError, NetworkError, SearchError
from app_utils.logger import get_logger

logger = get_logger(__name__)


class EcourtsClient:
    """
    Wraps a `requests.Session` against the eCourts case-status portal.

    One EcourtsClient instance = one browsing session (cookies persist
    across calls, which the portal requires - CAPTCHA validation is tied
    to the session that fetched it).
    """

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        })
        self._base = settings.ecourts_base_url
        self._bootstrapped = False

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def bootstrap(self) -> None:
        """
        Load the case-status page once to establish session cookies.
        Must be called before anything else (CAPTCHA, cascades, search).
        """
        try:
            self._session.get(
                self._base + "?p=casestatus/index",
                timeout=settings.request_timeout_seconds,
            )
            self._bootstrapped = True
            logger.info("eCourts session bootstrapped.")
        except requests.RequestException as exc:
            logger.exception("Failed to bootstrap eCourts session.")
            raise NetworkError("Could not reach the eCourts portal.") from exc

    def _ensure_bootstrapped(self) -> None:
        if not self._bootstrapped:
            self.bootstrap()

    def _post(self, path: str, data: dict[str, Any]) -> requests.Response:
        self._ensure_bootstrapped()
        try:
            return self._session.post(
                self._base + path,
                data={**data, "ajax_req": "true", "app_token": ""},
                timeout=settings.request_timeout_seconds,
            )
        except requests.RequestException as exc:
            logger.exception("POST %s failed.", path)
            raise NetworkError(f"Request to eCourts portal failed ({path}).") from exc

    # ------------------------------------------------------------------
    # Location cascade (state list is static, see assets/states.json)
    # ------------------------------------------------------------------

    def fetch_districts(self, state_code: str) -> str:
        """Returns raw JSON text like {"dist_list": "<option ...>..."} - parse with api.parser.parse_options."""
        resp = self._post("?p=casestatus/fillDistrict", {"state_code": state_code})
        return resp.text

    def fetch_court_complexes(self, state_code: str, dist_code: str) -> str:
        """Returns raw JSON text like {"complex_list": "<option ...>...", "status": 1}."""
        resp = self._post(
            "?p=casestatus/fillcomplex",
            {"state_code": state_code, "dist_code": dist_code},
        )
        return resp.text

    # ------------------------------------------------------------------
    # CAPTCHA
    # ------------------------------------------------------------------

    def refresh_captcha(self) -> bytes:
        """
        Fetch a fresh CAPTCHA image tied to the current session. Call
        this once to load the CAPTCHA screen, and again whenever the
        user clicks "Refresh CAPTCHA".
        """
        self._ensure_bootstrapped()
        try:
            self._session.post(
                self._base + "?p=casestatus/getCaptcha",
                data={"ajax_req": "true", "app_token": ""},
                timeout=settings.request_timeout_seconds,
            )
            img = self._session.get(
                self._base + "vendor/securimage/securimage_show.php",
                timeout=settings.request_timeout_seconds,
            )
            img.raise_for_status()
            return img.content
        except requests.RequestException as exc:
            logger.exception("Failed to fetch CAPTCHA image.")
            raise CaptchaError("Could not load a CAPTCHA image from the portal.") from exc

    # ------------------------------------------------------------------
    # Search - VERIFIED: advocate name search
    # ------------------------------------------------------------------

    def search_by_advocate_name(
        self,
        advocate_name: str,
        captcha_text: str,
        state_code: str,
        dist_code: str,
        court_complex_code: str,
        case_status: str = "Pending",
    ) -> dict[str, Any]:
        from datetime import datetime

        payload = {
            "radAdvt": "1",
            "advocate_name": advocate_name,
            "adv_bar_state": "",
            "adv_bar_code": "",
            "adv_bar_year": "",
            "case_status": case_status,
            "caselist_date": datetime.now().strftime("%d-%m-%Y"),
            "adv_captcha_code": captcha_text,
            "state_code": state_code,
            "dist_code": dist_code,
            "court_complex_code": court_complex_code,
            "est_code": "0",
            "case_type": "",
        }
        resp = self._post("?p=casestatus/submitAdvName", payload)
        return self._parse_json_or_raise(resp, "advocate name search")

    # ------------------------------------------------------------------
    # Search - UNVERIFIED: CNR and case-number search
    #
    # These follow the same request shape as the verified advocate
    # search (same portal, same CAPTCHA field convention) but the exact
    # endpoint path and field names were not present in your captured
    # test scripts, so treat these as a starting point to test and fix
    # against the live portal rather than confirmed-working code.
    # ------------------------------------------------------------------

    def search_by_cnr(self, cnr_number: str, captcha_text: str) -> dict[str, Any]:
        payload = {
            "cino": cnr_number,
            "fcaptcha_code": captcha_text,  # UNVERIFIED field name
        }
        resp = self._post("?p=cnrstatus/searchByCino", payload)  # UNVERIFIED endpoint
        return self._parse_json_or_raise(resp, "CNR search")

    def search_by_case_number(
        self,
        case_type: str,
        case_number: str,
        case_year: str,
        captcha_text: str,
        state_code: str,
        dist_code: str,
        court_complex_code: str,
    ) -> dict[str, Any]:
        payload = {
            "case_type": case_type,
            "search_case_no": case_number,
            "rgyear": case_year,
            "case_captcha_code": captcha_text,  # UNVERIFIED field name
            "state_code": state_code,
            "dist_code": dist_code,
            "court_complex_code": court_complex_code,
            "est_code": "0",
        }
        resp = self._post("?p=casestatus/submitCaseNo", payload)  # UNVERIFIED endpoint
        return self._parse_json_or_raise(resp, "case number search")

    # ------------------------------------------------------------------
    # Case detail / history - VERIFIED
    # ------------------------------------------------------------------

    def fetch_case_history(self, view_args: list) -> dict[str, Any]:
        """
        `view_args` comes from the `viewHistory(...)` onclick handler
        parsed out of a search-results row by api.parser.
        Expected shape (9 positional values), matching your full_tracker.py:
            [case_no, cino, court_code, ?, search_flag, state_code,
             dist_code, court_complex_code, search_by]
        """
        if not view_args or len(view_args) < 9:
            raise SearchError("Case row did not contain enough data to fetch its history.")

        payload = {
            "court_code": str(view_args[2]),
            "state_code": str(view_args[5]),
            "dist_code": str(view_args[6]),
            "court_complex_code": str(view_args[7]),
            "case_no": str(view_args[0]),
            "cino": str(view_args[1]),
            "hideparty": "",
            "search_flag": str(view_args[4]),
            "search_by": str(view_args[8]),
        }
        resp = self._post("?p=home/viewHistory", payload)
        return self._parse_json_or_raise(resp, "case history fetch")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json_or_raise(resp: requests.Response, action: str) -> dict[str, Any]:
        try:
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.exception("%s HTTP error.", action)
            raise NetworkError(f"Network error during {action}.") from exc
        except json.JSONDecodeError as exc:
            logger.error("%s returned non-JSON response (first 300 chars): %s",
                         action, resp.text[:300])
            raise SearchError(
                f"Unexpected response during {action}. "
                "This usually means the CAPTCHA was wrong or the endpoint needs updating."
            ) from exc
