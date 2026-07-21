"""
exceptions.py

Custom exception hierarchy for LawyerTracker.

Design decision: rather than letting raw `requests.RequestException` or
`sqlite3.Error` bubble up into the UI layer, each layer catches low-level
errors and re-raises one of these typed exceptions. This lets the UI show
a friendly message based on *what kind* of failure happened (network vs.
CAPTCHA vs. database) without needing to know about requests/sqlite3 at all.
"""


class LawyerTrackerError(Exception):
    """Base class for all application-specific errors."""


class NetworkError(LawyerTrackerError):
    """Raised when a request to the eCourts portal fails (timeout, DNS, etc.)."""


class CaptchaError(LawyerTrackerError):
    """Raised when CAPTCHA retrieval or validation fails."""


class SearchError(LawyerTrackerError):
    """Raised when a case search request fails or returns an unexpected shape."""


class DatabaseError(LawyerTrackerError):
    """Raised when a local database read/write operation fails."""


class ValidationError(LawyerTrackerError):
    """Raised when user input fails validation before being sent anywhere."""
