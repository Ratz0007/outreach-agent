"""Contact enrichment — Stage 2.

Multi-source enrichment pipeline:
1. Hunter.io (free, 50 searches/month) — primary domain search for contacts + emails
2. Snov.io (free credits) — email finder by name + domain (supplements Hunter)
3. Apollo.io (free) — company domain discovery to feed Hunter/Snov
4. Mock data fallback when no APIs return results

Priority: 1=hiring manager, 2=team lead/peer, 3=recruiter.
Rate limit: 1 request/sec.
"""

import json
import logging
import random
import time
from datetime import datetime

import requests

from src.config import AgentConfig, Secrets
from src.db.models import JobShortlist, PeopleMapper
from src.db.session import get_session

logger = logging.getLogger(__name__)

HUNTER_DOMAIN_SEARCH_URL = "https://api.hunter.io/v2/domain-search"
HUNTER_ACCOUNT_URL = "https://api.hunter.io/v2/account"
APOLLO_ORG_ENRICH_URL = "https://api.apollo.io/api/v1/organizations/enrich"
SNOV_AUTH_URL = "https://api.snov.io/v1/oauth/access_token"
SNOV_EMAIL_FINDER_URL = "https://api.snov.io/v1/get-emails-from-names"

# Title patterns mapped to relationship types and priorities
TITLE_PRIORITY_MAP = {
    "hiring_manager": {
        "titles": ["Head of Sales", "VP Sales", "VP of Sales", "CRO", "Chief Revenue Officer",
                    "Sales Director", "Director of Sales", "Hiring Manager",
                    "Director of Revenue", "Head of Revenue"],
        "priority": 1,
    },
    "team_lead": {
        "titles": ["Sales Team Lead", "Team Lead", "Sales Lead", "Senior Sales Manager",
                    "Regional Sales Manager", "Sales Manager", "Account Director",
                    "Senior Account Executive", "Revenue Manager"],
        "priority": 2,
    },
    "recruiter": {
        "titles": ["Talent Acquisition", "Recruiter", "HR Manager", "People Operations",
                    "Hiring Coordinator", "People Partner", "HR Director",
                    "Head of People", "Head of Talent"],
        "priority": 3,
    },
}

# Sales-relevant title keywords for filtering Hunter.io results
SALES_TITLE_KEYWORDS = [
    "sales", "revenue", "commercial", "business development", "account",
    "cro", "vp", "director", "head of", "manager", "lead",
    "growth", "partnerships", "talent", "recruit", "hiring",
    "hr", "people", "founder", "ceo", "coo", "co-founder",
]


def _classify_contact(title: str) -> tuple[str, int]:
    """Classify a contact's relationship type and priority based on their title."""
    title_lower = (title or "").lower()
    for rel_type, config in TITLE_PRIORITY_MAP.items():
        for pattern in config["titles"]:
            if pattern.lower() in title_lower:
                return rel_type, config["priority"]
    # Default: treat as peer with priority 2
    return "peer", 2


def _is_sales_relevant(title: str) -> bool:
    """Check if a contact's title is relevant to sales outreach."""
    if not title:
        return True  # Include contacts without titles (might be useful)
    title_lower = title.lower()
    return any(kw in title_lower for kw in SALES_TITLE_KEYWORDS)


def _get_hunter_remaining() -> int:
    """Check how many Hunter.io searches remain this month."""
    if not Secrets.HUNTER_API_KEY:
        return 0
    try:
        resp = requests.get(HUNTER_ACCOUNT_URL, params={
            "api_key": Secrets.HUNTER_API_KEY,
        }, timeout=10)
        if resp.status_code == 200:
            searches = resp.json().get("data", {}).get("requests", {}).get("searches", {})
            available = searches.get("available", 0)
            used = searches.get("used", 0)
            remaining = available - used
            logger.info(f"Hunter.io searches: {used}/{available} used, {remaining} remaining")
            return remaining
    except Exception as e:
        logger.error(f"Hunter.io account check failed: {e}")
    return 0


def _get_domain_from_apollo(company_name: str) -> str | None:
    """Use Apollo's free org enrichment to find a company's domain."""
    if not Secrets.APOLLO_API_KEY:
        return None
    try:
        resp = requests.get(APOLLO_ORG_ENRICH_URL, headers={
            "X-Api-Key": Secrets.APOLLO_API_KEY,
            "Content-Type": "application/json",
        }, params={
            "name": company_name,
        }, timeout=10)
        if resp.status_code == 200:
            org = resp.json().get("organization", {})
            domain = org.get("primary_domain") or org.get("website_url", "")
            if domain:
                # Clean up domain
                domain = domain.replace("https://", "").replace("http://", "").rstrip("/")
                logger.info(f"Apollo found domain for {company_name}: {domain}")
                return domain
    except Exception as e:
        logger.error(f"Apollo org enrichment failed for {company_name}: {e}")
    return None


