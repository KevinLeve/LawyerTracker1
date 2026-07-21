"""
settings.py

Central configuration for LawyerTracker.

Design decision: instead of scattering magic strings/paths across the
codebase (file paths, timeouts, the eCourts base URL, log levels), we
define one dataclass instance called `settings` that every other module
imports. This means:

  - There's exactly one place to change "where does data live" or
    "what's the eCourts base URL" when something changes.
  - Modules stay decoupled from filesystem details - e.g. the database
    module just asks `settings.DB_PATH`, it doesn't compute paths itself.
  - It's easy to override values for testing (construct a different
    Settings instance) without touching business logic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


# Project root = two levels up from this file (config/settings.py -> project root)
BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    # --- Filesystem layout ---
    base_dir: Path = BASE_DIR
    data_dir: Path = BASE_DIR / "data"
    logs_dir: Path = BASE_DIR / "logs"
    assets_dir: Path = BASE_DIR / "assets"

    db_path: Path = BASE_DIR / "data" / "lawyertracker.db"
    log_file: Path = BASE_DIR / "logs" / "app.log"

    # --- eCourts public portal ---
    # This is the same public web portal (not the internal mobile-app API)
    # that a citizen or advocate would use in a browser.
    ecourts_base_url: str = "https://services.ecourts.gov.in/ecourtindia_v6/"
    request_timeout_seconds: int = 20

    # --- App metadata ---
    app_name: str = "LawyerTracker"
    app_version: str = "0.1.0"

    # --- UI ---
    window_width: int = 1000
    window_height: int = 680
    appearance_mode: str = "System"   # CustomTkinter: "System" | "Dark" | "Light"
    color_theme: str = "assets/theme_professional.json"  # resolved relative to base_dir at load time

    # --- Logging ---
    log_level: str = "INFO"


    def ensure_directories(self) -> None:
        """Create data/logs/assets directories if they don't exist yet."""
        for directory in (self.data_dir, self.logs_dir, self.assets_dir):
            directory.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_directories()
