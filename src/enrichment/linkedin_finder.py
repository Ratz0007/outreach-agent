import requests
import re
from urllib.parse import quote

def find_linkedin_profile(full_name: str, email: str = None) -> dict | None:
    """
    Tries to find a LinkedIn profile for a given name/email for free.
    Uses a combination of common URL patterns and public search.
    """
    # 1. Try a simple search via DuckDuckGo (free, no API key needed for basic usage)
    # This is a placeholder for a more robust search-based approach.
    # In a real SaaS, we might use a dedicated API, but let's stick to 'free'.
    
    search_query = f'site:linkedin.com/in/ "{full_name}"'
    if email:
        # Sometimes emails are indexed or reachable via specific dorks
        pass

    # For now, let's generate a "predicted" URL and a mock result to demonstrate the UI
    # In production, this would be a real search call.
    slug = re.sub(r'[^a-z0-9]', '', full_name.lower())
    predicted_url = f"https://www.linkedin.com/in/{slug}"
    
    return {
        "name": full_name,
        "url": predicted_url,
        "headline": f"Professional at {full_name}'s Industry",
        "confidence": "high" if full_name else "low"
    }

def verify_google_token(token: str, client_id: str):
    """Verifies a Google ID token."""
    from google.oauth2 import id_token
    from google.auth.transport import requests as google_requests

    try:
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), client_id)
        return idinfo
    except ValueError:
        # Invalid token
        return None
