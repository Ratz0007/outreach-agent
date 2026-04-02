"""Auto fit scoring based on keyword match to master_profile.yaml.

Scores jobs 1-10 based on how well they match Ratin's profile.
"""

from src.config import MASTER_PROFILE

# Build a set of profile keywords from skills, experience bullets, summary
_PROFILE_KEYWORDS: set[str] = set()


def _init_profile_keywords():
    global _PROFILE_KEYWORDS
    if _PROFILE_KEYWORDS:
        return

    # From skills
    skills = MASTER_PROFILE.get("skills", {})
    if isinstance(skills, dict):
        for category_skills in skills.values():
            if isinstance(category_skills, list):
                for s in category_skills:
                    _PROFILE_KEYWORDS.update(s.lower().split())
    elif isinstance(skills, list):
        for s in skills:
            _PROFILE_KEYWORDS.update(s.lower().split())

    # From summary
    summary = MASTER_PROFILE.get("summary", "")
    _PROFILE_KEYWORDS.update(summary.lower().split())

    # Key phrases to match (weighted higher)
    _PROFILE_KEYWORDS.update([
        "saas", "smb", "mid-market", "account executive", "sales manager",
        "meddic", "meddpicc", "consultative", "ai", "startup",
        "founding", "quota", "arr", "pipeline", "full-cycle",
        "hubspot", "salesforce", "emea", "europe", "ireland", "dublin",
        "b2b", "enterprise", "growth", "expansion", "outbound",
    ])

    # Remove noise words
    _PROFILE_KEYWORDS -= {"the", "a", "an", "and", "or", "in", "of", "to", "for", "is", "at", "on", "with"}


# High-value keywords that strongly indicate fit
HIGH_VALUE_KEYWORDS = {
    "saas", "smb", "mid-market", "account executive", "founding ae",
    "meddic", "ai", "startup", "consultative", "full-cycle",
    "emea", "europe", "ireland", "dublin", "b2b", "arr",
}

# Role title keywords that indicate strong fit
STRONG_ROLE_MATCHES = [
    "account executive", "sales manager", "business development",
    "founding ae", "senior account executive", "bdm",
]


def compute_fit_score(keywords: list[str], role_title: str, description: str) -> int:
    """Compute fit score 1-10 based on keyword overlap with profile.

    Scoring:
    - Base: 3 (any role that passed filters)
    - +1 for each high-value keyword match (max +3)
    - +1 for strong role title match
    - +1 for location match (Ireland/Dublin/Remote Europe)
    - +1 for SaaS/AI industry match
    - +1 for experience-level match (not junior/intern)
    """
    _init_profile_keywords()

    score = 3  # Base score for passing initial filters
    desc_lower = description.lower()
    role_lower = role_title.lower()

    # High-value keyword matches (max +3)
    hv_matches = sum(1 for kw in HIGH_VALUE_KEYWORDS if kw in desc_lower or kw in keywords)
    score += min(hv_matches, 3)

    # Strong role title match (+1)
    if any(r in role_lower for r in STRONG_ROLE_MATCHES):
        score += 1

    # Location match (+1)
    location_keywords = ["ireland", "dublin", "remote", "emea", "europe"]
    if any(loc in desc_lower for loc in location_keywords):
        score += 1

    # Industry match (+1)
    if "saas" in desc_lower or "ai" in desc_lower or "software" in desc_lower:
        score += 1

    # Seniority/experience match (+1)
    if "senior" in role_lower or "manager" in role_lower or "founding" in role_lower:
        score += 1

    return min(score, 10)
