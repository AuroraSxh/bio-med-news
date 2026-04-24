import logging
import sys

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.services.database_init import init_database
from worker.scheduler import run_once, start_scheduler


def main() -> None:
    setup_logging()
    logger = logging.getLogger("worker")
    logger.info("Starting Phase 4 worker.")
    init_database()

    if "--once" in sys.argv:
        run_once()
        return

    if get_settings().worker_run_on_startup:
        run_once()

    start_scheduler()


if __name__ == "__main__":
    main()
