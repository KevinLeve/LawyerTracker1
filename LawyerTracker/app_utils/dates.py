"""
dates.py

The eCourts portal returns dates in inconsistent formats depending on
which field/page they came from - "21-04-2026" in some tables, "19th
June 2026" (with ordinal suffix) in the case-detail view. Neither sorts
correctly as plain text, so this module converts whatever we get into
a proper ISO "YYYY-MM-DD" string, which we store alongside the original
text so the dashboard can `ORDER BY` it in SQL.

Best-effort by design: if a date string doesn't match any known
pattern, we return None rather than guessing - the UI falls back to
showing "no date" instead of a wrong sort position.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

_ORDINAL_SUFFIX = re.compile(r"(\d+)(st|nd|rd|th)", re.IGNORECASE)

_FORMATS = [
    "%d-%m-%Y",   # 21-04-2026
    "%d/%m/%Y",   # 21/04/2026
    "%d %B %Y",   # 19 June 2026 (after stripping ordinal suffix)
    "%d %b %Y",   # 19 Jun 2026
]


def parse_flexible_date(text: str) -> Optional[str]:
    """Return 'YYYY-MM-DD' for a recognized date string, else None."""
    if not text:
        return None
    cleaned = _ORDINAL_SUFFIX.sub(r"\1", text).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)

    for fmt in _FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None
