"""CSV import for LinkedIn/IrishJobs job exports — Stage 1.

Supports:
- LinkedIn job search CSV exports
- IrishJobs CSV exports
- Generic CSV with company/role columns
"""

import csv
import json
import logging
from pathlib import Path

from sqlalchemy import and_

from src.config import is_tier1, AgentConfig
from src.db.models import JobShortlist
from src.db.session import get_session
from src.sourcing.fit_scorer import compute_fit_score

logger = logging.getLogger(__name__)

# Column name mappings for different CSV formats
LINKEDIN_COLUMNS = {
    "company": ["Company", "company", "Company Name"],
    "role": ["Title", "title", "Job Title", "Position"],
    "location": ["Location", "location"],
    "description": ["Description", "description", "Job Description"],
    "link": ["Link", "link", "Job URL", "URL", "Application Link"],
}

IRISHJOBS_COLUMNS = {
    "company": ["Company", "Employer", "company"],
    "role": ["Job Title", "Title", "Role", "Position"],
    "location": ["Location", "location", "Area"],
    "description": ["Description", "description", "Details"],
    "link": ["URL", "Link", "Apply Link"],
}


def _find_column(headers: list[str], candidates: list[str]) -> str | None:
    """Find the first matching column name from a list of candidates."""
    headers_lower = {h.lower().strip(): h for h in headers}
    for candidate in candidates:
        if candidate.lower().strip() in headers_lower:
            return headers_lower[candidate.lower().strip()]
    return None


def _get_column_map(headers: list[str], source: str) -> dict[str, str | None]:
    """Map our field names to actual CSV column names."""
    col_defs = LINKEDIN_COLUMNS if source == "linkedin" else IRISHJOBS_COLUMNS
    return {
        field: _find_column(headers, candidates)
        for field, candidates in col_defs.items()
    }


def _is_excluded(title: str, description: str) -> bool:
    """Check if job contains excluded keywords."""
    text = f"{title} {description}".lower()
    return any(kw in text for kw in AgentConfig.exclude_keywords)


def import_jobs_csv(file_path: str, source: str = "linkedin") -> int:
    """Import jobs from a CSV file. Returns count of jobs imported.

    Args:
        file_path: Path to CSV file
        source: 'linkedin' or 'irishjobs' (determines column mapping)
    """
    path = Path(file_path)
    if not path.exists():
        logger.error(f"CSV file not found: {file_path}")
        raise FileNotFoundError(f"CSV file not found: {file_path}")

    session = get_session()
    new_count = 0

    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []

            if not headers:
                logger.error("CSV file has no headers.")
                return 0

            col_map = _get_column_map(headers, source)

            # Must have at least company and role
            if not col_map.get("company") or not col_map.get("role"):
                logger.error(
                    f"CSV missing required columns. Found: {headers}. "
                    f"Need at least 'Company' and 'Title'/'Role' columns."
                )
                return 0

            for row in reader:
                company = (row.get(col_map["company"]) or "").strip()
                role = (row.get(col_map["role"]) or "").strip()

                if not company or not role:
                    continue

                description = (row.get(col_map.get("description", "")) or "").strip() if col_map.get("description") else ""
                location = (row.get(col_map.get("location", "")) or "").strip() if col_map.get("location") else ""
                link = (row.get(col_map.get("link", "")) or "").strip() if col_map.get("link") else ""

                # Skip excluded keywords
                if _is_excluded(role, description):
                    continue

                # Deduplicate against DB
                existing = session.query(JobShortlist).filter(
                    and_(
                        JobShortlist.company.ilike(company),
                        JobShortlist.role.ilike(role),
                    )
                ).first()
                if existing:
                    continue

                # Score and flag
                keywords = []  # Basic extraction for CSV (less data than API)
                if description:
                    from src.sourcing.adzuna import _extract_keywords
                    keywords = _extract_keywords(description)

                fit_score = compute_fit_score(keywords, role, description)
                tier1 = is_tier1(company)

                job = JobShortlist(
                    company=company,
                    role=role,
                    location=location,
                    description=description,
                    application_link=link,
                    keywords=json.dumps(keywords) if keywords else "[]",
                    fit_score=fit_score,
                    is_tier1=tier1,
                    status="shortlisted",
                    source=source,
                    sourcer_note="Tier 1 — apply manually" if tier1 else None,
                )
                session.add(job)
                new_count += 1

        session.commit()
        logger.info(f"Imported {new_count} jobs from {path.name} (source: {source}).")
    except Exception as e:
        session.rollback()
        logger.error(f"Error importing CSV: {e}")
        raise
    finally:
        session.close()

    return new_count
