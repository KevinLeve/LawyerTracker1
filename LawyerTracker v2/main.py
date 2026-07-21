"""
main.py

Application entry point.

For Milestone 1, this just wires together config -> logging -> database
initialization and confirms everything boots cleanly. The CustomTkinter
UI will be added in a later milestone and launched from here.
"""
from config import settings
from database import init_database
from app_utils.logger import get_logger

logger = get_logger(__name__)


def main() -> None:
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)
    init_database()

    from ui.app import LawyerTrackerApp
    app = LawyerTrackerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