def _search_hunter(company_name: str, domain: str = None) -> list[dict]:
    """Search Hunter.io for contacts at a company. Returns list of contact dicts."""
    api_key = Secrets.HUNTER_API_KEY
    if not api_key:
        return []

    params = {
        "api_key": api_key,
        "limit": 5,
        "type": "personal",  # Skip generic emails like info@company.com
    }

    if domain:
        params["domain"] = domain
    else:
        params["company"] = company_name

    try:
        resp = requests.get(HUNTER_DOMAIN_SEARCH_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        emails = data.get("emails", [])

        contacts = []
        for e in emails:
            first = e.get("first_name", "") or ""
            last = e.get("last_name", "") or ""
            name = f"{first} {last}".strip()
            if not name or name == " ":
                continue

            title = e.get("position", "") or ""
            email = e.get("value", "")
            confidence = e.get("confidence", 0)
            linkedin = e.get("linkedin", "") or ""

            contacts.append({
                "name": name,
                "title": title,
                "email": email,
                "linkedin_url": linkedin,
                "company": company_name,
                "confidence": confidence,
                "source": "hunter",
            })

        # Sort: sales-relevant first, then by confidence
        contacts.sort(key=lambda c: (
            not _is_sales_relevant(c["title"]),
            -c.get("confidence", 0),
        ))

        return contacts

    except requests.RequestException as e:
        logger.error(f"Hunter.io API error for '{company_name}': {e}")
        return []


def _get_snov_token() -> str | None:
    """Get Snov.io access token using client credentials."""
    if not Secrets.SNOV_USER_ID or not Secrets.SNOV_SECRET:
        return None
    try:
        resp = requests.post(SNOV_AUTH_URL, json={
            "grant_type": "client_credentials",
            "client_id": Secrets.SNOV_USER_ID,
            "client_secret": Secrets.SNOV_SECRET,
        }, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("access_token")
    except Exception as e:
        logger.error(f"Snov.io auth failed: {e}")
    return None


def _snov_find_email(first_name: str, last_name: str, domain: str, token: str) -> str | None:
    """Use Snov.io to find a person's email by name + company domain."""
    try:
        resp = requests.post(SNOV_EMAIL_FINDER_URL, json={
            "access_token": token,
            "firstName": first_name,
            "lastName": last_name,
            "domain": domain,
        }, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
                emails = data.get("data", {}).get("emails", [])
                for e in emails:
                    if e.get("emailStatus") in ("valid", "unknown"):
                        return e.get("email")
    except Exception as e:
        logger.error(f"Snov.io email finder failed for {first_name} {last_name}: {e}")
    return None


def _enrich_missing_emails_with_snov(contacts: list[dict], domain: str) -> list[dict]:
    """Use Snov.io to find emails for contacts that Hunter didn't return emails for."""
    if not Secrets.SNOV_USER_ID:
        return contacts

    token = _get_snov_token()
    if not token:
        return contacts

    for contact in contacts:
        if contact.get("email"):
            continue  # Already has email

        name_parts = contact["name"].split(None, 1)
        if len(name_parts) < 2:
            continue

        first_name, last_name = name_parts[0], name_parts[1]
        email = _snov_find_email(first_name, last_name, domain, token)
        if email:
            contact["email"] = email
            contact["source"] = contact.get("source", "hunter") + "+snov"
            logger.info(f"  Snov.io found email for {contact['name']}: {email}")
        time.sleep(0.5)  # Rate limit

    return contacts


def _search_contacts(company_name: str) -> tuple[list[dict], str]:
    """Search for contacts using available APIs. Returns (contacts, source)."""

    domain = None

    # Strategy 1: Hunter.io direct company search
    if Secrets.HUNTER_API_KEY:
        contacts = _search_hunter(company_name)
        if contacts:
            # Try Snov.io for contacts missing emails
            missing = [c for c in contacts if not c.get("email")]
            if missing and Secrets.SNOV_USER_ID:
                # Need domain for Snov — extract from existing emails or Apollo
                existing_emails = [c["email"] for c in contacts if c.get("email")]
                if existing_emails:
                    domain = existing_emails[0].split("@")[-1]
                else:
                    domain = _get_domain_from_apollo(company_name) if Secrets.APOLLO_API_KEY else None
                if domain:
                    contacts = _enrich_missing_emails_with_snov(contacts, domain)
            return contacts, "hunter"

        # Strategy 2: Use Apollo to find domain, then Hunter.io domain search
        if Secrets.APOLLO_API_KEY:
            domain = _get_domain_from_apollo(company_name)
            if domain:
                contacts = _search_hunter(company_name, domain=domain)
                if contacts:
                    # Enrich missing emails with Snov
                    if Secrets.SNOV_USER_ID:
                        contacts = _enrich_missing_emails_with_snov(contacts, domain)
                    return contacts, "hunter+apollo"

    # Strategy 3: Mock data fallback
    logger.info(f"No real contacts found for {company_name}. Using mock data.")
    return _mock_contacts(company_name), "mock"


def _mock_contacts(company_name: str) -> list[dict]:
    """Generate mock contacts for development when APIs can't find real contacts."""
    first_names = ["Sarah", "James", "Lisa", "Mark", "Emma", "David", "Rachel", "Tom"]
    last_names = ["O'Brien", "Murphy", "Chen", "Kelly", "Walsh", "Ryan", "Singh", "Brown"]

    mock_titles = [
        ("Head of Sales", "hiring_manager"),
        ("Sales Team Lead", "team_lead"),
        ("Talent Acquisition Manager", "recruiter"),
    ]

    contacts = []
    num_contacts = random.randint(1, 3)
    for i in range(num_contacts):
        first = random.choice(first_names)
        last = random.choice(last_names)
        title, _ = mock_titles[i % len(mock_titles)]
        domain = company_name.lower().replace(" ", "").replace(".", "") + ".com"
        last_clean = last.replace("'", "").lower()

        contacts.append({
            "name": f"{first} {last}",
            "title": title,
            "email": f"{first.lower()}.{last_clean}@{domain}",
            "linkedin_url": f"https://linkedin.com/in/{first.lower()}{last_clean}",
            "company": company_name,
        })

    return contacts


def enrich_contacts(max_jobs: int = 0) -> int:
    """Enrich contacts for all non-Tier1 jobs that don't have contacts yet.

    Args:
        max_jobs: Maximum number of jobs to enrich (0 = all pending).
                  Useful for staying within Hunter.io free tier limits.

    Returns:
        Count of jobs enriched.
    """
    session = get_session()
    enriched_count = 0

    try:
        # Check Hunter.io remaining quota
        hunter_remaining = _get_hunter_remaining()
        if Secrets.HUNTER_API_KEY and hunter_remaining <= 0:
            logger.warning("Hunter.io search quota exhausted for this month. Using mock data.")

        # Find jobs that need enrichment: non-Tier1, no contacts yet
        query = session.query(JobShortlist).filter(
            JobShortlist.is_tier1 == False,
            ~JobShortlist.id.in_(
                session.query(PeopleMapper.job_id).distinct()
            )
        ).order_by(JobShortlist.fit_score.desc())  # Prioritise high-fit jobs

        if max_jobs > 0:
            query = query.limit(max_jobs)

        jobs = query.all()

        if not jobs:
            logger.info("No jobs need contact enrichment.")
            return 0

        logger.info(f"Enriching contacts for {len(jobs)} jobs...")

        for job in jobs:
            logger.info(f"Enriching: {job.company} -- {job.role}")

            # Check if we still have Hunter searches
            if Secrets.HUNTER_API_KEY and hunter_remaining <= 2:
                logger.warning("Low Hunter.io quota — switching to mock for remaining jobs")
                contacts, source = _mock_contacts(job.company), "mock"
            else:
                contacts, source = _search_contacts(job.company)
                if source.startswith("hunter"):
                    hunter_remaining -= 1

            if not contacts:
                logger.warning(f"No contacts found for {job.company}. Flagging for manual research.")
                continue

            # Limit to max_contacts_per_company
            added = 0
            for contact_data in contacts[:AgentConfig.max_contacts_per_company]:
                rel_type, priority = _classify_contact(contact_data.get("title", ""))

                person = PeopleMapper(
                    job_id=job.id,
                    name=contact_data["name"],
                    title=contact_data.get("title", ""),
                    company=contact_data["company"],
                    linkedin_url=contact_data.get("linkedin_url", ""),
                    email=contact_data.get("email", ""),
                    relationship_type=rel_type,
                    priority=priority,
                    next_action="to_contact",
                    source=source,
                )
                session.add(person)
                added += 1

            if added > 0:
                enriched_count += 1
                logger.info(f"  Added {added} contacts from {source}")

            # Rate limit: 1 req/sec
            time.sleep(1)

        session.commit()
        logger.info(f"Enriched contacts for {enriched_count} jobs.")
    except Exception as e:
        session.rollback()
        logger.error(f"Error during contact enrichment: {e}")
        raise
    finally:
        session.close()

    return enriched_count
