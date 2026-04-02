"""Response handling — Stage 5.

Check for replies, classify them, and route next actions:
  - Referral offered → pause direct app, apply through referral
  - Interest/advice → apply with tailored CV, thank them
  - Connected (no reply) → soft ask in 2 days
  - No reply after 7 days → send ONE follow-up (max 1)
  - No reply after 14 days → apply directly, archive contact
  - Declined / not a fit → thank, archive, move on
"""

import logging
from datetime import datetime, date, timedelta

from src.config import AgentConfig
from src.db.models import OutreachLog, PeopleMapper, JobShortlist, ResponseTracker
from src.db.session import get_session
from src.outreach.gmail import check_gmail_replies

logger = logging.getLogger(__name__)


# ── Response Classification ────────────────────────────────────────

REFERRAL_KEYWORDS = [
    "refer", "referral", "introduce", "introduction", "put you in touch",
    "connect you with", "pass your resume", "send your cv", "forward",
    "recommend you", "happy to help", "internal",
]

INTEREST_KEYWORDS = [
    "interesting", "impressed", "great background", "like your experience",
    "let's chat", "schedule a call", "would love to talk", "send me your cv",
    "apply", "link to apply", "open role",
]

DECLINE_KEYWORDS = [
    "not hiring", "no openings", "position filled", "not a fit",
    "unfortunately", "moved forward with", "can't help", "not the right time",
    "no longer available", "role has been filled",
]


def _classify_reply(snippet: str) -> str:
    """Classify a reply into response_type based on content.
    Returns: referral, interest, not_fit, or connected."""
    text = snippet.lower()

    for kw in REFERRAL_KEYWORDS:
        if kw in text:
            return "referral"

    for kw in INTEREST_KEYWORDS:
        if kw in text:
            return "interest"

    for kw in DECLINE_KEYWORDS:
        if kw in text:
            return "not_fit"

    # Default: they replied, so at minimum they connected
    return "connected"


def _determine_action(response_type: str) -> str:
    """Determine the action to take based on response type."""
    actions = {
        "referral": "referral_to_apply",
        "interest": "apply_with_cv",
        "connected": "follow_up_soft",
        "not_fit": "archived",
        "no_reply": "follow_up_or_archive",
    }
    return actions.get(response_type, "review_manually")


# ── Main Check & Classify ─────────────────────────────────────────

def check_and_classify_replies() -> int:
    """Check Gmail for replies, classify them, update statuses.
    Returns count of replies processed."""
    session = get_session()
    processed = 0

    try:
        # Step 1: Check Gmail for new replies
        gmail_replies = check_gmail_replies()

        for reply in gmail_replies:
            # Check if we already logged this response
            existing = session.query(ResponseTracker).filter(
                ResponseTracker.outreach_id == reply["outreach_id"],
            ).first()
            if existing:
                continue

            # Classify
            response_type = _classify_reply(reply["reply_snippet"])
            action = _determine_action(response_type)

            # Create response record
            response = ResponseTracker(
                outreach_id=reply["outreach_id"],
                person_id=reply["person_id"],
                job_id=reply["job_id"],
                response_type=response_type,
                response_date=datetime.utcnow(),
                action_taken=action,
                notes=f"Auto-classified. Snippet: {reply['reply_snippet'][:100]}",
            )
            session.add(response)

            # Update outreach status
            outreach = session.get(OutreachLog, reply["outreach_id"])
            if outreach:
                outreach.status = "replied"

            # Update contact next_action
            person = session.get(PeopleMapper, reply["person_id"])
            if person:
                if response_type in ("referral", "interest"):
                    person.next_action = "replied"
                elif response_type == "not_fit":
                    person.next_action = "archived"
                else:
                    person.next_action = "replied"

            # Update job status if referral
            if response_type == "referral":
                job = session.get(JobShortlist, reply["job_id"])
                if job and job.status == "contacted":
                    job.status = "follow_up"

            processed += 1
            logger.info(
                f"Reply from {reply['contact_name']}: {response_type} -> {action}"
            )

        # Step 2: Check for follow-ups due (no reply after follow_up_days)
        processed += _process_follow_ups(session)

        # Step 3: Check for stale contacts (no reply after 14 days)
        processed += _process_stale_contacts(session)

        session.commit()
        return processed

    except Exception as e:
        session.rollback()
        logger.error(f"Error in response handling: {e}")
        raise
    finally:
        session.close()


