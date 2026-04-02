"""Adzuna API job sourcing — Stage 1.

Adzuna API docs: https://developer.adzuna.com/overview
Free tier: 250 requests/month, no credit card needed.
Sign up at https://developer.adzuna.com/ to get APP_ID and APP_KEY.
"""

import json
import logging
import time
from datetime import datetime

import requests
from sqlalchemy import and_

from src.config import AgentConfig, Secrets, is_tier1, TIER1_COMPANIES_LOWER
from src.db.models import JobShortlist
from src.db.session import get_session
from src.sourcing.fit_scorer import compute_fit_score

logger = logging.getLogger(__name__)

ADZUNA_BASE_URL = "https://api.adzuna.com/v1/api/jobs"

# Map our config locations to Adzuna country codes + what param
# Adzuna supported countries: at, au, be, br, ca, ch, de, es, fr, gb, in, it, mx, nl, nz, pl, sg, us, za
# Ireland is NOT supported — we search GB (includes many Dublin/Ireland-based roles)
LOCATION_MAP = {
    "ireland": {"country": "gb", "where": "Ireland"},
    "dublin": {"country": "gb", "where": "Dublin"},
    "london": {"country": "gb", "where": "London"},
    "remote - europe": [
        {"country": "gb", "where": "", "extra_what": "remote"},
        {"country": "de", "where": "", "extra_what": "remote"},
        {"country": "nl", "where": "", "extra_what": "remote"},
        {"country": "fr", "where": "", "extra_what": "remote"},
    ],
}


def _search_adzuna(role: str, country: str, where: str = "", page: int = 1) -> list[dict]:
    """Query Adzuna API for jobs. Returns list of raw job dicts."""
    app_id = Secrets.ADZUNA_APP_ID
    app_key = Secrets.ADZUNA_APP_KEY

    if not app_id or not app_key:
        logger.warning("Adzuna API keys not set. Skipping API search.")
        return []

    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": 20,
        "what": role,
        "content-type": "application/json",
        "sort_by": "date",
        "max_days_old": 7,  # Only jobs from last 7 days
    }
    if where:
        params["where"] = where

    url = f"{ADZUNA_BASE_URL}/{country}/search/{page}"

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])
    except requests.RequestException as e:
        logger.error(f"Adzuna API error for '{role}' in {country}: {e}")
        return []


def _parse_adzuna_job(raw: dict) -> dict:
    """Parse raw Adzuna API response into our schema fields."""
    company = raw.get("company", {}).get("display_name", "Unknown")
    title = raw.get("title", "").replace("<strong>", "").replace("</strong>", "")
    location_name = raw.get("location", {}).get("display_name", "")
    description = raw.get("description", "")
    redirect_url = raw.get("redirect_url", "")
    category = raw.get("category", {}).get("label", "")

    return {
        "company": company.strip(),
        "role": title.strip(),
        "location": location_name.strip(),
        "industry": category.strip(),
        "description": description.strip(),
        "application_link": redirect_url,
        "source": "adzuna",
    }


def _is_excluded(title: str, description: str) -> bool:
    """Check if job title or description contains excluded keywords."""
    text = f"{title} {description}".lower()
    return any(kw in text for kw in AgentConfig.exclude_keywords)


def _is_duplicate(session, company: str, role: str) -> bool:
    """Check if job already exists by company + title combo."""
    existing = session.query(JobShortlist).filter(
        and_(
            JobShortlist.company.ilike(company.strip()),
            JobShortlist.role.ilike(role.strip()),
        )
    ).first()
    return existing is not None


def _extract_keywords(description: str) -> list[str]:
    """Extract basic keywords from job description.
    Simple keyword extraction — Claude API will do deeper analysis later."""
    keyword_bank = [
        "saas", "ai", "ml", "machine learning", "b2b", "b2c", "smb", "mid-market",
        "enterprise", "startup", "fintech", "cybersecurity", "cloud", "devops",
        "meddic", "meddpicc", "consultative", "solution selling", "quota",
        "pipeline", "cold calling", "outbound", "inbound", "account executive",
        "sales manager", "bdm", "business development", "founding",
        "hubspot", "salesforce", "crm", "sales navigator", "gong", "outreach",
        "emea", "europe", "ireland", "dublin", "london", "remote",
        "full-cycle", "discovery", "demo", "negotiation", "closing",
        "arr", "mrr", "acv", "revenue", "growth", "expansion",
    ]
    desc_lower = description.lower()
    found = [kw for kw in keyword_bank if kw in desc_lower]
    return list(set(found))


def source_jobs() -> int:
    """Query Adzuna API for all configured roles/locations, deduplicate, store new jobs.
    Returns count of new jobs added."""
    session = get_session()
    new_count = 0

    try:
        seen_combos = set()  # (company_lower, role_lower) within this run

        for role in AgentConfig.roles:
            for location in AgentConfig.locations:
                loc_key = location.strip().lower()
                loc_config = LOCATION_MAP.get(loc_key)
                if not loc_config:
                    logger.warning(f"Unknown location '{location}', skipping.")
                    continue

                # Handle multi-country searches (e.g., Remote - Europe)
                search_configs = loc_config if isinstance(loc_config, list) else [loc_config]

                for sc in search_configs:
                    search_role = role
                    if sc.get("extra_what"):
                        search_role = f"{role} {sc['extra_what']}"

                    logger.info(f"Searching Adzuna: '{search_role}' in {sc['country']} {sc.get('where', '')}")
                    raw_jobs = _search_adzuna(search_role, sc["country"], sc.get("where", ""))

                    for raw in raw_jobs:
                        parsed = _parse_adzuna_job(raw)

                        # Skip excluded keywords
                        if _is_excluded(parsed["role"], parsed["description"]):
                            continue

                        # Deduplicate within this run
                        combo = (parsed["company"].lower(), parsed["role"].lower())
                        if combo in seen_combos:
                            continue
                        seen_combos.add(combo)

                        # Deduplicate against existing DB
                        if _is_duplicate(session, parsed["company"], parsed["role"]):
                            continue

                        # Extract keywords and compute fit score
                        keywords = _extract_keywords(parsed["description"])
                        fit_score = compute_fit_score(keywords, parsed["role"], parsed["description"])
                        tier1 = is_tier1(parsed["company"])

                        job = JobShortlist(
                            company=parsed["company"],
                            role=parsed["role"],
                            location=parsed["location"],
                            industry=parsed["industry"],
                            fit_score=fit_score,
                            status="shortlisted",
                            application_link=parsed["application_link"],
                            description=parsed["description"],
                            keywords=json.dumps(keywords),
                            is_tier1=tier1,
                            source="adzuna",
                            sourcer_note="Tier 1 — apply manually" if tier1 else None,
                        )
                        session.add(job)
                        new_count += 1

                    # Rate limit: be polite to Adzuna API
                    time.sleep(0.5)

        session.commit()
        logger.info(f"Sourced {new_count} new jobs from Adzuna.")
    except Exception as e:
        session.rollback()
        logger.error(f"Error during job sourcing: {e}")
        raise
    finally:
        session.close()

    return new_count
