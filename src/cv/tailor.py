"""Expert CV tailoring with Claude API — Stage 6.

Uses a world-class resume strategist prompt to:
1. Analyse the JD deeply (not just keyword matching)
2. Select and rewrite the most relevant bullets from master_profile.yaml
3. Generate a tailored summary, skills section, and bullet points
4. Respect region-based formatting standards
5. Optionally generate a cover letter
6. Build the final ATS-optimised document
"""

import json
import logging
from datetime import datetime

from src.config import (
    AgentConfig, Secrets, MASTER_PROFILE,
    get_profile_summary, get_profile_bullets, get_skills,
)
from src.db.models import JobShortlist, CVVersion
from src.db.session import get_session
from src.cv.builder import build_cv
from src.cv.regions import get_region_format
from src.cv.cover_letter import generate_cover_letter

logger = logging.getLogger(__name__)

# ── The Expert Resume Strategist Prompt ──────────────────────────────
SYSTEM_PROMPT = """You are one of the world's top resume strategists, ATS optimization experts, and career coaches combined into one. You have:

- 20+ years of experience in executive recruiting and talent acquisition
- Deep expertise in Applicant Tracking Systems (ATS) and how they parse, score, and rank resumes
- Extensive knowledge of industry-specific resume conventions across tech, SaaS, finance, consulting, and more
- A proven track record of helping candidates land interviews at top-tier companies

Your approach combines:
1. STRATEGIC THINKING: You don't just match keywords — you understand the hiring manager's underlying needs
2. ACHIEVEMENT FRAMING: You transform responsibilities into measurable impact statements
3. ATS MASTERY: You know exactly how systems like Greenhouse, Lever, Workday, and iCIMS parse resumes
4. PSYCHOLOGICAL INSIGHT: You understand what makes hiring managers stop scrolling and start reading

When tailoring a resume, you follow this rigorous process:

STEP 1 — DEEP JD ANALYSIS
- Identify the PRIMARY mandate (what problem does this role solve?)
- Extract MUST-HAVE vs NICE-TO-HAVE qualifications
- Identify the SENIORITY SIGNALS (years, scope, team size, budget)
- Note CULTURAL INDICATORS (values, work style, team dynamics)
- Map the TECHNICAL STACK precisely
- Understand the BUSINESS CONTEXT (growth stage, market position, challenges)

STEP 2 — STRATEGIC KEYWORD EXTRACTION
- Primary keywords: Job title variations, core technical skills, methodologies
- Secondary keywords: Industry terms, soft skills, tools, certifications
- Hidden keywords: Synonyms the ATS might match (e.g., "revenue" = "sales" = "bookings")
- Contextual keywords: Company-specific language, industry jargon

STEP 3 — BULLET POINT OPTIMIZATION (using the STAR-Q framework)
Every bullet should follow: Situation → Task → Action → Result → Quantification
- Start with powerful, varied action verbs (never repeat the same verb)
- Include at least one metric per bullet where possible
- Mirror JD language naturally (not forced keyword stuffing)
- Show PROGRESSION and GROWTH across roles
- Highlight transferable skills that map to the target role

STEP 4 — SUMMARY/PROFILE CRAFTING
- Open with years of experience + core expertise area
- Include 2-3 headline achievements with numbers
- Mirror the JD's most critical requirements
- End with a forward-looking statement about what you bring

STEP 5 — SKILLS SECTION OPTIMIZATION
- Categorize skills to match JD structure
- Lead with the most relevant skills for this specific role
- Include exact tool/technology names as listed in the JD
- Add complementary skills that strengthen the narrative

CRITICAL RULES:
- NEVER fabricate achievements, metrics, or experiences that don't exist in the source profile
- NEVER inflate numbers — use the exact figures from the master profile
- ALWAYS maintain truthfulness while maximizing relevance
- Adapt LANGUAGE and FRAMING, not facts
- If the candidate lacks a required skill, DO NOT invent it — instead, highlight the closest transferable experience"""


