"""
profile.py

This app is built for one advocate on their own machine, so there's a
single Profile row rather than a multi-user accounts system. Collected
once during onboarding: their name, and the court complex they
primarily practice in (used to prefill the search form's location
picker so they don't re-select it every single search).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class Profile:
    advocate_name: str = ""
    default_state_code: str = ""
    default_state_name: str = ""
    default_dist_code: str = ""
    default_dist_name: str = ""
    default_court_complex_code: str = ""
    default_court_complex_name: str = ""

    def is_complete(self) -> bool:
        return bool(self.advocate_name)

    def to_row(self) -> dict[str, Any]:
        return {
            "advocate_name": self.advocate_name,
            "default_state_code": self.default_state_code,
            "default_state_name": self.default_state_name,
            "default_dist_code": self.default_dist_code,
            "default_dist_name": self.default_dist_name,
            "default_court_complex_code": self.default_court_complex_code,
            "default_court_complex_name": self.default_court_complex_name,
        }

    @classmethod
    def from_row(cls, row: Optional[Any]) -> "Profile":
        if row is None:
            return cls()
        return cls(
            advocate_name=row["advocate_name"] or "",
            default_state_code=row["default_state_code"] or "",
            default_state_name=row["default_state_name"] or "",
            default_dist_code=row["default_dist_code"] or "",
            default_dist_name=row["default_dist_name"] or "",
            default_court_complex_code=row["default_court_complex_code"] or "",
            default_court_complex_name=row["default_court_complex_name"] or "",
        )
