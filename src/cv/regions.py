"""Region-based CV/Resume formatting standards.

Every region has different resume conventions:
  - US/Canada: 1 page, no photo, no DOB, no personal details
  - UK/Ireland: 2 pages OK, "CV" not "resume", personal profile section
  - DACH (Germany/Austria/Swiss): Photo expected, DOB, 2-3 pages, detailed
  - Nordics: 1-2 pages, clean/minimal, skills-focused
  - France: Photo common, 1 page preferred, "competences" section
  - Middle East/APAC: 2 pages, photo common, more personal details OK
  - Netherlands: 1-2 pages, no photo, skills-first
  - Remote/EU (generic): 1-2 pages, no photo, EU standard
"""

REGION_FORMATS = {
    "us": {
        "name": "US / North America",
        "doc_name": "Resume",
        "max_pages": 1,
        "include_photo": False,
        "include_dob": False,
        "include_nationality": False,
        "include_address": False,
        "font": "Calibri",
        "font_size": 11,
        "margins_inches": 0.7,
        "section_order": ["summary", "experience", "skills", "education"],
        "summary_label": "Professional Summary",
        "experience_label": "Professional Experience",
        "skills_label": "Skills",
        "education_label": "Education",
        "skills_format": "categorized",  # grouped by category
        "bullet_style": "achievement",  # action + result + metric
        "notes": "1 page max. No personal details. Achievement-heavy bullets.",
    },
    "uk_ireland": {
        "name": "UK / Ireland",
        "doc_name": "CV",
        "max_pages": 2,
        "include_photo": False,
        "include_dob": False,
        "include_nationality": False,
        "include_address": True,
        "font": "Calibri",
        "font_size": 11,
        "margins_inches": 0.7,
        "section_order": ["summary", "experience", "skills", "education"],
        "summary_label": "Personal Profile",
        "experience_label": "Career History",
        "skills_label": "Key Skills",
        "education_label": "Education & Qualifications",
        "skills_format": "categorized",
        "bullet_style": "achievement",
        "notes": "2 pages OK. Called 'CV' not 'resume'. Personal profile section.",
    },
    "dach": {
        "name": "DACH (Germany / Austria / Switzerland)",
        "doc_name": "Lebenslauf",
        "max_pages": 2,
        "include_photo": True,
        "include_dob": True,
        "include_nationality": True,
        "include_address": True,
        "font": "Arial",
        "font_size": 11,
        "margins_inches": 0.8,
        "section_order": ["summary", "experience", "education", "skills"],
        "summary_label": "Professional Profile",
        "experience_label": "Professional Experience",
        "skills_label": "Skills & Competencies",
        "education_label": "Education",
        "skills_format": "detailed",  # with proficiency levels
        "bullet_style": "detailed",  # more descriptive
        "notes": "Photo expected. DOB/nationality included. Education more prominent.",
    },
    "nordics": {
        "name": "Nordics (Sweden / Denmark / Norway / Finland)",
        "doc_name": "CV",
        "max_pages": 2,
        "include_photo": False,
        "include_dob": False,
        "include_nationality": False,
        "include_address": False,
        "font": "Calibri",
        "font_size": 11,
        "margins_inches": 0.8,
        "section_order": ["summary", "skills", "experience", "education"],
        "summary_label": "Profile",
        "experience_label": "Experience",
        "skills_label": "Core Competencies",
        "education_label": "Education",
        "skills_format": "flat",  # simple list
        "bullet_style": "concise",
        "notes": "Clean, minimal design. Skills before experience. Equality-focused.",
    },
    "france": {
        "name": "France",
        "doc_name": "CV",
        "max_pages": 1,
        "include_photo": True,
        "include_dob": True,
        "include_nationality": False,
        "include_address": True,
        "font": "Calibri",
        "font_size": 11,
        "margins_inches": 0.7,
        "section_order": ["summary", "experience", "education", "skills"],
        "summary_label": "Profil Professionnel",
        "experience_label": "Experience Professionnelle",
        "skills_label": "Competences",
        "education_label": "Formation",
        "skills_format": "categorized",
        "bullet_style": "concise",
        "notes": "1 page preferred. Photo common. French section headers if applying in French.",
    },
    "netherlands": {
        "name": "Netherlands",
        "doc_name": "CV",
        "max_pages": 2,
        "include_photo": False,
        "include_dob": False,
        "include_nationality": False,
        "include_address": False,
        "font": "Calibri",
        "font_size": 11,
        "margins_inches": 0.7,
        "section_order": ["summary", "skills", "experience", "education"],
        "summary_label": "Professional Summary",
        "experience_label": "Work Experience",
        "skills_label": "Skills",
        "education_label": "Education",
        "skills_format": "flat",
        "bullet_style": "achievement",
        "notes": "Direct, skills-first. No photo. Similar to Nordics style.",
    },
    "remote_eu": {
        "name": "Remote / EU (Generic)",
        "doc_name": "CV",
        "max_pages": 2,
        "include_photo": False,
        "include_dob": False,
        "include_nationality": False,
        "include_address": False,
        "font": "Calibri",
        "font_size": 11,
        "margins_inches": 0.7,
        "section_order": ["summary", "experience", "skills", "education"],
        "summary_label": "Professional Summary",
        "experience_label": "Experience",
        "skills_label": "Skills & Tools",
        "education_label": "Education",
        "skills_format": "categorized",
        "bullet_style": "achievement",
        "notes": "Generic EU format. No personal details. Achievement-focused.",
    },
}


