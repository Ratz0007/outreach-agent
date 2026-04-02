"""Tests for job sourcing: CSV import, deduplication, Tier 1 flagging, fit scoring."""

import csv
import json
import os
import tempfile
from pathlib import Path

# Ensure we can import from project root
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.session import init_db, get_session, engine
from src.db.models import Base, JobShortlist, PeopleMapper, OutreachLog, ResponseTracker, CVVersion
from src.sourcing.csv_import import import_jobs_csv
from src.sourcing.fit_scorer import compute_fit_score
from src.config import is_tier1


def setup_test_db():
    """Create a fresh test by clearing existing data (respecting FK order)."""
    init_db()
    session = get_session()
    session.query(ResponseTracker).delete()
    session.query(OutreachLog).delete()
    session.query(CVVersion).delete()
    session.query(PeopleMapper).delete()
    session.query(JobShortlist).delete()
    session.commit()
    session.close()


def create_test_csv(rows: list[dict], path: str):
    """Write test CSV file."""
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def test_csv_import():
    """Test basic CSV import."""
    setup_test_db()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        tmp_path = f.name

    rows = [
        {"Company": "TestCo", "Title": "Account Executive", "Location": "Dublin", "Description": "SaaS sales role in Dublin. MEDDIC experience preferred.", "Link": "https://example.com/1"},
        {"Company": "AIStartup", "Title": "Founding AE", "Location": "Remote - Europe", "Description": "First sales hire for AI startup. Full-cycle B2B SaaS.", "Link": "https://example.com/2"},
    ]
    create_test_csv(rows, tmp_path)

    count = import_jobs_csv(tmp_path, "linkedin")
    assert count == 2, f"Expected 2 imports, got {count}"

    session = get_session()
    jobs = session.query(JobShortlist).all()
    assert len(jobs) == 2
    assert jobs[0].company == "TestCo"
    assert jobs[0].source == "linkedin"
    assert jobs[0].fit_score >= 3  # Should get a decent score
    session.close()

    os.unlink(tmp_path)
    print("PASS: test_csv_import")


def test_deduplication():
    """Test that duplicate company+title combos are skipped."""
    setup_test_db()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        tmp_path = f.name

    rows = [
        {"Company": "DupeCo", "Title": "Sales Manager", "Location": "Dublin", "Description": "Sales role", "Link": ""},
        {"Company": "DupeCo", "Title": "Sales Manager", "Location": "London", "Description": "Same role different location", "Link": ""},
    ]
    create_test_csv(rows, tmp_path)

    count = import_jobs_csv(tmp_path, "linkedin")
    assert count == 1, f"Expected 1 (dedup), got {count}"

    # Import same file again — should add 0
    count2 = import_jobs_csv(tmp_path, "linkedin")
    assert count2 == 0, f"Expected 0 (already exists), got {count2}"

    os.unlink(tmp_path)
    print("PASS: test_deduplication")


def test_tier1_flagging():
    """Test that Tier 1 companies get flagged."""
    setup_test_db()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        tmp_path = f.name

    rows = [
        {"Company": "Salesforce", "Title": "Account Executive", "Location": "Dublin", "Description": "AE at Salesforce", "Link": ""},
        {"Company": "Google", "Title": "Sales Manager", "Location": "Dublin", "Description": "Sales at Google", "Link": ""},
        {"Company": "RandomStartup", "Title": "AE", "Location": "Dublin", "Description": "AE role", "Link": ""},
    ]
    create_test_csv(rows, tmp_path)

    count = import_jobs_csv(tmp_path, "linkedin")
    assert count == 3

    session = get_session()
    sf = session.query(JobShortlist).filter_by(company="Salesforce").first()
    google = session.query(JobShortlist).filter_by(company="Google").first()
    random = session.query(JobShortlist).filter_by(company="RandomStartup").first()

    assert sf.is_tier1 is True, "Salesforce should be Tier 1"
    assert google.is_tier1 is True, "Google should be Tier 1"
    assert random.is_tier1 is False, "RandomStartup should NOT be Tier 1"
    assert sf.sourcer_note == "Tier 1 — apply manually"

    session.close()
    os.unlink(tmp_path)
    print("PASS: test_tier1_flagging")


def test_excluded_keywords():
    """Test that junior/intern roles are excluded."""
    setup_test_db()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        tmp_path = f.name

    rows = [
        {"Company": "Co1", "Title": "Junior Sales Rep", "Location": "Dublin", "Description": "Entry level role", "Link": ""},
        {"Company": "Co2", "Title": "Sales Intern", "Location": "Dublin", "Description": "Internship", "Link": ""},
        {"Company": "Co3", "Title": "Senior Account Executive", "Location": "Dublin", "Description": "Senior SaaS role", "Link": ""},
    ]
    create_test_csv(rows, tmp_path)

    count = import_jobs_csv(tmp_path, "linkedin")
    assert count == 1, f"Expected 1 (juniors excluded), got {count}"

    session = get_session()
    job = session.query(JobShortlist).first()
    assert job.company == "Co3"
    session.close()

    os.unlink(tmp_path)
    print("PASS: test_excluded_keywords")


def test_fit_scoring():
    """Test fit score computation."""
    # Perfect match: SaaS, SMB, AE, Dublin, AI
    score = compute_fit_score(
        ["saas", "smb", "ai", "meddic", "dublin"],
        "Senior Account Executive",
        "SaaS sales role in Dublin. AI-powered platform for SMB. MEDDIC experience required."
    )
    assert score >= 7, f"Perfect match should score >=7, got {score}"

    # Poor match: unrelated
    score2 = compute_fit_score(
        [],
        "Warehouse Worker",
        "Picking and packing items in our warehouse."
    )
    assert score2 <= 4, f"Poor match should score <=4, got {score2}"

    print("PASS: test_fit_scoring")


def test_tier1_check():
    """Test Tier 1 company detection."""
    assert is_tier1("Salesforce") is True
    assert is_tier1("salesforce") is True  # Case insensitive
    assert is_tier1("GOOGLE") is True
    assert is_tier1("RandomStartup") is False
    assert is_tier1("  HubSpot  ") is True  # Handles whitespace
    print("PASS: test_tier1_check")


if __name__ == "__main__":
    test_tier1_check()
    test_fit_scoring()
    test_csv_import()
    test_deduplication()
    test_tier1_flagging()
    test_excluded_keywords()
    print("\n=== ALL SOURCING TESTS PASSED ===")
