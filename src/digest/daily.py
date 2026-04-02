"""Daily KPI email — Stage 8.

Compiles stats from today's pipeline run and sends a digest email
to ratinsharma99@gmail.com via Gmail API.
"""

import logging
from datetime import datetime, date, timedelta

from sqlalchemy import func

from src.config import AgentConfig, Secrets
from src.db.models import (
    JobShortlist, PeopleMapper, OutreachLog, ResponseTracker, CVVersion
)
from src.db.session import get_session
from src.outreach.linkedin import get_linkedin_quota_status
from src.testing.ab_engine import get_variant_performance
from src.tracking.response_handler import get_follow_ups_due

logger = logging.getLogger(__name__)


def _compile_stats() -> dict:
    """Gather all KPIs for today's digest."""
    session = get_session()
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    tomorrow_due = today + timedelta(days=1)

    try:
        # Jobs sourced today
        jobs_today = session.query(func.count(JobShortlist.id)).filter(
            JobShortlist.created_at >= today_start
        ).scalar() or 0

        # Total jobs
        total_jobs = session.query(func.count(JobShortlist.id)).scalar() or 0

        # Contacts enriched today
        contacts_today = session.query(func.count(PeopleMapper.id)).filter(
            PeopleMapper.created_at >= today_start
        ).scalar() or 0

        # Messages drafted today
        drafts_today = session.query(func.count(OutreachLog.id)).filter(
            OutreachLog.created_at >= today_start,
            OutreachLog.status == "draft",
        ).scalar() or 0

        # Messages sent today
        sent_today = session.query(func.count(OutreachLog.id)).filter(
            OutreachLog.sent_at >= today_start,
            OutreachLog.status.in_(["sent", "replied"]),
        ).scalar() or 0

        # Total sent ever
        total_sent = session.query(func.count(OutreachLog.id)).filter(
            OutreachLog.status.in_(["sent", "replied"]),
        ).scalar() or 0

        # Replies received today
        replies_today = session.query(func.count(ResponseTracker.id)).filter(
            ResponseTracker.response_date >= today_start,
        ).scalar() or 0

        # Referrals today
        referrals_today = session.query(func.count(ResponseTracker.id)).filter(
            ResponseTracker.response_date >= today_start,
            ResponseTracker.response_type == "referral",
        ).scalar() or 0

        # Total referrals
        total_referrals = session.query(func.count(ResponseTracker.id)).filter(
            ResponseTracker.response_type == "referral",
        ).scalar() or 0

        # Applications submitted (status = applied)
        apps_today = session.query(func.count(JobShortlist.id)).filter(
            JobShortlist.status == "applied",
            JobShortlist.updated_at >= today_start,
        ).scalar() or 0

        # Follow-ups due tomorrow
        follow_ups_tomorrow = len(get_follow_ups_due(tomorrow_due))

        # Pending drafts
        pending_drafts = session.query(func.count(OutreachLog.id)).filter(
            OutreachLog.status == "draft",
        ).scalar() or 0

        # Contacts to message tomorrow
        to_contact = session.query(func.count(PeopleMapper.id)).filter(
            PeopleMapper.next_action == "to_contact",
        ).scalar() or 0

        # LinkedIn quota
        linkedin_quota = get_linkedin_quota_status()

        # Tier 1 flagged roles
        tier1_roles = session.query(JobShortlist).filter(
            JobShortlist.is_tier1 == True,
            JobShortlist.status == "shortlisted",
        ).all()

        # Variant performance (top 3)
        variant_stats = get_variant_performance()
        top_variants = [
            {
                "id": s.variant_id,
                "style": s.style,
                "reply_rate": s.reply_rate,
                "sends": s.sends,
            }
            for s in variant_stats[:3] if s.sends > 0
        ]

        return {
            "date": today.strftime("%A, %B %d, %Y"),
            "jobs_today": jobs_today,
            "total_jobs": total_jobs,
            "contacts_today": contacts_today,
            "drafts_today": drafts_today,
            "sent_today": sent_today,
            "total_sent": total_sent,
            "replies_today": replies_today,
            "referrals_today": referrals_today,
            "total_referrals": total_referrals,
            "apps_today": apps_today,
            "follow_ups_tomorrow": follow_ups_tomorrow,
            "pending_drafts": pending_drafts,
            "to_contact": to_contact,
            "linkedin_daily": linkedin_quota["daily_sent"],
            "linkedin_daily_limit": linkedin_quota["daily_limit"],
            "linkedin_weekly": linkedin_quota["weekly_sent"],
            "linkedin_weekly_limit": linkedin_quota["weekly_limit"],
            "top_variants": top_variants,
            "tier1_roles": [
                {"company": j.company, "role": j.role, "link": j.application_link or "N/A"}
                for j in tier1_roles[:5]
            ],
        }
    finally:
        session.close()


def _format_digest(stats: dict) -> str:
    """Format the digest email body."""
    lines = [
        f"Daily Summary - {stats['date']}",
        "=" * 48,
        "",
        f"Jobs sourced today:        {stats['jobs_today']}",
        f"Contacts enriched:         {stats['contacts_today']}",
        f"Messages drafted:          {stats['drafts_today']}",
        f"Messages sent:             {stats['sent_today']} / Target: 15-20",
        f"LinkedIn invites used:     {stats['linkedin_daily']}/{stats['linkedin_daily_limit']} today, "
        f"{stats['linkedin_weekly']}/{stats['linkedin_weekly_limit']} this week",
        f"Replies received:          {stats['replies_today']}",
        f"Referrals secured:         {stats['referrals_today']} (total: {stats['total_referrals']})",
        f"Applications submitted:    {stats['apps_today']}",
        f"Follow-ups due tomorrow:   {stats['follow_ups_tomorrow']}",
        "",
    ]

    # Variant performance
    if stats["top_variants"]:
        lines.append("Variant Performance (top 3):")
        for v in stats["top_variants"]:
            lines.append(f"  {v['id']} ({v['style']}): {v['reply_rate']}% reply rate (n={v['sends']} sends)")
        lines.append("")

    # Tier 1 roles
    if stats["tier1_roles"]:
        lines.append("Flagged Tier 1 roles (manual apply):")
        for r in stats["tier1_roles"]:
            lines.append(f"  - {r['company']} - {r['role']} - {r['link']}")
        lines.append("")

    # Tomorrow's plan
    lines.extend([
        "Tomorrow's plan:",
        f"  - {stats['to_contact']} new contacts to message",
        f"  - {stats['follow_ups_tomorrow']} follow-ups due",
        f"  - {stats['pending_drafts']} drafts awaiting review",
        "",
        "---",
        f"Total pipeline: {stats['total_jobs']} jobs | {stats['total_sent']} sent | {stats['total_referrals']} referrals",
    ])

    return "\n".join(lines)


def send_daily_digest():
    """Compile stats and send daily digest email."""
    stats = _compile_stats()
    body = _format_digest(stats)
    subject = f"Job Search Digest - {stats['date']}"

    logger.info(f"Daily digest compiled:\n{body}")

    # Try to send via Gmail
    try:
        from src.outreach.gmail import _get_gmail_service, _create_email_message

        service = _get_gmail_service()
        if service:
            message = _create_email_message(
                to=AgentConfig.email,
                subject=subject,
                body=body,
            )
            service.users().messages().send(userId="me", body=message).execute()
            logger.info(f"Daily digest sent to {AgentConfig.email}")
        else:
            logger.info("Gmail not configured — digest printed to console only")
            print(body)
    except Exception as e:
        logger.error(f"Failed to send digest email: {e}")
        print(body)
