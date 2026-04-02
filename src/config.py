"""Config loading: .env secrets + YAML settings + Multi-Tenant Overrides."""

import os
from pathlib import Path
from dotenv import load_dotenv
import yaml
import contextvars
import json

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Context var for multi-tenancy background jobs
current_user_id = contextvars.ContextVar("current_user_id", default=None)

# Load .env from project root
load_dotenv(PROJECT_ROOT / ".env", override=True)

def _load_yaml(filename: str) -> dict:
    path = PROJECT_ROOT / filename
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

_config = _load_yaml("config.yaml")
_tier1 = _load_yaml("data/tier1_exclusions.yaml")
_profile = _load_yaml("data/master_profile.yaml")

def _get_user_setting(key: str, default):
    uid = current_user_id.get()
    if not uid:
        return default
    
    # Import locally to avoid circular dependencies
    from src.db.session import SessionLocal
    from src.db.models import User
    
    session = SessionLocal()
    try:
        user = session.get(User, uid)
        if user and user.settings:
            settings = json.loads(user.settings)
            val = settings.get(key)
            if val is not None and str(val).strip() != "":
                # Attempt to parse types if the default is a specific type
                if isinstance(default, int) and isinstance(val, str):
                    try: return int(val)
                    except: pass
                if isinstance(default, list) and isinstance(val, str):
                    try: return [x.strip() for x in val.split(",") if x.strip()]
                    except: pass
                return val
    except Exception:
        pass
    finally:
        session.close()
        
    return default

class SecretsMeta(type):
    @property
    def ANTHROPIC_API_KEY(cls): return _get_user_setting("anthropic_api_key", os.getenv("ANTHROPIC_API_KEY", ""))
    @property
    def APOLLO_API_KEY(cls): return _get_user_setting("apollo_api_key", os.getenv("APOLLO_API_KEY", ""))
    @property
    def GMAIL_CLIENT_ID(cls): return _get_user_setting("gmail_client_id", os.getenv("GMAIL_CLIENT_ID", ""))
    @property
    def GMAIL_CLIENT_SECRET(cls): return _get_user_setting("gmail_client_secret", os.getenv("GMAIL_CLIENT_SECRET", ""))
    @property
    def GMAIL_REFRESH_TOKEN(cls): return _get_user_setting("gmail_refresh_token", os.getenv("GMAIL_REFRESH_TOKEN", ""))
    @property
    def LINKEDIN_CLIENT_ID(cls): return _get_user_setting("linkedin_client_id", os.getenv("LINKEDIN_CLIENT_ID", ""))
    @property
    def LINKEDIN_CLIENT_SECRET(cls): return _get_user_setting("linkedin_client_secret", os.getenv("LINKEDIN_CLIENT_SECRET", ""))
    @property
    def LINKEDIN_ACCESS_TOKEN(cls): return _get_user_setting("linkedin_access_token", os.getenv("LINKEDIN_ACCESS_TOKEN", ""))
    @property
    def ADZUNA_APP_ID(cls): return _get_user_setting("adzuna_app_id", os.getenv("ADZUNA_APP_ID", ""))
    @property
    def ADZUNA_APP_KEY(cls): return _get_user_setting("adzuna_app_key", os.getenv("ADZUNA_APP_KEY", ""))
    @property
    def HUNTER_API_KEY(cls): return _get_user_setting("hunter_api_key", os.getenv("HUNTER_API_KEY", ""))
    @property
    def SNOV_USER_ID(cls): return _get_user_setting("snov_user_id", os.getenv("SNOV_USER_ID", ""))
    @property
    def SNOV_SECRET(cls): return _get_user_setting("snov_secret", os.getenv("SNOV_SECRET", ""))

class Secrets(metaclass=SecretsMeta):
    pass