def _build_tailoring_prompt(
    jd_text: str,
    profile: dict,
    region_fmt: dict,
    role: str,
    company: str,
) -> str:
    """Build the user prompt for Claude API with full context."""

    # Format experience for the prompt
    experience_text = ""
    for exp in profile.get("experience", []):
        experience_text += f"\n### {exp.get('title', '')} at {exp.get('company', '')}"
        experience_text += f"\n**Location:** {exp.get('location', 'N/A')}"
        experience_text += f"\n**Dates:** {exp.get('dates', 'N/A')}"
        for bullet in exp.get("bullets", []):
            experience_text += f"\n- {bullet}"
        experience_text += "\n"

    # Format education
    education_text = ""
    for edu in profile.get("education", []):
        education_text += f"\n- {edu.get('degree', '')} — {edu.get('school', '')}"
        if edu.get("dates"):
            education_text += f" ({edu['dates']})"
        if edu.get("thesis"):
            education_text += f"\n  Thesis: {edu['thesis']}"

    # Format skills
    skills = profile.get("skills", {})
    skills_text = ""
    if isinstance(skills, dict):
        for category, items in skills.items():
            if isinstance(items, list):
                skills_text += f"\n**{category.title()}:** {', '.join(items)}"
    elif isinstance(skills, list):
        skills_text = ", ".join(skills)

    # Region instructions
    region_notes = f"""
REGION FORMAT: {region_fmt['name']}
- Document type: {region_fmt['doc_name']}
- Max pages: {region_fmt['max_pages']}
- Section order: {' -> '.join(region_fmt['section_order'])}
- Summary label: {region_fmt['summary_label']}
- Experience label: {region_fmt['experience_label']}
- Skills label: {region_fmt['skills_label']}
- Education label: {region_fmt['education_label']}
- Skills format: {region_fmt['skills_format']}
- Bullet style: {region_fmt['bullet_style']}
- Notes: {region_fmt['notes']}"""

    return f"""TASK: Tailor the following candidate's resume for the target role below. Follow the full 5-step process from your training.

## TARGET ROLE
**Company:** {company}
**Role:** {role}

## JOB DESCRIPTION
{jd_text[:4000]}

## CANDIDATE MASTER PROFILE
**Name:** {profile.get('name', 'Ratin Sharma')}
**Headline:** {profile.get('headline', '')}
**Location:** {profile.get('location', 'Dublin, Ireland')}
**Summary:** {profile.get('summary', '')}

### EXPERIENCE
{experience_text}

### EDUCATION
{education_text}

### SKILLS
{skills_text}

## REGION-SPECIFIC FORMATTING
{region_notes}

## OUTPUT FORMAT
Return a JSON object with this EXACT structure (no markdown, no explanation, ONLY valid JSON):
{{
  "keywords": ["list", "of", "top", "15", "jd", "keywords"],
  "summary": "Tailored professional summary (3-5 lines, mirrors JD language)",
  "experience": [
    {{
      "company": "Company Name",
      "title": "Title from master profile",
      "location": "Location",
      "dates": "Date range",
      "bullets": ["Tailored bullet 1", "Tailored bullet 2", "..."]
    }}
  ],
  "education": [
    {{
      "degree": "Degree",
      "school": "School",
      "dates": "Dates",
      "thesis": "Thesis if relevant, null otherwise"
    }}
  ],
  "skills": {{
    "category_name": ["skill1", "skill2"],
    "another_category": ["skill3", "skill4"]
  }},
  "section_order": ["summary", "experience", "skills", "education"]
}}

IMPORTANT RULES:
- Select the 5-8 MOST RELEVANT bullets per role (not all bullets)
- For {region_fmt['bullet_style']} style bullets: {"focus on quantified achievements with metrics" if region_fmt['bullet_style'] == 'achievement' else "be descriptive but concise" if region_fmt['bullet_style'] == 'detailed' else "keep bullets short and impactful"}
- Respect the max {region_fmt['max_pages']} page limit — be selective
- Use section order: {' -> '.join(region_fmt['section_order'])}
- Skills format: {region_fmt['skills_format']} — {"group skills by category" if region_fmt['skills_format'] == 'categorized' else "list skills with proficiency levels" if region_fmt['skills_format'] == 'detailed' else "simple flat list of skills"}
- NEVER invent new achievements or inflate numbers
- Mirror the JD's exact terminology where natural"""


def _tailor_with_claude(
    jd_text: str,
    profile: dict,
    region_fmt: dict,
    role: str,
    company: str,
) -> dict | None:
    """Call Claude API with the expert prompt. Returns structured tailored data."""
    if not Secrets.ANTHROPIC_API_KEY:
        logger.warning("No ANTHROPIC_API_KEY — falling back to simple tailoring")
        return None

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=Secrets.ANTHROPIC_API_KEY)

        user_prompt = _build_tailoring_prompt(jd_text, profile, region_fmt, role, company)

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        text = response.content[0].text.strip()

        # Handle potential markdown code block wrapping
        if text.startswith("```"):
            # Strip ```json ... ``` wrapper
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

        result = json.loads(text)

        # Validate required fields
        required = ["keywords", "summary", "experience", "skills"]
        for field in required:
            if field not in result:
                logger.error(f"Claude response missing '{field}' field")
                return None

        logger.info(f"Claude tailoring successful — {len(result['keywords'])} keywords, "
                     f"{len(result['experience'])} roles")
        return result

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude JSON response: {e}")
        return None
    except Exception as e:
        logger.error(f"Claude tailoring API call failed: {e}")
        return None


