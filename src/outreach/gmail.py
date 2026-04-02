"""Gmail send + thread tracking — Stage 4 & 5.

Uses Gmail API via OAuth2 to:
  - Send approved email outreach
  - Track threads for reply detection
  - Check for replies to outreach emails

Requires Google Cloud Console setup:
  1. Enable Gmail API
  2. Create OAuth2 credentials (Desktop app)
  3. Set GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET in .env
  4. Run `python main.py gmail-auth` to get refresh token
"""

import base64
import json
import logging
from datetime import datetime, timedelta
from email.mime.text import MIMEText

from sqlalchemy import func

from src.config import AgentConfig, Secrets
from src.db.models import OutreachLog, PeopleMapper, JobShortlist
from src.db.session import get_session

logger = logging.getLogger(__name__)

# ── Gmail API Client ──────────────────────────────────────────────

_gmail_service = None


def _get_gmail_service():
    """Get authenticated Gmail API service. Returns None if not configured."""
    global _gmail_service
    if _gmail_service:
        return _gmail_service

    if not Secrets.GMAIL_CLIENT_ID or not Secrets.GMAIL_REFRESH_TOKEN:
        logger.warning("Gmail not configured. Set GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN in .env")
        return None

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None,
            refresh_token=Secrets.GMAIL_REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=Secrets.GMAIL_CLIENT_ID,
            client_secret=Secrets.GMAIL_CLIENT_SECRET,
            scopes=["https://www.googleapis.com/auth/gmail.send",
                     "https://www.googleapis.com/auth/gmail.readonly"],
        )
        _gmail_service = build("gmail", "v1", credentials=creds)
        logger.info("Gmail API service initialized")
        return _gmail_service
    except ImportError:
        logger.error("google-api-python-client not installed. Run: pip install google-api-python-client google-auth")
        return None
    except Exception as e:
        logger.error(f"Failed to init Gmail service: {e}")
        return None


# ── Email Sending ──────────────────────────────────────────────────

def _create_email_message(to: str, subject: str, body: str, from_email: str = None) -> dict:
    """Create a Gmail API-compatible message."""
    msg = MIMEText(body)
    msg["to"] = to
    msg["from"] = from_email or AgentConfig.email
    msg["subject"] = subject

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    return {"raw": raw}


def _build_subject(contact_name: str, company: str, role: str) -> str:
    """Build a natural email subject line."""
    # Vary subjects to avoid spam filters
    subjects = [
        f"Quick question about {role} at {company}",
        f"Connecting re: {role} opportunity",
        f"{company} - {role} inquiry",
        f"Hi {contact_name.split()[0]} - reaching out about {company}",
    ]
    # Pick based on hash of name for consistency (same contact = same subject)
    idx = hash(contact_name + company) % len(subjects)
    return subjects[idx]


def send_single_email(outreach_id: int) -> bool:
    """Send a single approved email. Returns True on success."""
    service = _get_gmail_service()
    session = get_session()

    try:
        outreach = session.get(OutreachLog, outreach_id)
        if not outreach:
            logger.error(f"Outreach {outreach_id} not found")
            return False

        if outreach.status != "approved":
            logger.warning(f"Outreach {outreach_id} not approved (status: {outreach.status})")
            return False

        if outreach.channel != "email":
            logger.warning(f"Outreach {outreach_id} is not email channel ({outreach.channel})")
            return False

        person = session.get(PeopleMapper, outreach.person_id)
        if not person or not person.email:
            logger.error(f"No email for contact on outreach {outreach_id}")
            return False

        job = session.get(JobShortlist, outreach.job_id)
        subject = _build_subject(person.name, person.company or "", job.role if job else "")

        if service:
            # Real send via Gmail API
            message = _create_email_message(
                to=person.email,
                subject=subject,
                body=outreach.message_body,
            )
            try:
                result = service.users().messages().send(userId="me", body=message).execute()
                thread_id = result.get("threadId", "")
                logger.info(f"Email sent to {person.email}, threadId={thread_id}")
            except Exception as e:
                logger.error(f"Gmail API send failed: {e}")
                return False
        else:
            # No Gmail configured — mark as sent anyway (for testing)
            logger.info(f"[DRY RUN] Would send email to {person.email}: {subject}")

        # Update outreach record
        now = datetime.utcnow()
        outreach.status = "sent"
        outreach.sent_at = now
        outreach.follow_up_date = (now + timedelta(days=AgentConfig.follow_up_days)).date()

        # Update contact
        if person:
            person.next_action = "contacted"
            person.last_contact_date = now.date()
            person.next_follow_up = outreach.follow_up_date

        session.commit()
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Error sending email for outreach {outreach_id}: {e}")
        return False
    finally:
        session.close()


