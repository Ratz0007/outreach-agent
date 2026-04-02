"""10 variant definitions + weighting for A/B testing.

Three styles, 10 variants. Each uses personalisation tokens that get filled
by the Claude API generator with real context from JD + contact data.
"""

VARIANT_TEMPLATES = {
    "V1": {
        "name": "Referral-Warm",
        "style": "referral",
        "description": "Mutual connection referral ask",
        "template": (
            "Hi {Name}, {Mutual} suggested I connect. I see {Company} is hiring a {Role}. "
            "As an AI/SaaS sales rep with 7+ years closing $750K+, I'd value your advice. "
            "Could you possibly refer me? Can we chat this week?"
        ),
        "requires": ["Name", "Company", "Role"],
        "optional": ["Mutual"],
    },
    "V2": {
        "name": "Referral-Direct",
        "style": "referral",
        "description": "Direct referral ask after applying",
        "template": (
            "Hi {Name}, can you advise? I applied for {Role} at {Company}. "
            "I'm an experienced quota-hitting rep in AI/SaaS. "
            "Would love any tips or referrals. Might you have time for a quick call?"
        ),
        "requires": ["Name", "Company", "Role"],
        "optional": [],
    },
    "V3": {
        "name": "Referral-Value",
        "style": "referral",
        "description": "Referral anchored to company news/achievement",
        "template": (
            "Quick question, {Name}. Congrats on {Company}'s recent {Achievement}! "
            "I helped SMBs scale SaaS sales to 150% quota. "
            "Could a referral get my resume seen? Should I send over my CV?"
        ),
        "requires": ["Name", "Company"],
        "optional": ["Achievement"],
    },
    "V4": {
        "name": "Value-First",
        "style": "value_first",
        "description": "Lead with achievement, ask for chat",
        "template": (
            "{Company} caught my eye for how you're approaching {Topic}. "
            "In 2025 I hit 150% quota selling SaaS to SMBs across Ireland. "
            "With that AI-selling experience, I'd love to discuss fit for {Role}. "
            "Can we set a 10-min chat?"
        ),
        "requires": ["Company", "Role"],
        "optional": ["Topic"],
    },
    "V5": {
        "name": "Value-First-Pitch",
        "style": "value_first",
        "description": "Growth-focused pitch with metrics",
        "template": (
            "Driving SMB growth at {Company}? Hi {Name}, I've taken small startups "
            "to new markets (130% quota, $480K international contracts). "
            "With your product launch, my skills align well. Interested in an intro?"
        ),
        "requires": ["Name", "Company"],
        "optional": [],
    },
    "V6": {
        "name": "Value-Question",
        "style": "value_first",
        "description": "Curiosity-led value exchange",
        "template": (
            "Curious about {Company}'s SMB strategy. I've helped startups expand "
            "EU sales via consultative selling and MEDDIC. "
            "How is {Company} approaching SMB growth? Happy to swap notes!"
        ),
        "requires": ["Company"],
        "optional": [],
    },
    "V7": {
        "name": "Conversational-Post",
        "style": "conversational",
        "description": "Reference their LinkedIn post/content",
        "template": (
            "Enjoyed your recent post on {Topic}. Hi {Name}, I'm a sales professional "
            "in AI/SaaS selling to SMBs. "
            "Any advice on breaking into your industry would be great! Could we connect?"
        ),
        "requires": ["Name"],
        "optional": ["Topic"],
    },
    "V8": {
        "name": "Conversational-Event",
        "style": "conversational",
        "description": "Congratulate on event, ask for advice",
        "template": (
            "Congrats on {Event}, {Name}! I'm exploring roles like {Role} at {Company}. "
            "Can you share what makes a candidate stand out in applications? "
            "Would love 5 mins of advice."
        ),
        "requires": ["Name", "Company", "Role"],
        "optional": ["Event"],
    },
    "V9": {
        "name": "Conversational-Open",
        "style": "conversational",
        "description": "Open-ended ask for application advice",
        "template": (
            "Hi {Name}, quick favour? I noticed {Company} looks for AI-savvy sales reps. "
            "What's the best way to express that fit in an application? "
            "Could you share your thoughts?"
        ),
        "requires": ["Name", "Company"],
        "optional": [],
    },
    "V10": {
        "name": "Conversational-Relational",
        "style": "conversational",
        "description": "Mutual connection, relational ask",
        "template": (
            "Hi {Name}, saw we both know {Mutual}. I'm targeting a {Role} at {Company}. "
            "As someone in sales/AI, I'd appreciate any referral or insight you can offer. "
            "Open to a brief chat?"
        ),
        "requires": ["Name", "Company", "Role"],
        "optional": ["Mutual"],
    },
}


def get_variant_template(variant_id: str) -> dict | None:
    """Get a variant template by ID (V1-V10)."""
    return VARIANT_TEMPLATES.get(variant_id)


def get_variants_by_style(style: str) -> list[str]:
    """Get variant IDs for a given style."""
    return [
        vid for vid, v in VARIANT_TEMPLATES.items()
        if v["style"] == style
    ]


def get_all_active_variant_ids(config_variants: dict) -> list[str]:
    """Get list of active variant IDs from config."""
    return [
        vid for vid, v in config_variants.items()
        if v.get("active", True)
    ]
