"""
location_service.py

Feeds the Home screen's State -> District -> Court Complex cascade.
States are static (loaded once from assets/states.json, since the
portal embeds them directly in its page rather than serving them via
AJAX). Districts and court complexes depend on the previous selection,
so those go through the live client.
"""
from __future__ import annotations

import json
from typing import Optional

from api.ecourts_client import EcourtsClient
from api.parser import parse_options
from config import settings
from app_utils.logger import get_logger

logger = get_logger(__name__)


class LocationService:
    def __init__(self, client: EcourtsClient) -> None:
        self._client = client
        self._states_cache: Optional[list[dict[str, str]]] = None

    def get_states(self) -> list[dict[str, str]]:
        if self._states_cache is None:
            path = settings.assets_dir / "states.json"
            with open(path, encoding="utf-8") as f:
                all_states = json.load(f)
            self._states_cache = [s for s in all_states if s["code"] != "0"]
        return self._states_cache

    def get_districts(self, state_code: str) -> list[dict[str, str]]:
        html = self._client.fetch_districts(state_code)
        districts = parse_options(html)
        logger.info("Loaded %d districts for state_code=%s", len(districts), state_code)
        return districts

    def get_court_complexes(self, state_code: str, dist_code: str) -> list[dict[str, str]]:
        html = self._client.fetch_court_complexes(state_code, dist_code)
        complexes = parse_options(html)
        logger.info("Loaded %d court complexes for state_code=%s dist_code=%s",
                    len(complexes), state_code, dist_code)
        return complexes