def send_approved_emails() -> int:
    """Send all approved email drafts. Returns count sent.
    Respects daily message limit."""
    session = get_session()
    try:
        # Check daily limit
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0)
        today_sent = session.query(func.count(OutreachLog.id)).filter(
            OutreachLog.channel == "email",
            OutreachLog.status == "sent",
            OutreachLog.sent_at >= today_start,
        ).scalar() or 0

        remaining = AgentConfig.daily_message_limit - today_sent
        if remaining <= 0:
            logger.info("Daily email limit reached.")
            return 0

        # Get approved email drafts
        approved = session.query(OutreachLog).filter(
            OutreachLog.channel == "email",
            OutreachLog.status == "approved",
        ).limit(remaining).all()

        if not approved:
            logger.info("No approved email drafts to send.")
            return 0

        # Enforce: max 1 per company per day
        companies_contacted_today = set()
        sent_count = 0

        for outreach in approved:
            person = session.get(PeopleMapper, outreach.person_id)
            company = (person.company or "").lower() if person else ""

            if company in companies_contacted_today:
                logger.info(f"Skipping {person.name if person else '?'} — already contacted someone at {company} today")
                continue

            session.close()  # Close before sending to avoid long-held locks
            session = get_session()

            if send_single_email(outreach.id):
                sent_count += 1
                if company:
                    companies_contacted_today.add(company)

        return sent_count
    finally:
        session.close()


# ── Reply Checking ─────────────────────────────────────────────────

def check_gmail_replies() -> list[dict]:
    """Check Gmail for replies to outreach threads.
    Returns list of {outreach_id, person_id, job_id, reply_snippet}."""
    service = _get_gmail_service()
    if not service:
        logger.info("Gmail not configured — skipping reply check")
        return []

    session = get_session()
    replies_found = []

    try:
        # Get sent outreach emails that haven't been replied to
        sent_emails = session.query(OutreachLog).filter(
            OutreachLog.channel == "email",
            OutreachLog.status == "sent",
            OutreachLog.sent_at.isnot(None),
        ).all()

        if not sent_emails:
            return []

        # Check inbox for replies (search for emails from contacts)
        for outreach in sent_emails:
            person = session.get(PeopleMapper, outreach.person_id)
            if not person or not person.email:
                continue

            try:
                # Search for replies from this contact
                query = f"from:{person.email} after:{outreach.sent_at.strftime('%Y/%m/%d')}"
                results = service.users().messages().list(
                    userId="me", q=query, maxResults=5
                ).execute()

                messages = results.get("messages", [])
                if messages:
                    # Get the first reply snippet
                    msg = service.users().messages().get(
                        userId="me", id=messages[0]["id"], format="metadata"
                    ).execute()

                    snippet = msg.get("snippet", "")
                    replies_found.append({
                        "outreach_id": outreach.id,
                        "person_id": person.id,
                        "job_id": outreach.job_id,
                        "reply_snippet": snippet[:200],
                        "contact_name": person.name,
                        "contact_email": person.email,
                    })
                    logger.info(f"Reply found from {person.email}: {snippet[:50]}...")
            except Exception as e:
                logger.error(f"Error checking replies from {person.email}: {e}")
                continue

        return replies_found
    finally:
        session.close()


# ── Gmail Auth Helper ──────────────────────────────────────────────

def run_gmail_auth_flow():
    """Interactive OAuth2 flow to get refresh token.
    Run this once: `python main.py gmail-auth`"""
    if not Secrets.GMAIL_CLIENT_ID or not Secrets.GMAIL_CLIENT_SECRET:
        print("\n[ERROR] Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in .env first.")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create a project (or select existing)")
        print("3. Enable Gmail API: APIs & Services > Library > Gmail API > Enable")
        print("4. Create OAuth credentials: APIs & Services > Credentials > Create > OAuth 2.0 Client ID")
        print("   - Application type: Desktop app")
        print("   - Download JSON, copy client_id and client_secret to .env")
        print("5. Add test user: OAuth consent screen > Test users > Add your Gmail")
        return

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow

        client_config = {
            "installed": {
                "client_id": Secrets.GMAIL_CLIENT_ID,
                "client_secret": Secrets.GMAIL_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }

        flow = InstalledAppFlow.from_client_config(
            client_config,
            scopes=[
                "https://www.googleapis.com/auth/gmail.send",
                "https://www.googleapis.com/auth/gmail.readonly",
            ],
        )
        creds = flow.run_local_server(port=0)

        print("\n=== Gmail OAuth2 Setup Complete ===")
        print(f"\nAdd this to your .env file:")
        print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
        print(f"\nToken will auto-refresh. You're all set!")

    except ImportError:
        print("\n[ERROR] Install required packages:")
        print("  pip install google-auth-oauthlib google-api-python-client")
    except Exception as e:
        print(f"\n[ERROR] Auth flow failed: {e}")