def _process_follow_ups(session) -> int:
    """Handle contacts whose follow-up date has passed with no reply."""
    today = date.today()
    count = 0

    # Find sent outreach with follow_up_date <= today and no reply
    due_follow_ups = session.query(OutreachLog).filter(
        OutreachLog.status == "sent",
        OutreachLog.follow_up_date <= today,
        OutreachLog.follow_up_count < AgentConfig.max_follow_ups,
    ).all()

    for outreach in due_follow_ups:
        # Check if already has a response
        has_response = session.query(ResponseTracker).filter(
            ResponseTracker.outreach_id == outreach.id,
        ).first()
        if has_response:
            continue

        person = session.get(PeopleMapper, outreach.person_id)
        if not person:
            continue

        # Mark for follow-up
        person.next_action = "follow_up"
        outreach.status = "no_reply"

        # Log a no_reply response
        response = ResponseTracker(
            outreach_id=outreach.id,
            person_id=person.id,
            job_id=outreach.job_id,
            response_type="no_reply",
            response_date=datetime.utcnow(),
            action_taken="follow_up_due",
            notes=f"No reply after {AgentConfig.follow_up_days} days. Follow-up recommended.",
        )
        session.add(response)
        count += 1
        logger.info(f"Follow-up due for {person.name} @ {person.company}")

    return count


def _process_stale_contacts(session) -> int:
    """Handle contacts with no reply after 14 days — archive and apply direct."""
    today = date.today()
    stale_date = today - timedelta(days=14)
    count = 0

    # Find contacts who were followed up but still no reply
    stale = session.query(OutreachLog).filter(
        OutreachLog.status == "no_reply",
        OutreachLog.follow_up_count >= AgentConfig.max_follow_ups,
        OutreachLog.sent_at <= datetime.combine(stale_date, datetime.min.time()),
    ).all()

    for outreach in stale:
        person = session.get(PeopleMapper, outreach.person_id)
        if not person or person.next_action == "archived":
            continue

        person.next_action = "archived"

        # Update job to apply directly
        job = session.get(JobShortlist, outreach.job_id)
        if job and job.status in ("contacted", "follow_up"):
            job.status = "applied"
            logger.info(f"Archiving {person.name} — no reply after 14 days. Apply directly to {job.company}.")

        count += 1

    return count


# ── Dashboard Helpers ──────────────────────────────────────────────

def get_follow_ups_due(for_date: date | None = None) -> list[dict]:
    """Get contacts whose follow-up is due on a given date."""
    target = for_date or date.today()
    session = get_session()
    try:
        contacts = session.query(PeopleMapper).filter(
            PeopleMapper.next_action == "follow_up",
            PeopleMapper.next_follow_up <= target,
        ).all()

        results = []
        for c in contacts:
            job = session.get(JobShortlist, c.job_id)
            results.append({
                "person_id": c.id,
                "name": c.name,
                "company": c.company,
                "title": c.title,
                "job_role": job.role if job else "",
                "last_contact": str(c.last_contact_date) if c.last_contact_date else "Never",
                "follow_up_date": str(c.next_follow_up),
            })
        return results
    finally:
        session.close()


def get_response_summary() -> dict:
    """Get summary of all responses for dashboard."""
    session = get_session()
    try:
        from sqlalchemy import func as sqlfunc

        total = session.query(sqlfunc.count(ResponseTracker.id)).scalar() or 0
        referrals = session.query(sqlfunc.count(ResponseTracker.id)).filter(
            ResponseTracker.response_type == "referral"
        ).scalar() or 0
        interest = session.query(sqlfunc.count(ResponseTracker.id)).filter(
            ResponseTracker.response_type == "interest"
        ).scalar() or 0
        no_reply = session.query(sqlfunc.count(ResponseTracker.id)).filter(
            ResponseTracker.response_type == "no_reply"
        ).scalar() or 0
        declined = session.query(sqlfunc.count(ResponseTracker.id)).filter(
            ResponseTracker.response_type == "not_fit"
        ).scalar() or 0

        return {
            "total_responses": total,
            "referrals": referrals,
            "interest": interest,
            "no_reply": no_reply,
            "declined": declined,
        }
    finally:
        session.close()


def manually_classify_response(
    outreach_id: int,
    response_type: str,
    action_taken: str,
    notes: str = "",
) -> bool:
    """Manually classify a response from the dashboard.
    For when auto-classification needs correction."""
    session = get_session()
    try:
        outreach = session.get(OutreachLog, outreach_id)
        if not outreach:
            return False

        # Update or create response
        existing = session.query(ResponseTracker).filter(
            ResponseTracker.outreach_id == outreach_id,
        ).first()

        if existing:
            existing.response_type = response_type
            existing.action_taken = action_taken
            existing.notes = notes
        else:
            response = ResponseTracker(
                outreach_id=outreach_id,
                person_id=outreach.person_id,
                job_id=outreach.job_id,
                response_type=response_type,
                response_date=datetime.utcnow(),
                action_taken=action_taken,
                notes=notes,
            )
            session.add(response)

        # Update outreach status
        outreach.status = "replied"

        # Update contact
        person = session.get(PeopleMapper, outreach.person_id)
        if person:
            if response_type in ("not_fit", "no_reply"):
                person.next_action = "archived"
            else:
                person.next_action = "replied"

        session.commit()
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Error manually classifying response: {e}")
        return False
    finally:
        session.close()
