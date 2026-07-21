"""
Configuration package for LawyerTracker.

Exposes a single `settings` object that the rest of the app imports,
so there is one source of truth for paths, constants, and app-wide values.
"""
from .settings import settings

__all__ = ["settings"]
