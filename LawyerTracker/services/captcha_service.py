"""
captcha_service.py

Owns CAPTCHA image retrieval, and the *optional* KevinOCR suggestion.

Important design decision, matching what we agreed on:
    OCR is a SUGGESTION ONLY. `suggest_text()` returns a best-guess
    string for the UI to pre-fill into the editable text box - it never
    submits anything itself and the CAPTCHA screen always requires an
    explicit user click on Submit. There is no code path in this file
    (or anywhere else in the app) that solves a CAPTCHA and sends a
    request without a human clicking Submit first.

KevinOCR's folder path is read from ConfigService (user-editable via
the Settings screen -> "Browse for KevinOCR folder"), not hardcoded in
config/settings.py, so turning OCR-assist on/off doesn't require
touching code. It's loaded lazily and defensively: if unset, or the
KevinOCR project isn't importable, or prediction fails for any reason,
OCR-assisted mode is simply unavailable and the app falls back to
manual entry - it never crashes the CAPTCHA screen.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from api.ecourts_client import EcourtsClient
from services.config_service import ConfigService
from app_utils.logger import get_logger

logger = get_logger(__name__)

_CONFIG_KEY = "kevinocr_dir"


class CaptchaService:
    def __init__(self, client: EcourtsClient, config_service: Optional[ConfigService] = None) -> None:
        self._client = client
        self._config = config_service or ConfigService()
        self._ocr_engine = None
        self._ocr_load_attempted_for_dir: Optional[str] = None

    # ------------------------------------------------------------------
    # CAPTCHA image
    # ------------------------------------------------------------------

    def fetch_image_bytes(self) -> bytes:
        return self._client.refresh_captcha()

    # ------------------------------------------------------------------
    # Optional OCR suggestion (never auto-submits - see module docstring)
    # ------------------------------------------------------------------

    def ocr_available(self) -> bool:
        return self._load_ocr_engine() is not None

    def suggest_text(self, image_path: str) -> Optional[str]:
        """
        Returns a best-guess CAPTCHA string to pre-fill in the UI, or
        None if OCR isn't available/configured or prediction fails.
        The caller (UI) is responsible for putting this in an editable
        field and still requiring the user to press Submit.
        """
        engine = self._load_ocr_engine()
        if engine is None:
            return None
        try:
            prediction = engine.predict(image_path)
            logger.info("KevinOCR suggestion generated for CAPTCHA screen.")
            return prediction
        except Exception:
            logger.exception("KevinOCR prediction failed; falling back to manual entry.")
            return None

    def _load_ocr_engine(self):
        configured_dir = self._config.get(_CONFIG_KEY)

        # Re-attempt if the configured directory changed since last time
        # (e.g. the user just set it in the Settings screen) or if we
        # haven't tried yet.
        if self._ocr_engine is not None and configured_dir == self._ocr_load_attempted_for_dir:
            return self._ocr_engine
        if configured_dir == self._ocr_load_attempted_for_dir and self._ocr_engine is None:
            return None

        self._ocr_load_attempted_for_dir = configured_dir
        self._ocr_engine = None

        if not configured_dir:
            logger.info("KevinOCR not configured; OCR-assisted mode disabled, manual entry only.")
            return None

        kevinocr_path = Path(configured_dir)
        if not kevinocr_path.exists():
            logger.warning("Configured KevinOCR dir %s does not exist; "
                           "OCR-assisted mode disabled.", kevinocr_path)
            return None

        try:
            path_str = str(kevinocr_path)
            if path_str not in sys.path:
                sys.path.insert(0, path_str)
            from ocr.engine import OCREngine  # type: ignore

            # OCREngine/OCRPredictor default to relative paths
            # ("models/character_model.pth"), which only resolve
            # correctly if the process's working directory happens to
            # be KevinOCR's own folder. Since we're running from
            # LawyerTracker's directory, we build absolute paths from
            # the configured folder instead.
            model_path = kevinocr_path / "models" / "character_model.pth"
            classes_path = kevinocr_path / "models" / "classes.txt"
            self._ocr_engine = OCREngine(model_path=str(model_path), classes_path=str(classes_path))
            logger.info("KevinOCR engine loaded from %s", kevinocr_path)
            return self._ocr_engine
        except Exception:
            logger.exception("Failed to load KevinOCR engine; OCR-assisted mode disabled.")
            return None
