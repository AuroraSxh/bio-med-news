import logging
from contextlib import suppress
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfoNotFoundError

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings
from app.db import SessionLocal
from app.services.ingestion import run_ingestion_cycle

logger = logging.getLogger(__name__)


def run_once() -> None:
    with SessionLocal() as db:
        run_ingestion_cycle(db, trigger="worker_once")


def start_scheduler() -> None:
    settings = get_settings()
    try:
        timezone = ZoneInfo(settings.ingestion_timezone)
        timezone_name = settings.ingestion_timezone
    except ZoneInfoNotFoundError:
        timezone_name = "Asia/Shanghai"
        timezone = ZoneInfo(timezone_name)
        logger.error("invalid INGESTION_TIMEZONE=%s; falling back to %s", settings.ingestion_timezone, timezone_name)

    scheduler = BlockingScheduler(timezone=timezone)

    hours = _safe_schedule_hours(settings.ingestion_schedule_hours)
    for hour in hours:
        job = scheduler.add_job(
            run_once,
            CronTrigger(hour=hour, minute=0, timezone=timezone),
            id=f"ingestion_{hour:02d}00",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
        )
        logger.info("worker scheduled job id=%s next_run=%s", job.id, getattr(job, "next_run_time", None))
    logger.info("worker scheduler started timezone=%s hours=%s", timezone_name, ",".join(str(hour) for hour in hours))
    scheduler.start()


def _parse_schedule_hours(value: str) -> list[int]:
    hours: list[int] = []
    for part in value.split(","):
        stripped = part.strip()
        if not stripped:
            continue
        hour = int(stripped)
        if hour < 0 or hour > 23:
            raise ValueError(f"invalid ingestion schedule hour: {hour}")
        hours.append(hour)
    return hours or [8, 12, 18]


def _safe_schedule_hours(value: str) -> list[int]:
    with suppress(ValueError):
        return _parse_schedule_hours(value)
    logger.error("invalid INGESTION_SCHEDULE_HOURS=%s; falling back to 8,12,18", value)
    return [8, 12, 18]
