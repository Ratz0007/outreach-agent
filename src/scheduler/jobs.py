"""APScheduler cron definitions — Stage 14.

Runs the daily pipeline on schedule:
  08:00 — Job sourcing
  08:30 — Contact enrichment
  09:00 — Message generation
  10:00 — Send outreach (after manual review)
  17:00 — Check replies
  20:00 — Daily digest
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import AgentConfig

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def _run_source():
    """Stage 1: Job sourcing."""
    try:
        from src.sourcing.adzuna import source_jobs
        count = source_jobs()
        logger.info(f"[Scheduler] Sourced {count} jobs")
    except Exception as e:
        logger.error(f"[Scheduler] Source failed: {e}")


def _run_enrich():
    """Stage 2: Contact enrichment."""
    try:
        from src.enrichment.apollo import enrich_contacts
        count = enrich_contacts()
        logger.info(f"[Scheduler] Enriched {count} contacts")
    except Exception as e:
        logger.error(f"[Scheduler] Enrich failed: {e}")


def _run_generate():
    """Stage 3: Message generation."""
    try:
        from src.messaging.generator import generate_messages
        count = generate_messages()
        logger.info(f"[Scheduler] Generated {count} drafts")
    except Exception as e:
        logger.error(f"[Scheduler] Generate failed: {e}")


def _run_send():
    """Stage 4: Send approved outreach."""
    try:
        from src.outreach.gmail import send_approved_emails
        count = send_approved_emails()
        logger.info(f"[Scheduler] Sent {count} emails")
    except Exception as e:
        logger.error(f"[Scheduler] Send failed: {e}")


def _run_check_replies():
    """Stage 5: Process responses."""
    try:
        from src.tracking.response_handler import check_and_classify_replies
        count = check_and_classify_replies()
        logger.info(f"[Scheduler] Processed {count} replies")
    except Exception as e:
        logger.error(f"[Scheduler] Reply check failed: {e}")


def _run_digest():
    """Stage 8: Daily digest."""
    try:
        from src.digest.daily import send_daily_digest
        send_daily_digest()
        logger.info("[Scheduler] Daily digest sent")
    except Exception as e:
        logger.error(f"[Scheduler] Digest failed: {e}")


def setup_scheduler():
    """Configure and start the APScheduler with all cron jobs."""
    schedule = AgentConfig.schedule

    def _parse_time(time_str: str) -> tuple[int, int]:
        """Parse 'HH:MM' into (hour, minute)."""
        parts = time_str.split(":")
        return int(parts[0]), int(parts[1])

    # Stage 1: Source jobs
    h, m = _parse_time(schedule.get("source_jobs", "08:00"))
    scheduler.add_job(_run_source, CronTrigger(hour=h, minute=m),
                      id="source_jobs", name="Job Sourcing")

    # Stage 2: Enrich contacts
    h, m = _parse_time(schedule.get("enrich_contacts", "08:30"))
    scheduler.add_job(_run_enrich, CronTrigger(hour=h, minute=m),
                      id="enrich_contacts", name="Contact Enrichment")

    # Stage 3: Generate messages
    h, m = _parse_time(schedule.get("generate_messages", "09:00"))
    scheduler.add_job(_run_generate, CronTrigger(hour=h, minute=m),
                      id="generate_messages", name="Message Generation")

    # Stage 4: Send outreach
    h, m = _parse_time(schedule.get("send_outreach", "10:00"))
    scheduler.add_job(_run_send, CronTrigger(hour=h, minute=m),
                      id="send_outreach", name="Send Outreach")

    # Stage 5: Check replies
    h, m = _parse_time(schedule.get("check_replies", "17:00"))
    scheduler.add_job(_run_check_replies, CronTrigger(hour=h, minute=m),
                      id="check_replies", name="Check Replies")

    # Stage 8: Daily digest
    h, m = _parse_time(schedule.get("daily_digest", "20:00"))
    scheduler.add_job(_run_digest, CronTrigger(hour=h, minute=m),
                      id="daily_digest", name="Daily Digest")

    scheduler.start()
    logger.info("Scheduler started with all cron jobs")

    # Log the schedule
    for job in scheduler.get_jobs():
        logger.info(f"  [{job.id}] {job.name} — next run: {job.next_run_time}")


def stop_scheduler():
    """Gracefully shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")


def get_scheduler_status() -> list[dict]:
    """Get status of all scheduled jobs for dashboard display."""
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": str(job.next_run_time) if job.next_run_time else "Not scheduled",
            "trigger": str(job.trigger),
        })
    return jobs