def _fallback_tailor(profile: dict, region_fmt: dict) -> dict:
    """Simple fallback when Claude API is unavailable."""
    experience = []
    for exp in profile.get("experience", []):
        experience.append({
            "company": exp.get("company", ""),
            "title": exp.get("title", ""),
            "location": exp.get("location", ""),
            "dates": exp.get("dates", ""),
            "bullets": exp.get("bullets", [])[:6],  # Limit bullets
        })

    # Flatten skills
    skills_raw = profile.get("skills", {})
    if isinstance(skills_raw, dict):
        skills = {}
        for cat, items in skills_raw.items():
            if isinstance(items, list):
                skills[cat] = items
    else:
        skills = {"core": skills_raw if isinstance(skills_raw, list) else []}

    education = []
    for edu in profile.get("education", []):
        education.append({
            "degree": edu.get("degree", ""),
            "school": edu.get("school", ""),
            "dates": edu.get("dates", ""),
            "thesis": edu.get("thesis"),
        })

    return {
        "keywords": ["SaaS", "B2B", "Account Executive", "sales", "quota"],
        "summary": profile.get("summary", ""),
        "experience": experience,
        "education": education,
        "skills": skills,
        "section_order": region_fmt.get("section_order", ["summary", "experience", "skills", "education"]),
    }


def tailor_cv(job_id: int, generate_cover: bool = True) -> dict:
    """Tailor CV for a specific job. Returns dict with file paths.

    Pipeline:
    1. Load job + detect region format
    2. Call Claude with expert resume strategist prompt
    3. Build ATS-optimised CV document with region formatting
    4. Optionally generate a cover letter
    5. Save to cv_versions table

    Args:
        job_id: ID of the job in job_shortlist table
        generate_cover: Whether to also generate a cover letter

    Returns:
        Dict with keys: cv_path, cover_letter_path (if generated), keywords
    """
    session = get_session()

    try:
        job = session.get(JobShortlist, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        logger.info(f"Tailoring CV for: {job.company} — {job.role}")

        # Step 1: Detect region format
        region_fmt = get_region_format(job.location or "")
        logger.info(f"Region detected: {region_fmt['name']} ({region_fmt['region_key']})")

        # Step 2: Get master profile
        profile = MASTER_PROFILE

        # Step 3: Tailor with Claude (or fallback)
        jd_text = job.description or ""
        tailored = _tailor_with_claude(jd_text, profile, region_fmt, job.role, job.company)

        if tailored is None:
            logger.warning("Using fallback tailoring (no Claude API)")
            tailored = _fallback_tailor(profile, region_fmt)

        keywords = tailored.get("keywords", [])
        logger.info(f"Keywords: {keywords}")

        # Step 4: Build the CV document
        cv_path = build_cv(
            name=profile.get("name", "Ratin Sharma"),
            email=profile.get("email", "ratinsharma99@gmail.com"),
            phone=profile.get("phone", ""),
            linkedin=profile.get("linkedin", ""),
            location=profile.get("location", "Dublin, Ireland"),
            summary=tailored["summary"],
            experience=tailored["experience"],
            education=tailored.get("education", profile.get("education", [])),
            skills=tailored["skills"],
            company=job.company,
            role=job.role,
            region_fmt=region_fmt,
        )

        # Step 5: Generate cover letter if requested
        cover_letter_path = None
        if generate_cover and jd_text:
            try:
                cover_letter_path = generate_cover_letter(
                    profile=profile,
                    job=job,
                    tailored_data=tailored,
                    region_fmt=region_fmt,
                )
                logger.info(f"Cover letter generated: {cover_letter_path}")
            except Exception as e:
                logger.error(f"Cover letter generation failed: {e}")

        # Step 6: Save to cv_versions table
        cv_record = CVVersion(
            job_id=job.id,
            filename=cv_path.split("\\")[-1].split("/")[-1],
            file_path=cv_path,
            tailored_bullets=json.dumps(
                [b for exp in tailored["experience"] for b in exp.get("bullets", [])]
            ),
            keywords_used=json.dumps(keywords),
        )
        session.add(cv_record)
        session.commit()

        logger.info(f"CV tailored and saved: {cv_path}")

        return {
            "cv_path": cv_path,
            "cover_letter_path": cover_letter_path,
            "keywords": keywords,
            "region": region_fmt["name"],
        }

    except Exception as e:
        session.rollback()
        logger.error(f"CV tailoring failed for job {job_id}: {e}")
        raise
    finally:
        session.close()
