"""
enums.py

Enumerations shared across models, services, and UI. Using Enum instead
of raw strings ("cnr", "advocate"...) means typos get caught by the
type checker/IDE instead of failing silently at runtime deep in a
database query.
"""
from __future__ import annotations

from enum import Enum


class SearchType(str, Enum):
    CNR = "cnr"
    ADVOCATE = "advocate"
    CASE_NUMBER = "case_number"


class CaseStatus(str, Enum):
    PENDING = "PENDING"
    DISPOSED = "DISPOSED"
    UNKNOWN = ""


class CaptchaMode(str, Enum):
    MANUAL = "manual"
    OCR_ASSISTED = "ocr_assisted"