def detect_region(location: str) -> str:
    """Detect the CV region format from job location string.
    Returns region key (e.g., 'uk_ireland', 'us', 'dach')."""
    loc = (location or "").lower().strip()

    # US / North America
    us_signals = ["united states", "usa", "u.s.", "new york", "san francisco",
                  "california", "texas", "boston", "seattle", "chicago",
                  "los angeles", "canada", "toronto", "vancouver"]
    if any(s in loc for s in us_signals):
        return "us"

    # UK / Ireland
    uk_ie_signals = ["ireland", "dublin", "cork", "galway", "limerick",
                     "london", "manchester", "birmingham", "edinburgh",
                     "united kingdom", "uk", "england", "scotland", "wales",
                     "belfast", "bristol", "leeds", "glasgow"]
    if any(s in loc for s in uk_ie_signals):
        return "uk_ireland"

    # DACH
    dach_signals = ["germany", "deutschland", "berlin", "munich", "frankfurt",
                    "hamburg", "austria", "vienna", "wien", "zurich",
                    "switzerland", "schweiz", "stuttgart", "cologne"]
    if any(s in loc for s in dach_signals):
        return "dach"

    # Nordics
    nordic_signals = ["sweden", "stockholm", "denmark", "copenhagen",
                      "norway", "oslo", "finland", "helsinki"]
    if any(s in loc for s in nordic_signals):
        return "nordics"

    # France
    france_signals = ["france", "paris", "lyon", "marseille", "toulouse"]
    if any(s in loc for s in france_signals):
        return "france"

    # Netherlands
    nl_signals = ["netherlands", "amsterdam", "rotterdam", "the hague",
                  "utrecht", "eindhoven", "dutch"]
    if any(s in loc for s in nl_signals):
        return "netherlands"

    # Remote / EU default
    eu_signals = ["remote", "europe", "eu", "emea", "hybrid"]
    if any(s in loc for s in eu_signals):
        return "remote_eu"

    # Default: UK/Ireland (since Ratin is based there)
    return "uk_ireland"


def get_region_format(location: str) -> dict:
    """Get the full region format config for a location."""
    region_key = detect_region(location)
    return {**REGION_FORMATS[region_key], "region_key": region_key}
