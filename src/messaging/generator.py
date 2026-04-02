"""Claude API message generation — Stage 3.

For each contact with next_action="to_contact":
1. Randomly assign a variant (V1-V10) using current weights
2. Call Claude API to personalise the message
3. Store as draft in outreach_log

When ANTHROPIC_API_KEY is not set, generates messages using template filling only.
"""

import json
import logging
import random
from datetime import datetime

from src.config import AgentConfig, Secrets, get_profile_summary
from src.db.models import JobShortlist, PeopleMapper, OutreachLog
from src.db.session import get_session
from src.messaging.variants import VARIANT_TEMPLATES, get_all_active_variant_ids

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a message personalisation assistant for Ratin Sharma, a Senior Account Executive
with 7+ years of sales experience (4+ in SaaS). He is job hunting for AE/Sales Manager roles
at SaaS startups and mid-market companies in Europe.

Your job: take a message template and personalise it using the contact's context and the job description.
Make it sound like a real human wrote it — natural, warm, and specific. Do NOT just fill in blanks.

Rules:
- Keep it under 100 words
- Reference something specific from the JD or company context
- Sound genuine, not salesy or generic
- Use the contact's actual title/role context
- Keep Ratin's real metrics (150% quota, $540K ARR, $750K+ closed, etc.)
- If an optional token (like {Mutual} or {Event}) has no data, gracefully skip it or rephrase
- Return ONLY the final message text, nothing else"""


def _select_variant(active_variants: dict) -> str:
    """Select a variant using weighted random based on config weights."""
    variant_ids = []
    weights = []
    for vid, vconfig in active_variants.items():
        if vconfig.get("active", True):
            variant_ids.append(vid)
            weights.append(vconfig.get("weight", 0.1))

    if not variant_ids:
        return "V1"

    return random.choices(variant_ids, weights=weights, k=1)[0]


def _build_claude_prompt(
    variant_template: dict,
    contact_name: str,
    contact_title: str,
    contact_company: str,
    contact_relationship: str,
    job_role: str,
    job_description: str,
    job_keywords: list[str],
) -> str:
    """Build the user prompt for Claude API."""
    return f"""Personalise this outreach message for Ratin Sharma's job search.

**Template (variant {variant_template.get('name', 'Unknown')}, style: {variant_template['style']}):**
{variant_template['template']}

**Contact:**
- Name: {contact_name}
- Title: {contact_title}
- Company: {contact_company}
- Relationship: {contact_relationship}

**Job:**
- Role: {job_role}
- JD Keywords: {', '.join(job_keywords[:15])}
- Description excerpt: {job_description[:500]}

**Ratin's Profile Summary:**
{get_profile_summary()[:400]}

Personalise the template naturally. Use the contact's role and company context.
Make it sound like a real human wrote it. Keep under 100 words. Return ONLY the final message."""


def _generate_with_claude(prompt: str) -> str | None:
    """Call Claude API to generate a personalised message."""
    api_key = Secrets.ANTHROPIC_API_KEY
    if not api_key:
        return None

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return None


def _generate_fallback(
    variant_template: dict,
    contact_name: str,
    contact_company: str,
    job_role: str,
    job_keywords: list[str],
) -> str:
    """Generate message by simple template filling when Claude API is unavailable."""
    template = variant_template["template"]

    # Fill tokens with available data
    replacements = {
        "{Name}": contact_name,
        "{Company}": contact_company,
        "{Role}": job_role,
        "{Topic}": job_keywords[0] if job_keywords else "your industry",
        "{Achievement}": "recent growth",
        "{Event}": "your latest milestone",
        "{Mutual}": "a mutual connection",
    }

    message = template
    for token, value in replacements.items():
        message = message.replace(token, value)

    return message


def generate_messages() -> int:
    """Generate personalised outreach drafts for contacts needing outreach.
    Returns count of drafts created."""
    session = get_session()
    draft_count = 0

    try:
        # Find contacts needing outreach: next_action="to_contact", no existing drafts
        contacts = session.query(PeopleMapper).filter(
            PeopleMapper.next_action == "to_contact"
        ).all()

        if not contacts:
            logger.info("No contacts need message generation.")
            return 0

        # Check daily draft limit
        today_drafts = session.query(OutreachLog).filter(
            OutreachLog.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
        ).count()

        remaining_limit = AgentConfig.daily_message_limit - today_drafts
        if remaining_limit <= 0:
            logger.info("Daily draft limit reached.")
            return 0

        active_variants = AgentConfig.variants

        for contact in contacts[:remaining_limit]:
            # Skip if already has a draft or sent message
            existing = session.query(OutreachLog).filter(
                OutreachLog.person_id == contact.id,
                OutreachLog.status.in_(["draft", "approved", "sent"]),
            ).first()
            if existing:
                continue

            # Get job data
            job = session.get(JobShortlist, contact.job_id)
            if not job:
                continue

            # Select variant
            variant_id = contact.assigned_variant or _select_variant(active_variants)
            variant_template = VARIANT_TEMPLATES.get(variant_id)
            if not variant_template:
                variant_id = "V4"
                variant_template = VARIANT_TEMPLATES["V4"]

            # Update contact with assigned variant
            if not contact.assigned_variant:
                contact.assigned_variant = variant_id

            # Parse job keywords
            try:
                keywords = json.loads(job.keywords) if job.keywords else []
            except (json.JSONDecodeError, TypeError):
                keywords = []

            # Build prompt and generate
            prompt = _build_claude_prompt(
                variant_template=variant_template,
                contact_name=contact.name,
                contact_title=contact.title or "",
                contact_company=contact.company or job.company,
                contact_relationship=contact.relationship_type or "unknown",
                job_role=job.role,
                job_description=job.description or "",
                job_keywords=keywords,
            )

            # Try Claude API first, fall back to template filling
            message = _generate_with_claude(prompt)
            if not message:
                message = _generate_fallback(
                    variant_template=variant_template,
                    contact_name=contact.name,
                    contact_company=contact.company or job.company,
                    job_role=job.role,
                    job_keywords=keywords,
                )

            # Determine channel
            if contact.email:
                channel = "email"
            elif contact.linkedin_url:
                channel = "linkedin_dm"
            else:
                channel = "email"

            # Create outreach log entry as draft
            outreach = OutreachLog(
                person_id=contact.id,
                job_id=job.id,
                variant=variant_id,
                style=variant_template["style"],
                channel=channel,
                message_body=message,
                status="draft",
            )
            session.add(outreach)
            draft_count += 1
            logger.info(f"Draft created: {variant_id} → {contact.name} @ {contact.company}")

        session.commit()
        logger.info(f"Generated {draft_count} message drafts.")
    except Exception as e:
        session.rollback()
        logger.error(f"Error during message generation: {e}")
        raise
    finally:
        session.close()

    return draft_count