class AgentConfigMeta(type):
    # Agent
    @property
    def name(cls): return _get_user_setting("full_name", _config.get("agent", {}).get("name", "Ratin Sharma"))
    @property
    def email(cls): return _get_user_setting("profile_email", _config.get("agent", {}).get("email", "ratinsharma99@gmail.com"))
    @property
    def daily_message_limit(cls): return _get_user_setting("daily_message_limit", _config.get("agent", {}).get("daily_message_limit", 20))
    @property
    def daily_linkedin_invite_limit(cls): return _get_user_setting("daily_linkedin_limit", _config.get("agent", {}).get("daily_linkedin_invite_limit", 15))
    @property
    def weekly_linkedin_invite_limit(cls): return _get_user_setting("weekly_linkedin_limit", _config.get("agent", {}).get("weekly_linkedin_invite_limit", 100))
    @property
    def follow_up_days(cls): return _get_user_setting("follow_up_days", _config.get("agent", {}).get("follow_up_days", 4))
    @property
    def max_follow_ups(cls): return _get_user_setting("max_follow_ups", _config.get("agent", {}).get("max_follow_ups", 1))
    @property
    def max_contacts_per_company(cls): return _get_user_setting("max_contacts_per_company", _config.get("agent", {}).get("max_contacts_per_company", 3))
    @property
    def max_contacts_per_company_per_day(cls): return _get_user_setting("max_contacts_per_company_per_day", _config.get("agent", {}).get("max_contacts_per_company_per_day", 1))
    @property
    def linkedin_invite_gap_minutes(cls): return _get_user_setting("linkedin_invite_gap_minutes", _config.get("agent", {}).get("linkedin_invite_gap_minutes", 5))

    @property
    def roles(cls): return _get_user_setting("search_roles", _config.get("search", {}).get("roles", []))
    @property
    def locations(cls): return _get_user_setting("search_locations", _config.get("search", {}).get("locations", []))
    @property
    def industries(cls): return _get_user_setting("search_industries", _config.get("search", {}).get("industries", []))
    @property
    def exclude_keywords(cls): return _get_user_setting("exclude_keywords", _config.get("search", {}).get("exclude_keywords", []))

    # A/B Testing
    @property
    def min_sends_per_variant(cls): return _get_user_setting("min_sends_per_variant", _config.get("ab_testing", {}).get("min_sends_per_variant", 10))
    @property
    def min_total_replies_to_evaluate(cls): return _get_user_setting("min_total_replies", _config.get("ab_testing", {}).get("min_total_replies_to_evaluate", 30))
    @property
    def kill_threshold_pct(cls): return _get_user_setting("kill_threshold", _config.get("ab_testing", {}).get("kill_threshold_pct", 30))
    @property
    def winner_boost_threshold_pct(cls): return _get_user_setting("boost_threshold", _config.get("ab_testing", {}).get("winner_boost_threshold_pct", 30))
    @property
    def min_active_variants(cls): return _get_user_setting("min_active_variants", _config.get("ab_testing", {}).get("min_active_variants", 4))

    @property
    def variants(cls): return _config.get("variants", {})
    @property
    def schedule(cls): return _config.get("schedule", {})

class AgentConfig(metaclass=AgentConfigMeta):
    pass

# Tier 1 exclusions
def _get_tier1():
    base = _tier1.get("tier1_companies", [])
    val = _get_user_setting("tier1_companies", None)
    if isinstance(val, str):
        return [c.strip() for c in val.split("\n") if c.strip()]
    return base

def is_tier1(company_name: str) -> bool:
    return company_name.strip().lower() in {c.lower() for c in _get_tier1()}

def _get_tier1_property():
    return _get_tier1()

TIER1_COMPANIES = property(_get_tier1_property)

# Master profile
MASTER_PROFILE: dict = _profile

def get_profile_summary() -> str: return MASTER_PROFILE.get("summary", "")
def get_profile_bullets() -> list[dict]:
    return [{"company": e.get("company", ""), "title": e.get("title", ""), "bullets": e.get("bullets", [])} for e in MASTER_PROFILE.get("experience", [])]
def get_skills() -> dict: return MASTER_PROFILE.get("skills", {})
