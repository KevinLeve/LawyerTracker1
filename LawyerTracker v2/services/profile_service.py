"""
profile_service.py

Manages the single-row `profile` table: the advocate's name and default
practicing court, collected once during onboarding.
"""
from __future__ import annotations

from database import get_connection
from models.profile import Profile
from app_utils.logger import get_logger

logger = get_logger(__name__)


class ProfileService:
    def get_profile(self) -> Profile:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
            return Profile.from_row(row)

    def is_onboarded(self) -> bool:
        return self.get_profile().is_complete()

    def save_profile(self, profile: Profile) -> None:
        with get_connection() as conn:
            row = profile.to_row()
            conn.execute(
                """INSERT INTO profile (id, advocate_name, default_state_code,
                        default_state_name, default_dist_code, default_dist_name,
                        default_court_complex_code, default_court_complex_name)
                   VALUES (1, :advocate_name, :default_state_code, :default_state_name,
                        :default_dist_code, :default_dist_name,
                        :default_court_complex_code, :default_court_complex_name)
                   ON CONFLICT(id) DO UPDATE SET
                        advocate_name = excluded.advocate_name,
                        default_state_code = excluded.default_state_code,
                        default_state_name = excluded.default_state_name,
                        default_dist_code = excluded.default_dist_code,
                        default_dist_name = excluded.default_dist_name,
                        default_court_complex_code = excluded.default_court_complex_code,
                        default_court_complex_name = excluded.default_court_complex_name
                """,
                row,
            )
            logger.info("Profile saved for advocate: %s", profile.advocate_name)
