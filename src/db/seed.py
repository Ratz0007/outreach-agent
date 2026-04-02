"""Seed database with test data for development."""

import json
from datetime import datetime, date, timedelta
from src.db.session import get_session
from src.db.models import JobShortlist, PeopleMapper, OutreachLog, ResponseTracker, CVVersion


def seed_test_data():
    """Insert sample data into all 5 tables."""
    session = get_session()
    try:
        # Check if data already exists
        if session.query(JobShortlist).count() > 0:
            from rich.console import Console
            Console().print("[yellow]Database already has data. Skipping seed.[/yellow]")
            return

        # ── Jobs ───────────────────────────────────────────────
        jobs = [
            JobShortlist(
                company="Acme SaaS", role="Account Executive", location="Dublin",
                industry="SaaS", company_stage="Series B", tier=2, desired_segment="SMB",
                fit_score=8, status="shortlisted",
                application_link="https://example.com/apply/1",
                description="Looking for an experienced AE to drive SMB sales in EMEA. MEDDIC experience preferred.",
                keywords=json.dumps(["SaaS", "SMB", "MEDDIC", "EMEA", "quota"]),
                is_tier1=False, source="adzuna",
            ),
            JobShortlist(
                company="FinBot AI", role="Senior Account Executive", location="Remote - Europe",
                industry="Fintech", company_stage="Series A", tier=2, desired_segment="Mid-Market",
                fit_score=9, status="shortlisted",
                application_link="https://example.com/apply/2",
                description="Join our growing sales team. Sell AI-powered financial tools to mid-market companies.",
                keywords=json.dumps(["AI", "Fintech", "Mid-Market", "consultative selling"]),
                is_tier1=False, source="adzuna",
            ),
            JobShortlist(
                company="CyberShield", role="Business Development Manager", location="London",
                industry="Cybersecurity", company_stage="Growth", tier=3, desired_segment="Enterprise",
                fit_score=6, status="shortlisted",
                description="BDM role focused on enterprise cybersecurity sales across UK and Ireland.",
                keywords=json.dumps(["Cybersecurity", "Enterprise", "UK", "Ireland"]),
                is_tier1=False, source="manual",
            ),
            JobShortlist(
                company="Salesforce", role="Account Executive", location="Dublin",
                industry="SaaS", company_stage="Public", tier=1, desired_segment="Enterprise",
                fit_score=7, status="shortlisted",
                description="AE role at Salesforce Dublin office.",
                keywords=json.dumps(["CRM", "Enterprise", "SaaS"]),
                is_tier1=True, source="linkedin",
                sourcer_note="Tier 1 — apply manually with tailored CV",
            ),
            JobShortlist(
                company="StartupXYZ", role="Founding AE", location="Dublin",
                industry="AI", company_stage="Seed", tier=2, desired_segment="SMB",
                fit_score=9, status="contacted",
                description="First sales hire. Build sales from zero. AI product for SMBs.",
                keywords=json.dumps(["Founding AE", "AI", "SMB", "0-to-1", "startup"]),
                is_tier1=False, source="adzuna",
            ),
        ]
        session.add_all(jobs)
        session.flush()

        # ── Contacts ──────────────────────────────────────────
        contacts = [
            PeopleMapper(
                job_id=jobs[0].id, name="Sarah O'Brien", title="Head of Sales",
                company="Acme SaaS", linkedin_url="https://linkedin.com/in/sarahobrien",
                email="sarah@acmesaas.com", relationship_type="hiring_manager",
                priority=1, next_action="to_contact", source="apollo",
            ),
            PeopleMapper(
                job_id=jobs[0].id, name="Mark Kelly", title="Sales Team Lead",
                company="Acme SaaS", linkedin_url="https://linkedin.com/in/markkelly",
                email="mark@acmesaas.com", relationship_type="team_lead",
                priority=2, next_action="to_contact", source="apollo",
            ),
            PeopleMapper(
                job_id=jobs[1].id, name="Lisa Chen", title="VP Sales",
                company="FinBot AI", linkedin_url="https://linkedin.com/in/lisachen",
                email="lisa@finbotai.com", relationship_type="hiring_manager",
                priority=1, next_action="to_contact", source="apollo",
            ),
            PeopleMapper(
                job_id=jobs[4].id, name="James Murphy", title="CEO & Founder",
                company="StartupXYZ", linkedin_url="https://linkedin.com/in/jamesmurphy",
                email="james@startupxyz.com", relationship_type="hiring_manager",
                priority=1, assigned_variant="V4", next_action="contacted",
                last_contact_date=date.today() - timedelta(days=3),
                next_follow_up=date.today() + timedelta(days=1),
                source="manual",
            ),
        ]
        session.add_all(contacts)
        session.flush()

        # ── Outreach logs ─────────────────────────────────────
        outreach = [
            OutreachLog(
                person_id=contacts[3].id, job_id=jobs[4].id,
                variant="V4", style="value_first", channel="email",
                message_body="Hi James, StartupXYZ caught my eye for how you're approaching AI for SMBs. "
                             "In 2024 I built $540K ARR from zero selling SaaS to SMBs across EMEA. "
                             "With that 0-to-1 experience, I'd love to discuss fit for the Founding AE role. "
                             "Can we set a 10-min chat?",
                status="sent",
                sent_at=datetime.utcnow() - timedelta(days=3),
                follow_up_date=date.today() + timedelta(days=1),
                follow_up_count=0,
            ),
        ]
        session.add_all(outreach)
        session.flush()

        # ── Responses ─────────────────────────────────────────
        responses = [
            ResponseTracker(
                outreach_id=outreach[0].id, person_id=contacts[3].id, job_id=jobs[4].id,
                response_type="interest", response_date=datetime.utcnow() - timedelta(days=1),
                action_taken="interview_scheduled",
                notes="James replied — interested, scheduled call for Friday.",
            ),
        ]
        session.add_all(responses)

        session.commit()
        from rich.console import Console
        Console().print(f"[green]Seeded: {len(jobs)} jobs, {len(contacts)} contacts, "
                       f"{len(outreach)} outreach logs, {len(responses)} responses.[/green]")
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()
