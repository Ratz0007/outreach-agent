"""LinkedIn outreach — manual/copy-paste mode with quota tracking.

LinkedIn's API requires partner-level access for invitations/messaging,
so this module operates in MANUAL mode:
  1. Generates ready-to-send messages in the dashboard
  2. You copy-paste them into LinkedIn
  3. Mark as sent in the dashboard → updates DB + quota tracking

Quota tracking is enforced even in manual mode to keep you within safe limits.
"""

import logging
from datetime import datetime, date, timedelta

from sqlalchemy import func

from src.config import AgentConfig
from src.db.models import OutreachLog, PeopleMapper
from src.db.session import get_session

logger = logging.getLogger(__name__)


# ── Quota Tracking ─────────────────────────────────────────────────

def get_daily_linkedin_sends(for_date: date | None = None) -> int:
    """Count LinkedIn invites/DMs sent today."""
    session = get_session()
    try:
        target_date = for_date or date.today()
        start = datetime.combine(target_date, datetime.min.time())
        end = datetime.combine(target_date, datetime.max.time())

        count = session.query(func.count(OutreachLog.id)).filter(
            OutreachLog.channel.in_(["linkedin_dm", "linkedin_invite"]),
            OutreachLog.status == "sent",
            OutreachLog.sent_at.between(start, end),
        ).scalar() or 0
        return count
    finally:
        session.close()


def get_weekly_linkedin_sends() -> int:
    """Count LinkedIn invites sent this week (Mon-Sun)."""
    session = get_session()
    try:
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        start = datetime.combine(monday, datetime.min.time())

        count = session.query(func.count(OutreachLog.id)).filter(
            OutreachLog.channel.in_(["linkedin_dm", "linkedin_invite"]),
            OutreachLog.status == "sent",
            OutreachLog.sent_at >= start,
        ).scalar() or 0
        return count
    finally:
        session.close()


def can_send_linkedin_today() -> tuple[bool, str]:
    """Check if we can send another LinkedIn message today.
    Returns (allowed, reason)."""
    daily = get_daily_linkedin_sends()
    weekly = get_weekly_linkedin_sends()

    if daily >= AgentConfig.daily_linkedin_invite_limit:
        return False, f"Daily limit reached ({daily}/{AgentConfig.daily_linkedin_invite_limit})"

    if weekly >= AgentConfig.weekly_linkedin_invite_limit:
        return False, f"Weekly limit reached ({weekly}/{AgentConfig.weekly_linkedin_invite_limit})"

    return True, f"OK ({daily}/{AgentConfig.daily_linkedin_invite_limit} today, {weekly}/{AgentConfig.weekly_linkedin_invite_limit} this week)"


def get_linkedin_quota_status() -> dict:
    """Full quota status for dashboard display."""
    daily = get_daily_linkedin_sends()
    weekly = get_weekly_linkedin_sends()

    return {
        "daily_sent": daily,
        "daily_limit": AgentConfig.daily_linkedin_invite_limit,
        "daily_remaining": max(0, AgentConfig.daily_linkedin_invite_limit - daily),
        "weekly_sent": weekly,
        "weekly_limit": AgentConfig.weekly_linkedin_invite_limit,
        "weekly_remaining": max(0, AgentConfig.weekly_linkedin_invite_limit - weekly),
        "can_send": daily < AgentConfig.daily_linkedin_invite_limit and weekly < AgentConfig.weekly_linkedin_invite_limit,
    }


# ── Manual Send Workflow ───────────────────────────────────────────

def get_linkedin_drafts() -> list[dict]:
    """Get all approved LinkedIn messages ready for manual copy-paste."""
    session = get_session()
    try:
        drafts = session.query(OutreachLog).filter(
            OutreachLog.channel.in_(["linkedin_dm", "linkedin_invite"]),
            OutreachLog.status == "approved",
        ).all()

        results = []
        for d in drafts:
            person = session.get(PeopleMapper, d.person_id)
            results.append({
                "outreach_id": d.id,
                "person_name": person.name if person else "Unknown",
                "person_title": person.title if person else "",
                "company": person.company if person else "",
                "linkedin_url": person.linkedin_url if person else "",
                "variant": d.variant,
                "style": d.style,
                "message": d.message_body,
                "channel": d.channel,
            })
        return results
    finally:
        session.close()


def mark_linkedin_sent(outreach_id: int) -> bool:
    """Mark a LinkedIn message as sent (after manual copy-paste).
    Enforces quota limits. Returns True if marked, False if quota exceeded."""
    session = get_session()
    try:
        # Check quota first
        can_send, reason = can_send_linkedin_today()
        if not can_send:
            logger.warning(f"Cannot mark as sent: {reason}")
            return False

        outreach = session.get(OutreachLog, outreach_id)
        if not outreach:
            logger.error(f"Outreach {outreach_id} not found")
            return False

        if outreach.status != "approved":
            logger.warning(f"Outreach {outreach_id} is not approved (status: {outreach.status})")
            return False

        # Mark sent
        now = datetime.utcnow()
        outreach.status = "sent"
        outreach.sent_at = now
        outreach.follow_up_date = (now + timedelta(days=AgentConfig.follow_up_days)).date()

        # Update contact
        person = session.get(PeopleMapper, outreach.person_id)
        if person:
            person.next_action = "contacted"
            person.last_contact_date = now.date()
            person.next_follow_up = outreach.follow_up_date

        session.commit()
        logger.info(f"LinkedIn message {outreach_id} marked as sent")
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Error marking LinkedIn sent: {e}")
        return False
    finally:
        session.close()


def get_pending_linkedin_count() -> int:
    """Count LinkedIn messages in approved state awaiting manual send."""
    session = get_session()
    try:
        return session.query(func.count(OutreachLog.id)).filter(
            OutreachLog.channel.in_(["linkedin_dm", "linkedin_invite"]),
            OutreachLog.status == "approved",
        ).scalar() or 0
    finally:
        session.close()
