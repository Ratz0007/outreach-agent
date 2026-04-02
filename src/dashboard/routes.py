"""Dashboard routes — all views + API endpoints + auth + settings."""

import json
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import defaultdict

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func

from src.db.session import get_session
from src.db.models import (
    JobShortlist, PeopleMapper, OutreachLog, ResponseTracker, CVVersion,
    ApplicationMemory, PortalConnector,
)
from src.outreach.linkedin import get_linkedin_quota_status
from src.testing.ab_engine import get_variant_performance, evaluate_variants
from src.tracking.response_handler import get_follow_ups_due, get_response_summary
from src.auth import (
    get_current_user, authenticate_user, register_user,
    create_session_token, get_user_settings, save_user_settings,
    COOKIE_NAME,
)

router = APIRouter()
api_router = APIRouter(prefix="/api")

# ── JSON API Helpers ──────────────────────────────────────────────

def _json_error(msg: str, status: int = 400):
    return JSONResponse({"error": msg}, status_code=status)

def _json_success(data: dict = None):
    return JSONResponse(data or {"success": True})

TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

STATUSES = ["shortlisted", "contacted", "follow_up", "applied", "interviewing", "rejected", "offer"]


# ── Helper: parse keywords JSON safely ────────────────────────────

def _parse_keywords(keywords_str):
    if not keywords_str:
        return []
    try:
        return json.loads(keywords_str)
    except (json.JSONDecodeError, TypeError):
        return []


def _ctx(request, extra=None):
    """Build template context with user info."""
    ctx = {"request": request, "user": get_current_user(request)}
    if extra:
        ctx.update(extra)
    return ctx


def _render(name: str, context: dict):
    """Render a Jinja2 template — compatible with all Starlette versions.

    Newer Starlette requires `request` as a separate keyword argument.
    """
    request = context.get("request")
    return templates.TemplateResponse(request=request, name=name, context=context)


# ── Dashboard Helpers ─────────────────────────────────────────────

def _build_recent_activity(session, today_start):
    """Build recent activity timeline for dashboard."""
    activities = []

    # Recent outreach (sent messages)
    recent_sent = session.query(OutreachLog).filter(OutreachLog.user_id == (user.id if user else 1), 
        OutreachLog.status.in_(["sent", "replied"])
    ).order_by(OutreachLog.sent_at.desc()).limit(5).all()
    for o in recent_sent:
        person = session.query(PeopleMapper).filter(PeopleMapper.id == o.person_id, PeopleMapper.user_id == (user.id if user else 1)).first() if o.person_id else None
        activities.append({
            "type": "sent",
            "title": f"Message sent to {person.name if person else 'contact'}",
            "desc": f"{person.company if person else ''} via {o.channel or 'email'}",
            "time": o.sent_at.strftime("%b %d %H:%M") if o.sent_at else "",
            "sort": o.sent_at or o.created_at,
        })

    # Recent responses
    recent_responses = session.query(ResponseTracker).filter(ResponseTracker.user_id == (user.id if user else 1)).order_by(
        ResponseTracker.created_at.desc()).limit(3).all()
    for r in recent_responses:
        person = session.query(PeopleMapper).filter(PeopleMapper.id == r.person_id, PeopleMapper.user_id == (user.id if user else 1)).first() if r.person_id else None
        activities.append({
            "type": "reply",
            "title": f"{r.response_type.title() if r.response_type else 'Response'} from {person.name if person else 'contact'}",
            "desc": r.action_taken or "",
            "time": r.created_at.strftime("%b %d %H:%M") if r.created_at else "",
            "sort": r.created_at,
        })

    # Recent jobs sourced
    recent_jobs_sourced = session.query(JobShortlist).filter(JobShortlist.user_id == (user.id if user else 1)).order_by(
        JobShortlist.created_at.desc()).limit(3).all()
    for j in recent_jobs_sourced:
        activities.append({
            "type": "job",
            "title": f"New job: {j.role}",
            "desc": f"{j.company} - {j.location or ''}",
            "time": j.created_at.strftime("%b %d %H:%M") if j.created_at else "",
            "sort": j.created_at,
        })

    # Recent drafts
    recent_drafts = session.query(OutreachLog).filter(OutreachLog.user_id == (user.id if user else 1), 
        OutreachLog.status == "draft"
    ).order_by(OutreachLog.created_at.desc()).limit(3).all()
    for d in recent_drafts:
        person = session.query(PeopleMapper).filter(PeopleMapper.id == d.person_id, PeopleMapper.user_id == (user.id if user else 1)).first() if d.person_id else None
        activities.append({
            "type": "draft",
            "title": f"Draft created for {person.name if person else 'contact'}",
            "desc": f"{d.variant} ({d.style})",
            "time": d.created_at.strftime("%b %d %H:%M") if d.created_at else "",
            "sort": d.created_at,
        })

    # Sort by time descending
    activities.sort(key=lambda x: x.get("sort") or datetime.min, reverse=True)
    # Remove sort key from output
    for a in activities:
        a.pop("sort", None)
    return activities[:10]


def _build_priority_queue(session, today_start):
    """Build prioritised action queue for dashboard."""
    queue = []

    # 1. Pending drafts needing review
    draft_count = session.query(func.count(OutreachLog.id)).filter(OutreachLog.user_id == (user.id if user else 1), 
        OutreachLog.status == "draft").scalar() or 0
    if draft_count > 0:
        queue.append({
            "title": f"{draft_count} drafts awaiting review",
            "desc": "Review and approve outreach messages",
            "link": "/outreach?status=draft",
            "urgency": "warning",
            "badge": "Review",
        })

    # 2. Approved messages ready to send
    approved_count = session.query(func.count(OutreachLog.id)).filter(OutreachLog.user_id == (user.id if user else 1), 
        OutreachLog.status == "approved").scalar() or 0
    if approved_count > 0:
        queue.append({
            "title": f"{approved_count} messages ready to send",
            "desc": "Approved and waiting for dispatch",
            "link": "/outreach?status=approved",
            "urgency": "urgent",
            "badge": "Send",
        })

    # 3. Overdue follow-ups
    follow_ups = get_follow_ups_due()
    if follow_ups:
        queue.append({
            "title": f"{len(follow_ups)} overdue follow-ups",
            "desc": "Contacts need follow-up messages",
            "link": "/contacts",
            "urgency": "urgent",
            "badge": "Overdue",
        })

    # 4. High-score uncontacted jobs
    high_score_jobs = session.query(JobShortlist).filter(JobShortlist.user_id == (user.id if user else 1), 
        JobShortlist.status == "shortlisted",
        JobShortlist.fit_score >= 7,
        JobShortlist.is_tier1 == False,
    ).order_by(JobShortlist.fit_score.desc()).limit(5).all()
    for job in high_score_jobs:
        queue.append({
            "title": f"{job.company} — {job.role}",
            "desc": f"Fit score {job.fit_score}/10, not yet contacted",
            "link": f"/jobs#job-{job.id}",
            "urgency": "info",
            "badge": f"Score {job.fit_score}",
        })

    # 5. Jobs with no contacts enriched
    jobs_no_contacts = session.query(JobShortlist).filter(JobShortlist.user_id == (user.id if user else 1), 
        JobShortlist.status == "shortlisted",
        JobShortlist.is_tier1 == False,
        ~JobShortlist.id.in_(
            session.query(PeopleMapper.job_id).filter(PeopleMapper.job_id.isnot(None))
        ),
    ).limit(3).all()
    for job in jobs_no_contacts:
        queue.append({
            "title": f"{job.company} needs contacts",
            "desc": f"{job.role} — run enrichment",
            "link": f"/jobs#job-{job.id}",
            "urgency": "info",
            "badge": "Enrich",
        })

    return queue


def _get_api_health():
    """Check which API keys are configured."""
    from src.config import Secrets

    services = [
        ("Adzuna", bool(getattr(Secrets, "ADZUNA_APP_ID", "") and getattr(Secrets, "ADZUNA_APP_KEY", ""))),
        ("Hunter", bool(getattr(Secrets, "HUNTER_API_KEY", ""))),
        ("Apollo", bool(getattr(Secrets, "APOLLO_API_KEY", ""))),
        ("Snov.io", bool(getattr(Secrets, "SNOV_USER_ID", "") and getattr(Secrets, "SNOV_SECRET", ""))),
        ("Claude AI", bool(getattr(Secrets, "ANTHROPIC_API_KEY", ""))),
        ("Gmail", bool(getattr(Secrets, "GMAIL_CLIENT_ID", ""))),
    ]

    result = []
    for name, configured in services:
        result.append({
            "name": name,
            "status": "healthy" if configured else "unknown",
            "detail": "Key set" if configured else "Not configured",
        })
    return result


# ── Auth Routes ───────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/", status_code=303)
    return _render("login.html", {"request": request})


@router.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    user = authenticate_user(username, password)
    if not user:
        return _render("login.html", {
            "request": request, "error": "Invalid username or password", "username": username,
        })
    token = create_session_token(user.id)
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(COOKIE_NAME, token, max_age=86400 * 7, httponly=True, samesite="lax")
    return response


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/", status_code=303)
    return _render("register.html", {"request": request})


@router.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
):
    if len(password) < 6:
        return _render("register.html", {
            "request": request, "error": "Password must be at least 6 characters",
            "full_name": full_name, "email": email, "username": username,
        })

    result = register_user(username, email, password, full_name)
    if isinstance(result, str):
        return _render("register.html", {
            "request": request, "error": result,
            "full_name": full_name, "email": email, "username": username,
        })

    # Auto-login after registration
    token = create_session_token(result.id)
    response = RedirectResponse(url="/settings", status_code=303)
    response.set_cookie(COOKIE_NAME, token, max_age=86400 * 7, httponly=True, samesite="lax")
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


# ── Settings ──────────────────────────────────────────────────────

@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, success: str = ""):
    user = get_current_user(request)

    # Build settings dict — works for both logged-in and guest users
    s: dict = {}
    if user:
        s = get_user_settings(user.id)

    # Pre-fill from current config if settings are empty
    if not s:
        try:
            from src.config import Secrets, AgentConfig, TIER1_COMPANIES
            s = {
                "full_name": (user.full_name if user else "") or "",
                "profile_email": (user.email if user else "") or "",
                "linkedin_url": (getattr(user, "linkedin_url", "") if user else "") or "",
                "anthropic_api_key": Secrets.ANTHROPIC_API_KEY,
                "adzuna_app_id": Secrets.ADZUNA_APP_ID,
                "adzuna_app_key": Secrets.ADZUNA_APP_KEY,
                "apollo_api_key": Secrets.APOLLO_API_KEY,
                "hunter_api_key": Secrets.HUNTER_API_KEY,
                "snov_user_id": Secrets.SNOV_USER_ID,
                "snov_secret": Secrets.SNOV_SECRET,
                "gmail_client_id": Secrets.GMAIL_CLIENT_ID,
                "gmail_client_secret": Secrets.GMAIL_CLIENT_SECRET,
                "gmail_refresh_token": Secrets.GMAIL_REFRESH_TOKEN,
                "linkedin_client_id": Secrets.LINKEDIN_CLIENT_ID,
                "linkedin_client_secret": Secrets.LINKEDIN_CLIENT_SECRET,
                "linkedin_access_token": Secrets.LINKEDIN_ACCESS_TOKEN,
                "search_roles": ", ".join(AgentConfig.roles),
                "search_locations": ", ".join(AgentConfig.locations),
                "search_industries": ", ".join(AgentConfig.industries),
                "exclude_keywords": ", ".join(AgentConfig.exclude_keywords),
                "daily_message_limit": AgentConfig.daily_message_limit,
                "daily_linkedin_limit": AgentConfig.daily_linkedin_invite_limit,
                "weekly_linkedin_limit": AgentConfig.weekly_linkedin_invite_limit,
                "follow_up_days": AgentConfig.follow_up_days,
                "max_follow_ups": AgentConfig.max_follow_ups,
                "max_contacts_per_company": AgentConfig.max_contacts_per_company,
                "min_sends_per_variant": AgentConfig.min_sends_per_variant,
                "min_total_replies": AgentConfig.min_total_replies_to_evaluate,
                "kill_threshold": AgentConfig.kill_threshold_pct,
                "boost_threshold": AgentConfig.winner_boost_threshold_pct,
                "min_active_variants": AgentConfig.min_active_variants,
                "tier1_companies": "\n".join(TIER1_COMPANIES),
            }
        except Exception:
            s = {}

    return _render("settings.html", _ctx(request, {"s": s, "success": bool(success)}))


@router.post("/settings")
async def settings_save(request: Request):
    user = get_current_user(request)

    form = await request.form()
    settings = {}
    for key in form:
        settings[key] = form[key]

    if user:
        # Save to user settings in DB
        save_user_settings(user.id, settings)

        # Update user profile
        user = get_current_user(request) if 'request' in locals() else None

        session = get_session()
        try:
            u = session.get(type(user), user.id)
            if u:
                u.full_name = settings.get("full_name", u.full_name)
                u.email = settings.get("profile_email", u.email)
                u.linkedin_url = settings.get("linkedin_url", u.linkedin_url)
                session.commit()
        finally:
            session.close()

    # Also update .env file with API keys (works for all users)
    # _update_env_file(settings)  # Disabled for multi-tenancy

    return RedirectResponse(url="/settings?success=1", status_code=303)


def _update_env_file(settings):
    """Update .env file with API key values from settings form."""
    from src.config import PROJECT_ROOT
    env_path = PROJECT_ROOT / ".env"

    env_map = {
        "ANTHROPIC_API_KEY": settings.get("anthropic_api_key", ""),
        "ADZUNA_APP_ID": settings.get("adzuna_app_id", ""),
        "ADZUNA_APP_KEY": settings.get("adzuna_app_key", ""),
        "APOLLO_API_KEY": settings.get("apollo_api_key", ""),
        "HUNTER_API_KEY": settings.get("hunter_api_key", ""),
        "SNOV_USER_ID": settings.get("snov_user_id", ""),
        "SNOV_SECRET": settings.get("snov_secret", ""),
        "GMAIL_CLIENT_ID": settings.get("gmail_client_id", ""),
        "GMAIL_CLIENT_SECRET": settings.get("gmail_client_secret", ""),
        "GMAIL_REFRESH_TOKEN": settings.get("gmail_refresh_token", ""),
        "LINKEDIN_CLIENT_ID": settings.get("linkedin_client_id", ""),
        "LINKEDIN_CLIENT_SECRET": settings.get("linkedin_client_secret", ""),
        "LINKEDIN_ACCESS_TOKEN": settings.get("linkedin_access_token", ""),
    }

    lines = []
    if env_path.exists():
        with open(env_path, "r") as f:
            lines = f.readlines()

    # Update existing keys or add new ones
    existing_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip()
            if key in env_map:
                val = env_map[key]
                if val:  # Only update if value is non-empty
                    new_lines.append(f"{key}={val}\n")
                else:
                    new_lines.append(line)  # Keep existing
                existing_keys.add(key)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    # Add any missing keys
    for key, val in env_map.items():
        if key not in existing_keys and val:
            new_lines.append(f"{key}={val}\n")

    with open(env_path, "w") as f:
        f.writelines(new_lines)


# ── Home / Dashboard ──────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0)
        # Week start (Monday) for weekly goals
        _now = datetime.utcnow()
        week_start = (_now - timedelta(days=_now.weekday())).replace(hour=0, minute=0, second=0)
        import math
        week_number = math.ceil(_now.timetuple().tm_yday / 7)

        pipeline = {}
        for s in STATUSES:
            pipeline[s] = session.query(func.count(JobShortlist.id)).filter(JobShortlist.user_id == (user.id if user else 1), 
                JobShortlist.status == s).scalar() or 0

        recent_jobs = session.query(JobShortlist).filter(JobShortlist.user_id == (user.id if user else 1)).order_by(
            JobShortlist.fit_score.desc(), JobShortlist.created_at.desc()
        ).limit(8).all()

        # Variant performance for chart
        variant_stats = get_variant_performance()
        variant_chart = {
            "labels": [v.variant_id for v in variant_stats],
            "sends": [v.sends for v in variant_stats],
            "replies": [v.replies for v in variant_stats],
            "styles": [v.style for v in variant_stats],
        }

        # Outreach status breakdown for donut chart
        outreach_statuses = session.query(
            OutreachLog.status, func.count(OutreachLog.id)
        ).group_by(OutreachLog.status).all()
        outreach_chart = {
            "labels": [s[0] for s in outreach_statuses],
            "counts": [s[1] for s in outreach_statuses],
        }

        # Activity over last 7 days for line chart
        activity_days = []
        activity_jobs = []
        activity_sent = []
        for i in range(6, -1, -1):
            day = datetime.utcnow().replace(hour=0, minute=0, second=0) - timedelta(days=i)
            day_end = day + timedelta(days=1)
            activity_days.append(day.strftime("%a"))
            activity_jobs.append(
                session.query(func.count(JobShortlist.id)).filter(JobShortlist.user_id == (user.id if user else 1), 
                    JobShortlist.created_at >= day, JobShortlist.created_at < day_end
                ).scalar() or 0
            )
            activity_sent.append(
                session.query(func.count(OutreachLog.id)).filter(OutreachLog.user_id == (user.id if user else 1), 
                    OutreachLog.created_at >= day, OutreachLog.created_at < day_end
                ).scalar() or 0
            )
        activity_chart = {"days": activity_days, "jobs": activity_jobs, "sent": activity_sent}

        # Schedule config
        from src.config import AgentConfig
        schedule = AgentConfig.schedule

        # Priority action queue
        priority_queue = _build_priority_queue(session, today_start)

        # API health status
        api_health = _get_api_health()

        # Recent activity timeline
        recent_activity = _build_recent_activity(session, today_start)

        # Memory / search preferences
        from src.config import AgentConfig
        memory_data = {
            "roles": getattr(AgentConfig, "search_roles", []),
            "locations": getattr(AgentConfig, "search_locations", []),
            "industries": getattr(AgentConfig, "search_industries", []),
        }

        stats = {
            "total_jobs": session.query(func.count(JobShortlist.id)).filter(JobShortlist.user_id == (user.id if user else 1)).scalar() or 0,
            "jobs_today": session.query(func.count(JobShortlist.id)).filter(JobShortlist.user_id == (user.id if user else 1), 
                JobShortlist.created_at >= today_start).scalar() or 0,
            "total_contacts": session.query(func.count(PeopleMapper.id)).filter(PeopleMapper.user_id == (user.id if user else 1)).scalar() or 0,
            "drafts": session.query(func.count(OutreachLog.id)).filter(OutreachLog.user_id == (user.id if user else 1), 
                OutreachLog.status == "draft").scalar() or 0,
            "approved": session.query(func.count(OutreachLog.id)).filter(OutreachLog.user_id == (user.id if user else 1), 
                OutreachLog.status == "approved").scalar() or 0,
            "sent": session.query(func.count(OutreachLog.id)).filter(OutreachLog.user_id == (user.id if user else 1), 
                OutreachLog.status.in_(["sent", "replied"])).scalar() or 0,
            "sent_today": session.query(func.count(OutreachLog.id)).filter(OutreachLog.user_id == (user.id if user else 1), 
                OutreachLog.sent_at >= today_start,
                OutreachLog.status.in_(["sent", "replied"])).scalar() or 0,
            "replies": session.query(func.count(ResponseTracker.id)).filter(ResponseTracker.user_id == (user.id if user else 1)).scalar() or 0,
            "referrals": session.query(func.count(ResponseTracker.id)).filter(ResponseTracker.user_id == (user.id if user else 1), 
                ResponseTracker.response_type == "referral").scalar() or 0,
            "linkedin": get_linkedin_quota_status(),
            "follow_ups_due": len(get_follow_ups_due()),
            "cvs": session.query(func.count(CVVersion.id)).filter(CVVersion.user_id == (user.id if user else 1)).scalar() or 0,
            "pipeline": pipeline,
            "recent_jobs": recent_jobs,
            "variant_chart": variant_chart,
            "outreach_chart": outreach_chart,
            "activity_chart": activity_chart,
            "schedule": schedule,
            "priority_queue": priority_queue,
            "api_health": api_health,
            "recent_activity": recent_activity,
            "memory": memory_data,
            "week_number": week_number,
            "weekly_sent": session.query(func.count(OutreachLog.id)).filter(OutreachLog.user_id == (user.id if user else 1), 
                OutreachLog.sent_at >= week_start,
                OutreachLog.status.in_(["sent", "replied"])).scalar() or 0,
            "weekly_jobs": session.query(func.count(JobShortlist.id)).filter(JobShortlist.user_id == (user.id if user else 1), 
                JobShortlist.created_at >= week_start).scalar() or 0,
            "weekly_replies": session.query(func.count(ResponseTracker.id)).filter(ResponseTracker.user_id == (user.id if user else 1), 
                ResponseTracker.response_date >= week_start).scalar() or 0,
            "weekly_applied": session.query(func.count(JobShortlist.id)).filter(JobShortlist.user_id == (user.id if user else 1), 
                JobShortlist.status == "applied",
                JobShortlist.updated_at >= week_start).scalar() or 0,
        }
        return _render("dashboard.html", _ctx(request, {"stats": stats}))
    finally:
        session.close()


# ── Jobs ──────────────────────────────────────────────────────────

@router.get("/jobs", response_class=HTMLResponse)
def jobs_view(request: Request, status: str = "", tier: str = ""):
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        query = session.query(JobShortlist).filter(JobShortlist.user_id == (user.id if user else 1)).order_by(
            JobShortlist.fit_score.desc(), JobShortlist.created_at.desc()
        )
        if status:
            query = query.filter(JobShortlist.status == status)
        if tier:
            query = query.filter(JobShortlist.tier == int(tier))
        jobs = query.all()

        for job in jobs:
            job.keywords_list = _parse_keywords(job.keywords)

        avg_fit = sum(j.fit_score or 0 for j in jobs) / len(jobs) if jobs else 0
        tier1_count = sum(1 for j in jobs if j.is_tier1)

        return _render("jobs.html", _ctx(request, {
            "jobs": jobs, "statuses": STATUSES,
            "current_status": status, "current_tier": tier,
            "avg_fit": avg_fit, "tier1_count": tier1_count,
        }))
    finally:
        session.close()


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail(request: Request, job_id: int):
    return RedirectResponse(url=f"/jobs#job-{job_id}", status_code=303)


@router.post("/api/jobs/add")
async def api_add_job(request: Request):
    """Add a job manually via JSON API."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "message": "Invalid JSON"}, status_code=400)

    company = (body.get("company") or "").strip()
    role = (body.get("role") or "").strip()
    if not company or not role:
        return JSONResponse({"status": "error", "message": "Company and role are required"}, status_code=400)

    user = get_current_user(request) if 'request' in locals() else None


    session = get_session()
    try:
        # Check for tier1
        try:
            from src.config import TIER1_COMPANIES
            is_tier1 = company.lower() in [c.lower() for c in TIER1_COMPANIES]
        except Exception:
            is_tier1 = False

        job = JobShortlist(
            company=company,
            role=role,
            location=body.get("location", ""),
            industry=body.get("industry", ""),
            company_stage=body.get("company_stage", ""),
            tier=int(body.get("tier", 2)),
            fit_score=int(body.get("fit_score", 5)),
            status="shortlisted",
            application_link=body.get("application_link", ""),
            description=body.get("description", ""),
            is_tier1=is_tier1,
            source="manual",
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        return JSONResponse({
            "status": "ok",
            "message": f"Added {company} — {role}",
            "job_id": job.id,
            "is_tier1": is_tier1,
        })
    finally:
        session.close()


@router.post("/api/jobs/import-csv")
async def api_import_csv(request: Request):
    """Import jobs from CSV via multipart form upload."""
    import csv
    import io

    form = await request.form()
    file = form.get("file")
    if not file:
        return JSONResponse({"status": "error", "message": "No file uploaded"}, status_code=400)

    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    user = get_current_user(request) if 'request' in locals() else None


    session = get_session()
    added = 0
    skipped = 0
    try:
        for row in reader:
            company = (row.get("company") or row.get("Company") or "").strip()
            role = (row.get("role") or row.get("Role") or row.get("title") or row.get("Title") or "").strip()
            if not company or not role:
                skipped += 1
                continue

            # Deduplicate
            exists = session.query(JobShortlist).filter(JobShortlist.user_id == (user.id if user else 1), 
                JobShortlist.company == company,
                JobShortlist.role == role,
            ).first()
            if exists:
                skipped += 1
                continue

            job = JobShortlist(
                company=company,
                role=role,
                location=(row.get("location") or row.get("Location") or "").strip(),
                industry=(row.get("industry") or row.get("Industry") or "").strip(),
                status="shortlisted",
                source=form.get("source", "csv"),
                application_link=(row.get("link") or row.get("url") or row.get("URL") or "").strip(),
            )
            session.add(job)
            added += 1

        session.commit()
        return JSONResponse({
            "status": "ok",
            "message": f"Imported {added} jobs ({skipped} skipped/duplicates)",
            "added": added,
            "skipped": skipped,
        })
    except Exception as e:
        session.rollback()
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        session.close()


@router.post("/jobs/{job_id}/status")
def update_job_status(request: Request, job_id: int, status: str = Form(...)):
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        job = session.query(JobShortlist).filter(JobShortlist.id == job_id, JobShortlist.user_id == (user.id if user else 1)).first()
        if job:
            job.status = status
            job.updated_at = datetime.utcnow()
            session.commit()
    finally:
        session.close()
    return RedirectResponse(url="/jobs", status_code=303)


@router.post("/jobs/{job_id}/apply")
def apply_to_job(request: Request, job_id: int):
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        job = session.query(JobShortlist).filter(JobShortlist.id == job_id, JobShortlist.user_id == (user.id if user else 1)).first()
        if job:
            job.status = "applied"
            job.updated_at = datetime.utcnow()
            session.commit()
            if job.application_link:
                return RedirectResponse(url=job.application_link, status_code=303)
    finally:
        session.close()
    return RedirectResponse(url="/jobs?status=applied", status_code=303)


# ── Contacts ──────────────────────────────────────────────────────

@router.get("/contacts", response_class=HTMLResponse)
def contacts_view(request: Request):
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        contacts = session.query(PeopleMapper).filter(PeopleMapper.user_id == (user.id if user else 1)).order_by(
            PeopleMapper.company, PeopleMapper.priority).all()

        all_contacts = []
        by_company = {}
        for c in contacts:
            job = session.query(JobShortlist).filter(JobShortlist.id == c.job_id, JobShortlist.user_id == (user.id if user else 1)).first() if c.job_id else None
            c.job_role = job.role if job else None
            c.job_link = job.application_link if job else None
            c.job_location = job.location if job else None
            all_contacts.append(c)

            key = c.company or "Unknown"
            if key not in by_company:
                by_company[key] = []
            by_company[key].append(c)

        return _render("contacts.html", _ctx(request, {
            "contacts": contacts, "all_contacts": all_contacts, "by_company": by_company,
        }))
    finally:
        session.close()


# ── Contact Detail (CRM Timeline) ─────────────────────────────────

@router.get("/contacts/{contact_id}", response_class=HTMLResponse)
def contact_detail(request: Request, contact_id: int):
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        person = session.query(PeopleMapper).filter(PeopleMapper.id == contact_id, PeopleMapper.user_id == (user.id if user else 1)).first()
        if not person:
            return RedirectResponse(url="/contacts", status_code=303)

        job = session.query(JobShortlist).filter(JobShortlist.id == person.job_id, JobShortlist.user_id == (user.id if user else 1)).first() if person.job_id else None

        # Get all outreach for this contact
        outreach = session.query(OutreachLog).filter(OutreachLog.user_id == (user.id if user else 1), 
            OutreachLog.person_id == contact_id
        ).order_by(OutreachLog.created_at.desc()).all()

        # Get all responses for this contact
        responses = session.query(ResponseTracker).filter(ResponseTracker.user_id == (user.id if user else 1), 
            ResponseTracker.person_id == contact_id
        ).order_by(ResponseTracker.created_at.desc()).all()

        # Build timeline events
        timeline = []

        # Contact created
        timeline.append({
            "type": "created",
            "date": person.created_at,
            "title": "Contact added",
            "desc": f"Added from {person.source or 'unknown'} source. Priority {person.priority or '?'}.",
            "icon": "person",
            "color": "blue",
        })

        # Outreach events
        for o in outreach:
            if o.status == "draft":
                timeline.append({
                    "type": "draft",
                    "date": o.created_at,
                    "title": f"Draft created ({o.variant})",
                    "desc": f"{o.style} style via {o.channel}. {(o.message_body or '')[:120]}...",
                    "icon": "edit",
                    "color": "gray",
                })
            if o.status in ("approved",):
                timeline.append({
                    "type": "approved",
                    "date": o.created_at,
                    "title": f"Message approved ({o.variant})",
                    "desc": f"Ready to send via {o.channel}",
                    "icon": "check",
                    "color": "blue",
                })
            if o.sent_at:
                timeline.append({
                    "type": "sent",
                    "date": o.sent_at,
                    "title": f"Message sent ({o.variant})",
                    "desc": f"Sent via {o.channel}. {o.style} style. Follow-up: {o.follow_up_date or 'N/A'}",
                    "icon": "send",
                    "color": "green",
                })
            if o.follow_up_date and o.follow_up_count and o.follow_up_count > 0:
                timeline.append({
                    "type": "followup",
                    "date": datetime.combine(o.follow_up_date, datetime.min.time()) if isinstance(o.follow_up_date, date) else o.follow_up_date,
                    "title": f"Follow-up #{o.follow_up_count}",
                    "desc": f"Follow-up sent via {o.channel}",
                    "icon": "repeat",
                    "color": "amber",
                })

        # Response events
        for r in responses:
            timeline.append({
                "type": "response",
                "date": r.response_date or r.created_at,
                "title": f"Response: {(r.response_type or 'unknown').replace('_', ' ').title()}",
                "desc": f"Action: {(r.action_taken or 'pending').replace('_', ' ')}. {r.notes or ''}",
                "icon": "reply",
                "color": "purple" if r.response_type == "referral" else "emerald" if r.response_type == "interest" else "red",
            })

        # Sort timeline by date (newest first)
        timeline.sort(key=lambda x: x["date"] or datetime.min, reverse=True)

        return _render("contact_detail.html", _ctx(request, {
            "person": person,
            "job": job,
            "outreach": outreach,
            "responses": responses,
            "timeline": timeline,
        }))
    finally:
        session.close()


# ── Outreach ──────────────────────────────────────────────────────

@router.get("/outreach", response_class=HTMLResponse)
def outreach_view(request: Request, status: str = ""):
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        query = session.query(OutreachLog).filter(OutreachLog.user_id == (user.id if user else 1)).order_by(OutreachLog.created_at.desc())
        if status:
            query = query.filter(OutreachLog.status == status)
        outreach = query.all()

        enriched = []
        for o in outreach:
            person = session.query(PeopleMapper).filter(PeopleMapper.id == o.person_id, PeopleMapper.user_id == (user.id if user else 1)).first()
            job = session.query(JobShortlist).filter(JobShortlist.id == o.job_id, JobShortlist.user_id == (user.id if user else 1)).first()
            enriched.append({
                "id": o.id,
                "person_name": person.name if person else "?",
                "person_title": person.title if person else "",
                "person_email": person.email if person else "",
                "linkedin_url": person.linkedin_url if person else "",
                "company": person.company if person else "?",
                "job_role": job.role if job else "?",
                "variant": o.variant,
                "style": o.style,
                "channel": o.channel,
                "message": o.message_body,
                "status": o.status,
                "sent_at": o.sent_at,
                "follow_up_date": o.follow_up_date,
            })
        return _render("outreach.html", _ctx(request, {
            "outreach": enriched, "current_status": status,
        }))
    finally:
        session.close()


@router.post("/outreach/{outreach_id}/approve")
def approve_outreach(request: Request, outreach_id: int):
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        o = session.query(OutreachLog).filter(OutreachLog.id == outreach_id, OutreachLog.user_id == (user.id if user else 1)).first()
        if o and o.status == "draft":
            o.status = "approved"
            session.commit()
    finally:
        session.close()
    return RedirectResponse(url="/outreach?status=draft", status_code=303)


@router.post("/outreach/{outreach_id}/send")
def send_outreach(request: Request, outreach_id: int):
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        o = session.query(OutreachLog).filter(OutreachLog.id == outreach_id, OutreachLog.user_id == (user.id if user else 1)).first()
        if not o or o.status != "approved":
            return RedirectResponse(url="/outreach", status_code=303)

        if o.channel == "email":
            from src.outreach.gmail import send_single_email
            send_single_email(outreach_id)
        else:
            from src.outreach.linkedin import mark_linkedin_sent
            mark_linkedin_sent(outreach_id)
    finally:
        session.close()
    return RedirectResponse(url="/outreach", status_code=303)


@router.post("/outreach/approve-all")
def approve_all_drafts(request: Request, ):
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        drafts = session.query(OutreachLog).filter(OutreachLog.user_id == (user.id if user else 1), OutreachLog.status == "draft").all()
        for d in drafts:
            d.status = "approved"
        session.commit()
    finally:
        session.close()
    return RedirectResponse(url="/outreach?status=approved", status_code=303)


# ── Analytics ─────────────────────────────────────────────────────

@router.get("/analytics", response_class=HTMLResponse)
def analytics_view(request: Request):
    stats = get_variant_performance()
    recs = evaluate_variants()
    response_summary = get_response_summary()

    return _render("analytics.html", _ctx(request, {
        "variant_stats": stats,
        "recommendations": recs,
        "response_summary": response_summary,
    }))


# ── CVs ───────────────────────────────────────────────────────────

@router.get("/cvs", response_class=HTMLResponse)
def cvs_view(request: Request):
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        cvs = session.query(CVVersion).filter(CVVersion.user_id == (user.id if user else 1)).order_by(CVVersion.created_at.desc()).all()
        enriched = []
        for cv in cvs:
            job = session.query(JobShortlist).filter(JobShortlist.id == cv.job_id, JobShortlist.user_id == (user.id if user else 1)).first()
            keywords = _parse_keywords(cv.keywords_used)
            enriched.append({
                "id": cv.id,
                "company": job.company if job else "?",
                "role": job.role if job else "?",
                "filename": cv.filename,
                "file_path": cv.file_path,
                "keywords": keywords,
                "created_at": cv.created_at,
            })
        return _render("cv.html", _ctx(request, {"cvs": enriched}))
    finally:
        session.close()


@router.get("/cvs/download/{cv_id}")
def download_cv(request: Request, cv_id: int):
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        cv = session.query(CVVersion).filter(CVVersion.id == cv_id, CVVersion.user_id == (user.id if user else 1)).first()
        if cv and cv.file_path:
            return FileResponse(cv.file_path, filename=cv.filename)
    finally:
        session.close()
    return RedirectResponse(url="/cvs", status_code=303)


@router.post("/cvs/generate/{job_id}")
def generate_cv(request: Request, job_id: int):
    from src.cv.tailor import tailor_cv
    result = tailor_cv(job_id, generate_cover=True)
    return RedirectResponse(url="/cvs", status_code=303)


# ── Applications ──────────────────────────────────────────────────

@router.get("/applications", response_class=HTMLResponse)
def applications_view(request: Request):
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        from src.db.models import ApplicationMemory, PortalConnector

        apps_raw = session.query(ApplicationMemory).filter(ApplicationMemory.user_id == (user.id if user else 1)).order_by(
            ApplicationMemory.updated_at.desc()
        ).all()

        applications = []
        for app in apps_raw:
            job = session.query(JobShortlist).filter(JobShortlist.id == app.job_id, JobShortlist.user_id == (user.id if user else 1)).first()
            applications.append({
                "id": app.id,
                "job_id": app.job_id,
                "company": job.company if job else "?",
                "role": job.role if job else "?",
                "portal": app.portal,
                "portal_status": app.portal_status,
                "application_url": app.application_url,
                "steps_completed": json.loads(app.steps_completed) if app.steps_completed else [],
                "steps_remaining": json.loads(app.steps_remaining) if app.steps_remaining else [],
                "blocked_reason": app.blocked_reason,
                "blocked_step": app.blocked_step,
                "ai_summary": app.ai_summary,
                "last_action": app.last_action,
                "last_action_at": app.last_action_at,
                "documents": json.loads(app.documents_uploaded) if app.documents_uploaded else [],
                "created_at": app.created_at,
                "updated_at": app.updated_at,
            })

        portals = session.query(PortalConnector).order_by(
            PortalConnector.support_level.desc()
        ).all() if session.query(PortalConnector).count() > 0 else []

        stats = {
            "total": len(applications),
            "completed": sum(1 for a in applications if a["portal_status"] == "completed"),
            "in_progress": sum(1 for a in applications if a["portal_status"] == "in_progress"),
            "blocked": sum(1 for a in applications if a["portal_status"] in ("blocked", "manual_needed")),
            "pending": sum(1 for a in applications if a["portal_status"] == "pending"),
        }

        return _render("applications.html", _ctx(request, {
            "applications": applications,
            "portals": [{"id": p.id, "portal_name": p.portal_name, "display_name": p.display_name,
                         "support_level": p.support_level, "can_detect_listings": p.can_detect_listings,
                         "can_extract_details": p.can_extract_details, "can_auto_apply": p.can_auto_apply,
                         "can_track_status": p.can_track_status, "requires_login": p.requires_login,
                         "is_active": p.is_active} for p in portals],
            "stats": stats,
        }))
    except Exception as e:
        # If tables don't exist yet, show empty state
        return _render("applications.html", _ctx(request, {
            "applications": [],
            "portals": [],
            "stats": {"total": 0, "completed": 0, "in_progress": 0, "blocked": 0, "pending": 0},
        }))
    finally:
        session.close()


# ── Activity Timeline ─────────────────────────────────────────────

@router.get("/activity", response_class=HTMLResponse)
def activity_view(request: Request, filter_type: str = ""):
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        activities = []

        # ── All outreach messages ──
        outreach_all = session.query(OutreachLog).filter(OutreachLog.user_id == (user.id if user else 1)).order_by(
            OutreachLog.created_at.desc()).limit(100).all()
        for o in outreach_all:
            person = session.query(PeopleMapper).filter(PeopleMapper.id == o.person_id, PeopleMapper.user_id == (user.id if user else 1)).first() if o.person_id else None
            job = session.query(JobShortlist).filter(JobShortlist.id == o.job_id, JobShortlist.user_id == (user.id if user else 1)).first() if o.job_id else None
            if o.status == "sent" and o.sent_at:
                activities.append({
                    "type": "sent",
                    "icon": "send",
                    "title": f"Message sent to {person.name if person else 'contact'}",
                    "desc": f"{person.company if person else ''} — {o.variant} ({o.style or ''}) via {o.channel or 'email'}",
                    "link": f"/outreach",
                    "date": o.sent_at,
                    "time": o.sent_at.strftime("%b %d, %Y %H:%M") if o.sent_at else "",
                })
            elif o.status == "draft":
                activities.append({
                    "type": "draft",
                    "icon": "file-edit",
                    "title": f"Draft created for {person.name if person else 'contact'}",
                    "desc": f"{job.company if job else ''} — {job.role if job else ''} — {o.variant}",
                    "link": f"/outreach?status=draft",
                    "date": o.created_at,
                    "time": o.created_at.strftime("%b %d, %Y %H:%M") if o.created_at else "",
                })
            elif o.status == "approved":
                activities.append({
                    "type": "approved",
                    "icon": "check-circle",
                    "title": f"Message approved for {person.name if person else 'contact'}",
                    "desc": f"{person.company if person else ''} — ready to send",
                    "link": f"/outreach?status=approved",
                    "date": o.created_at,
                    "time": o.created_at.strftime("%b %d, %Y %H:%M") if o.created_at else "",
                })

        # ── Responses ──
        responses = session.query(ResponseTracker).filter(ResponseTracker.user_id == (user.id if user else 1)).order_by(
            ResponseTracker.created_at.desc()).limit(50).all()
        for r in responses:
            person = session.query(PeopleMapper).filter(PeopleMapper.id == r.person_id, PeopleMapper.user_id == (user.id if user else 1)).first() if r.person_id else None
            activities.append({
                "type": "reply",
                "icon": "message-circle",
                "title": f"{(r.response_type or 'Response').replace('_', ' ').title()} from {person.name if person else 'contact'}",
                "desc": r.action_taken or "",
                "link": f"/contacts/{r.person_id}" if r.person_id else "/contacts",
                "date": r.created_at,
                "time": r.created_at.strftime("%b %d, %Y %H:%M") if r.created_at else "",
            })

        # ── Jobs sourced ──
        jobs_all = session.query(JobShortlist).filter(JobShortlist.user_id == (user.id if user else 1)).order_by(
            JobShortlist.created_at.desc()).limit(100).all()
        for j in jobs_all:
            activities.append({
                "type": "job",
                "icon": "briefcase",
                "title": f"Job sourced: {j.role}",
                "desc": f"{j.company} — {j.location or ''} — Fit: {j.fit_score or '?'}/10",
                "link": f"/jobs#job-{j.id}",
                "date": j.created_at,
                "time": j.created_at.strftime("%b %d, %Y %H:%M") if j.created_at else "",
            })

        # ── CVs generated ──
        cvs = session.query(CVVersion).filter(CVVersion.user_id == (user.id if user else 1)).order_by(CVVersion.created_at.desc()).limit(30).all()
        for c in cvs:
            job = session.query(JobShortlist).filter(JobShortlist.id == c.job_id, JobShortlist.user_id == (user.id if user else 1)).first() if c.job_id else None
            activities.append({
                "type": "cv",
                "icon": "file-text",
                "title": f"CV tailored for {job.company if job else 'role'}",
                "desc": f"{job.role if job else ''} — {c.filename or ''}",
                "link": f"/cvs",
                "date": c.created_at,
                "time": c.created_at.strftime("%b %d, %Y %H:%M") if c.created_at else "",
            })

        # ── Status changes (applications) ──
        try:
            applied = session.query(ApplicationMemory).filter(ApplicationMemory.user_id == (user.id if user else 1)).order_by(
                ApplicationMemory.created_at.desc()).limit(50).all()
            for a in applied:
                activities.append({
                    "type": "applied",
                    "icon": "rocket",
                    "title": f"Applied: {a.role_title or ''} at {a.company_name or ''}",
                    "desc": f"via {a.portal or 'direct'} — {a.status or ''}",
                    "link": f"/applications",
                    "date": a.created_at,
                    "time": a.created_at.strftime("%b %d, %Y %H:%M") if a.created_at else "",
                })
        except Exception:
            pass

        # Sort all by date
        activities.sort(key=lambda x: x.get("date") or datetime.min, reverse=True)

        # Apply filter
        if filter_type:
            activities = [a for a in activities if a["type"] == filter_type]

        # Group by date for display
        grouped = defaultdict(list)
        for a in activities[:200]:
            day_key = a["date"].strftime("%A, %B %d, %Y") if a.get("date") else "Unknown"
            grouped[day_key].append(a)

        # Type counts for filter badges
        type_counts = defaultdict(int)
        for a in activities:
            type_counts[a["type"]] += 1

        return _render("activity.html", _ctx(request, {
            "activities": activities[:200],
            "grouped": dict(grouped),
            "day_order": list(grouped.keys()),
            "total": len(activities),
            "filter_type": filter_type,
            "type_counts": dict(type_counts),
        }))
    except Exception as e:
        return _render("activity.html", _ctx(request, {
            "activities": [],
            "grouped": {},
            "day_order": [],
            "total": 0,
            "filter_type": "",
            "type_counts": {},
            "error": str(e),
        }))
    finally:
        session.close()


# ── Dashboard API Endpoints ───────────────────────────────────────

@router.get("/api/health")
def api_health_check():
    """Return API health status as JSON."""
    return JSONResponse({"services": _get_api_health()})


@router.get("/api/dashboard/priority-queue")
def api_priority_queue():
    """Return priority action queue as JSON."""
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0)
        queue = _build_priority_queue(session, today_start)
        return JSONResponse({"items": queue, "count": len(queue)})
    finally:
        session.close()


@router.post("/api/actions/{action_name}")
def api_run_action(action_name: str):
    """Trigger pipeline actions from the dashboard."""
    import subprocess
    import sys

    allowed = {
        "source": "source",
        "enrich": "enrich",
        "generate": "generate",
        "ab-report": "ab-report",
        "digest": "digest",
        "check-replies": "check-replies",
    }

    if action_name not in allowed:
        return JSONResponse(
            {"status": "error", "message": f"Unknown action: {action_name}"},
            status_code=400,
        )

    cmd_name = allowed[action_name]
    try:
        from src.config import PROJECT_ROOT
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "main.py"), cmd_name],
            capture_output=True, text=True, timeout=120,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode == 0:
            return JSONResponse({
                "status": "ok",
                "message": f"{action_name} completed successfully",
                "output": result.stdout[-500:] if result.stdout else "",
            })
        else:
            return JSONResponse({
                "status": "error",
                "message": f"{action_name} failed: {result.stderr[-300:] if result.stderr else 'Unknown error'}",
            })
    except subprocess.TimeoutExpired:
        return JSONResponse({
            "status": "error",
            "message": f"{action_name} timed out after 120 seconds",
        })
    except Exception as e:
        return JSONResponse({
            "status": "error",
            "message": f"Failed to run {action_name}: {str(e)}",
        })


# ── Sage AI Copilot API ──────────────────────────────────────────

@router.post("/api/chat")
@router.post("/api/sage")
async def sage_endpoint(request: Request):
    """Sage AI copilot — intelligent chat with tool execution."""
    from src.dashboard.sage import process_sage_message

    try:
        body = await request.json()
        user_message = body.get("message", "").strip()
        history = body.get("history", [])
        page_context = body.get("context", "dashboard")
        client_api_key = body.get("api_key", "")  # Optional client-provided key
    except Exception:
        return JSONResponse(
            {"reply": "Invalid request.", "actions": [], "suggestions": []},
            status_code=400,
        )

    if not user_message:
        return JSONResponse(
            {"reply": "Please ask me something!", "actions": [], "suggestions": []},
            status_code=400,
        )

    result = process_sage_message(
        user_message, history, page_context, api_key_override=client_api_key
    )
    return JSONResponse(result)


# ── Notifications API ────────────────────────────────────────────

@router.get("/api/notifications")
def api_notifications():
    """Smart notification alerts with company intelligence."""
    from src.dashboard.sage import build_notifications

    user = get_current_user(request) if 'request' in locals() else None


    session = get_session()
    try:
        notifs = build_notifications(session)
        return JSONResponse({
            "notifications": notifs,
            "count": len(notifs),
            "urgent_count": sum(
                1 for n in notifs if n["severity"] == "urgent"
            ),
        })
    finally:
        session.close()


@router.post("/api/notifications/{notif_id}/dismiss")
def api_dismiss_notification(request: Request, notif_id: str):
    """Dismiss a notification (stored in session/localStorage on frontend)."""
    return JSONResponse({"status": "ok", "dismissed": notif_id})


# ── Draft Editing API ────────────────────────────────────────────

@router.patch("/api/outreach/{outreach_id}/edit")
async def api_edit_outreach_message(outreach_id: int, request: Request):
    """Edit a draft outreach message body."""
    try:
        body = await request.json()
        new_message = body.get("message", "").strip()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    if not new_message:
        return JSONResponse({"error": "Message cannot be empty"}, status_code=400)

    user = get_current_user(request) if 'request' in locals() else None


    session = get_session()
    try:
        o = session.query(OutreachLog).filter(OutreachLog.id == outreach_id, OutreachLog.user_id == (user.id if user else 1)).first()
        if not o:
            return JSONResponse({"error": "Not found"}, status_code=404)
        if o.status != "draft":
            return JSONResponse(
                {"error": f"Can only edit drafts. Status is '{o.status}'."},
                status_code=400,
            )
        old_msg = o.message_body
        o.message_body = new_message
        session.commit()
        return JSONResponse({
            "status": "ok",
            "outreach_id": outreach_id,
            "old_length": len(old_msg) if old_msg else 0,
            "new_length": len(new_message),
        })
    finally:
        session.close()


# ── Company Intelligence API ─────────────────────────────────────

@router.get("/api/company/{company_name}/intelligence")
def api_company_intelligence(company_name: str):
    """Full company intelligence report."""
    from src.dashboard.sage import _exec_company_report

    user = get_current_user(request) if 'request' in locals() else None


    session = get_session()
    try:
        result = _exec_company_report(session, {"company": company_name})
        return JSONResponse(result)
    finally:
        session.close()


# ── Connector Test API ───────────────────────────────────────────

@router.post("/api/connectors/test")
async def api_test_connector(request: Request):
    """Test an API connector."""
    try:
        body = await request.json()
        service = body.get("service", "").strip().lower()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    from src.config import Secrets

    testers = {
        "anthropic": lambda: _test_anthropic(Secrets),
        "claude": lambda: _test_anthropic(Secrets),
        "adzuna": lambda: _test_adzuna(Secrets),
        "apollo": lambda: _test_apollo(Secrets),
        "gmail": lambda: _test_gmail(Secrets),
        "hunter": lambda: _test_hunter(Secrets),
        "snov": lambda: _test_snov(Secrets),
    }

    tester = testers.get(service)
    if not tester:
        return JSONResponse({
            "error": f"Unknown service: {service}",
            "valid": list(testers.keys()),
        }, status_code=400)

    result = tester()
    return JSONResponse(result)


def _test_anthropic(secrets):
    key = getattr(secrets, "ANTHROPIC_API_KEY", "")
    if not key:
        return {"service": "Claude AI", "status": "error", "detail": "No API key configured"}
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model="claude-sonnet-4-20250514", max_tokens=10,
            messages=[{"role": "user", "content": "Hi"}],
        )
        return {"service": "Claude AI", "status": "connected", "detail": "API key valid"}
    except Exception as e:
        return {"service": "Claude AI", "status": "error", "detail": str(e)[:100]}


def _test_adzuna(secrets):
    app_id = getattr(secrets, "ADZUNA_APP_ID", "")
    app_key = getattr(secrets, "ADZUNA_APP_KEY", "")
    if not app_id or not app_key:
        return {"service": "Adzuna", "status": "error", "detail": "Missing APP_ID or APP_KEY"}
    try:
        import requests
        r = requests.get(
            f"https://api.adzuna.com/v1/api/jobs/ie/search/1",
            params={"app_id": app_id, "app_key": app_key, "results_per_page": 1, "what": "test"},
            timeout=10,
        )
        if r.status_code == 200:
            return {"service": "Adzuna", "status": "connected", "detail": "API key valid"}
        return {"service": "Adzuna", "status": "error", "detail": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"service": "Adzuna", "status": "error", "detail": str(e)[:100]}


def _test_apollo(secrets):
    key = getattr(secrets, "APOLLO_API_KEY", "")
    if not key:
        return {"service": "Apollo", "status": "error", "detail": "No API key configured"}
    try:
        import requests
        r = requests.post(
            "https://api.apollo.io/api/v1/auth/health",
            headers={"X-Api-Key": key}, timeout=10,
        )
        if r.status_code in (200, 201):
            return {"service": "Apollo", "status": "connected", "detail": "API key valid"}
        return {"service": "Apollo", "status": "error", "detail": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"service": "Apollo", "status": "error", "detail": str(e)[:100]}


def _test_gmail(secrets):
    client_id = getattr(secrets, "GMAIL_CLIENT_ID", "")
    if not client_id:
        return {"service": "Gmail", "status": "error", "detail": "No client ID configured"}
    refresh = getattr(secrets, "GMAIL_REFRESH_TOKEN", "")
    if not refresh:
        return {"service": "Gmail", "status": "partial", "detail": "Client ID set but no refresh token"}
    return {"service": "Gmail", "status": "connected", "detail": "OAuth credentials configured"}


def _test_hunter(secrets):
    key = getattr(secrets, "HUNTER_API_KEY", "")
    if not key:
        return {"service": "Hunter", "status": "error", "detail": "No API key configured"}
    try:
        import requests
        r = requests.get(
            "https://api.hunter.io/v2/account",
            params={"api_key": key}, timeout=10,
        )
        if r.status_code == 200:
            return {"service": "Hunter", "status": "connected", "detail": "API key valid"}
        return {"service": "Hunter", "status": "error", "detail": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"service": "Hunter", "status": "error", "detail": str(e)[:100]}


def _test_snov(secrets):
    uid = getattr(secrets, "SNOV_USER_ID", "")
    secret = getattr(secrets, "SNOV_SECRET", "")
    if not uid or not secret:
        return {"service": "Snov.io", "status": "error", "detail": "Missing user ID or secret"}
    return {"service": "Snov.io", "status": "configured", "detail": "Credentials set"}


# ── REST API: Jobs ───────────────────────────────────────────────

@router.get("/api/jobs")
def api_jobs_list(status: str = "", tier: str = "", q: str = "", limit: int = 50, offset: int = 0):
    """List jobs as JSON with optional filters."""
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        query = session.query(JobShortlist).filter(JobShortlist.user_id == (user.id if user else 1)).order_by(
            JobShortlist.fit_score.desc(), JobShortlist.created_at.desc()
        )
        if status:
            query = query.filter(JobShortlist.status == status)
        if tier:
            query = query.filter(JobShortlist.tier == int(tier))
        if q:
            q_lower = f"%{q.lower()}%"
            query = query.filter(
                (func.lower(JobShortlist.company).like(q_lower)) |
                (func.lower(JobShortlist.role).like(q_lower)) |
                (func.lower(JobShortlist.location).like(q_lower)) |
                (func.lower(JobShortlist.industry).like(q_lower))
            )

        total = query.count()
        jobs = query.offset(offset).limit(limit).all()

        return JSONResponse({
            "total": total,
            "offset": offset,
            "limit": limit,
            "items": [{
                "id": j.id,
                "company": j.company,
                "role": j.role,
                "location": j.location,
                "industry": j.industry,
                "company_stage": j.company_stage,
                "tier": j.tier,
                "fit_score": j.fit_score,
                "status": j.status,
                "is_tier1": j.is_tier1,
                "source": j.source,
                "application_link": j.application_link,
                "keywords": _parse_keywords(j.keywords),
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "updated_at": j.updated_at.isoformat() if j.updated_at else None,
            } for j in jobs],
        })
    finally:
        session.close()


@router.patch("/api/jobs/{job_id}/status")
async def api_update_job_status(job_id: int, request: Request):
    """Update job status via AJAX (used by kanban drag-drop)."""
    try:
        body = await request.json()
        new_status = body.get("status", "").strip()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    if new_status not in STATUSES:
        return JSONResponse({"error": f"Invalid status: {new_status}"}, status_code=400)

    user = get_current_user(request) if 'request' in locals() else None


    session = get_session()
    try:
        job = session.query(JobShortlist).filter(JobShortlist.id == job_id, JobShortlist.user_id == (user.id if user else 1)).first()
        if not job:
            return JSONResponse({"error": "Job not found"}, status_code=404)
        old_status = job.status
        job.status = new_status
        job.updated_at = datetime.utcnow()
        session.commit()
        return JSONResponse({
            "status": "ok",
            "job_id": job_id,
            "old_status": old_status,
            "new_status": new_status,
        })
    finally:
        session.close()


@router.delete("/api/jobs/{job_id}")
def api_delete_job(job_id: int):
    """Delete a job and its related contacts, outreach, and CVs."""
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        job = session.query(JobShortlist).filter(JobShortlist.id == job_id, JobShortlist.user_id == (user.id if user else 1)).first()
        if not job:
            return JSONResponse({"error": "Job not found"}, status_code=404)

        # Delete related records
        session.query(CVVersion).filter(CVVersion.user_id == (user.id if user else 1), CVVersion.job_id == job_id).delete()
        outreach_ids = [o.id for o in session.query(OutreachLog).filter(OutreachLog.user_id == (user.id if user else 1), OutreachLog.job_id == job_id).all()]
        if outreach_ids:
            session.query(ResponseTracker).filter(ResponseTracker.user_id == (user.id if user else 1), ResponseTracker.outreach_id.in_(outreach_ids)).delete(synchronize_session=False)
        session.query(OutreachLog).filter(OutreachLog.user_id == (user.id if user else 1), OutreachLog.job_id == job_id).delete()
        session.query(PeopleMapper).filter(PeopleMapper.user_id == (user.id if user else 1), PeopleMapper.job_id == job_id).delete()
        session.delete(job)
        session.commit()

        return JSONResponse({"status": "ok", "message": f"Job {job_id} deleted"})
    finally:
        session.close()


# ── REST API: Contacts ───────────────────────────────────────────

@router.get("/api/contacts")
def api_contacts_list(q: str = "", company: str = "", next_action: str = "", limit: int = 50, offset: int = 0):
    """List contacts as JSON with optional filters."""
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        query = session.query(PeopleMapper).filter(PeopleMapper.user_id == (user.id if user else 1)).order_by(
            PeopleMapper.company, PeopleMapper.priority
        )
        if company:
            query = query.filter(func.lower(PeopleMapper.company) == company.lower())
        if next_action:
            query = query.filter(PeopleMapper.next_action == next_action)
        if q:
            q_lower = f"%{q.lower()}%"
            query = query.filter(
                (func.lower(PeopleMapper.name).like(q_lower)) |
                (func.lower(PeopleMapper.company).like(q_lower)) |
                (func.lower(PeopleMapper.title).like(q_lower))
            )

        total = query.count()
        contacts = query.offset(offset).limit(limit).all()

        return JSONResponse({
            "total": total,
            "offset": offset,
            "limit": limit,
            "items": [{
                "id": c.id,
                "name": c.name,
                "title": c.title,
                "company": c.company,
                "email": c.email,
                "linkedin_url": c.linkedin_url,
                "relationship": c.relationship_type,
                "priority": c.priority,
                "assigned_variant": c.assigned_variant,
                "next_action": c.next_action,
                "last_contact_date": c.last_contact_date.isoformat() if c.last_contact_date else None,
                "next_follow_up": c.next_follow_up.isoformat() if c.next_follow_up else None,
                "source": c.source,
                "job_id": c.job_id,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            } for c in contacts],
        })
    finally:
        session.close()


@router.patch("/api/contacts/{contact_id}/next-action")
async def api_update_contact_action(contact_id: int, request: Request):
    """Update a contact's next_action field via AJAX."""
    try:
        body = await request.json()
        next_action = body.get("next_action", "").strip()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    valid_actions = ["to_contact", "contacted", "follow_up", "replied", "archived"]
    if next_action not in valid_actions:
        return JSONResponse({"error": f"Invalid action: {next_action}"}, status_code=400)

    user = get_current_user(request) if 'request' in locals() else None


    session = get_session()
    try:
        contact = session.query(PeopleMapper).filter(PeopleMapper.id == contact_id, PeopleMapper.user_id == (user.id if user else 1)).first()
        if not contact:
            return JSONResponse({"error": "Contact not found"}, status_code=404)
        old_action = contact.next_action
        contact.next_action = next_action
        session.commit()
        return JSONResponse({
            "status": "ok",
            "contact_id": contact_id,
            "old_action": old_action,
            "new_action": next_action,
        })
    finally:
        session.close()


# ── REST API: Outreach ───────────────────────────────────────────

@router.get("/api/outreach")
def api_outreach_list(status: str = "", variant: str = "", style: str = "", channel: str = "", limit: int = 50, offset: int = 0):
    """List outreach messages as JSON with optional filters."""
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        query = session.query(OutreachLog).filter(OutreachLog.user_id == (user.id if user else 1)).order_by(OutreachLog.created_at.desc())
        if status:
            query = query.filter(OutreachLog.status == status)
        if variant:
            query = query.filter(OutreachLog.variant == variant)
        if style:
            query = query.filter(OutreachLog.style == style)
        if channel:
            query = query.filter(OutreachLog.channel == channel)

        total = query.count()
        messages = query.offset(offset).limit(limit).all()

        items = []
        for o in messages:
            person = session.query(PeopleMapper).filter(PeopleMapper.id == o.person_id, PeopleMapper.user_id == (user.id if user else 1)).first()
            job = session.query(JobShortlist).filter(JobShortlist.id == o.job_id, JobShortlist.user_id == (user.id if user else 1)).first()
            items.append({
                "id": o.id,
                "person_name": person.name if person else "?",
                "person_title": person.title if person else "",
                "company": person.company if person else "?",
                "job_role": job.role if job else "?",
                "variant": o.variant,
                "style": o.style,
                "channel": o.channel,
                "message": o.message_body,
                "status": o.status,
                "sent_at": o.sent_at.isoformat() if o.sent_at else None,
                "follow_up_date": o.follow_up_date.isoformat() if o.follow_up_date else None,
                "follow_up_count": o.follow_up_count,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            })

        return JSONResponse({"total": total, "offset": offset, "limit": limit, "items": items})
    finally:
        session.close()


@router.patch("/api/outreach/{outreach_id}/status")
async def api_update_outreach_status(outreach_id: int, request: Request):
    """Update outreach message status via AJAX."""
    try:
        body = await request.json()
        new_status = body.get("status", "").strip()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    valid = ["draft", "approved", "sent", "replied", "no_reply"]
    if new_status not in valid:
        return JSONResponse({"error": f"Invalid status: {new_status}"}, status_code=400)

    user = get_current_user(request) if 'request' in locals() else None


    session = get_session()
    try:
        o = session.query(OutreachLog).filter(OutreachLog.id == outreach_id, OutreachLog.user_id == (user.id if user else 1)).first()
        if not o:
            return JSONResponse({"error": "Outreach not found"}, status_code=404)
        old_status = o.status
        o.status = new_status
        if new_status == "sent" and not o.sent_at:
            o.sent_at = datetime.utcnow()
            from src.config import AgentConfig
            o.follow_up_date = (datetime.utcnow() + timedelta(days=AgentConfig.follow_up_days)).date()
        session.commit()
        return JSONResponse({
            "status": "ok",
            "outreach_id": outreach_id,
            "old_status": old_status,
            "new_status": new_status,
        })
    finally:
        session.close()


# ── REST API: Analytics ──────────────────────────────────────────

@router.get("/api/analytics")
def api_analytics(days: int = 30):
    """Return analytics data as JSON with configurable time window."""
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)

        variant_stats = get_variant_performance()
        recs = evaluate_variants()
        response_summary = get_response_summary()

        # Daily activity over the period
        daily = []
        for i in range(min(days, 30) - 1, -1, -1):
            day = datetime.utcnow().replace(hour=0, minute=0, second=0) - timedelta(days=i)
            day_end = day + timedelta(days=1)
            daily.append({
                "date": day.strftime("%Y-%m-%d"),
                "jobs_sourced": session.query(func.count(JobShortlist.id)).filter(JobShortlist.user_id == (user.id if user else 1), 
                    JobShortlist.created_at >= day, JobShortlist.created_at < day_end
                ).scalar() or 0,
                "messages_sent": session.query(func.count(OutreachLog.id)).filter(OutreachLog.user_id == (user.id if user else 1), 
                    OutreachLog.sent_at >= day, OutreachLog.sent_at < day_end,
                    OutreachLog.status.in_(["sent", "replied"]),
                ).scalar() or 0,
                "replies": session.query(func.count(ResponseTracker.id)).filter(ResponseTracker.user_id == (user.id if user else 1), 
                    ResponseTracker.response_date >= day, ResponseTracker.response_date < day_end
                ).scalar() or 0,
            })

        # Conversion funnel
        total_contacts = session.query(func.count(PeopleMapper.id)).filter(PeopleMapper.user_id == (user.id if user else 1)).scalar() or 0
        contacted = session.query(func.count(OutreachLog.id)).filter(OutreachLog.user_id == (user.id if user else 1), 
            OutreachLog.status.in_(["sent", "replied"])).scalar() or 0
        replied = session.query(func.count(ResponseTracker.id)).filter(ResponseTracker.user_id == (user.id if user else 1)).scalar() or 0
        referrals = session.query(func.count(ResponseTracker.id)).filter(ResponseTracker.user_id == (user.id if user else 1), 
            ResponseTracker.response_type == "referral").scalar() or 0
        applied = session.query(func.count(JobShortlist.id)).filter(JobShortlist.user_id == (user.id if user else 1), 
            JobShortlist.status.in_(["applied", "interviewing", "offer"])).scalar() or 0
        interviewing = session.query(func.count(JobShortlist.id)).filter(JobShortlist.user_id == (user.id if user else 1), 
            JobShortlist.status.in_(["interviewing", "offer"])).scalar() or 0

        return JSONResponse({
            "period_days": days,
            "variants": [{
                "variant_id": s.variant_id,
                "style": s.style,
                "sends": s.sends,
                "replies": s.replies,
                "reply_rate": s.reply_rate,
                "referrals": s.referrals,
                "referral_rate": s.referral_rate,
                "weight": s.weight,
                "active": s.active,
            } for s in variant_stats],
            "recommendations": {
                "can_evaluate": recs["can_evaluate"],
                "total_sends": recs["total_sends"],
                "total_replies": recs["total_replies"],
                "active_count": recs["active_count"],
                "boost": list(recs.get("boost", [])),
                "kill": list(recs.get("kill", [])),
            },
            "response_summary": {
                "total_responses": response_summary.get("total_responses", 0) if isinstance(response_summary, dict) else getattr(response_summary, "total_responses", 0),
                "referrals": response_summary.get("referrals", 0) if isinstance(response_summary, dict) else getattr(response_summary, "referrals", 0),
                "interest": response_summary.get("interest", 0) if isinstance(response_summary, dict) else getattr(response_summary, "interest", 0),
                "no_reply": response_summary.get("no_reply", 0) if isinstance(response_summary, dict) else getattr(response_summary, "no_reply", 0),
                "declined": response_summary.get("declined", 0) if isinstance(response_summary, dict) else getattr(response_summary, "declined", 0),
            },
            "daily_activity": daily,
            "funnel": {
                "total_contacts": total_contacts,
                "contacted": contacted,
                "replied": replied,
                "referrals": referrals,
                "applied": applied,
                "interviewing": interviewing,
            },
        })
    finally:
        session.close()


# ── REST API: Stats Summary ──────────────────────────────────────

@router.get("/api/stats")
def api_stats_summary():
    """Quick stats summary as JSON — used by external tools and widgets."""
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0)

        return JSONResponse({
            "total_jobs": session.query(func.count(JobShortlist.id)).filter(JobShortlist.user_id == (user.id if user else 1)).scalar() or 0,
            "jobs_today": session.query(func.count(JobShortlist.id)).filter(JobShortlist.user_id == (user.id if user else 1), 
                JobShortlist.created_at >= today_start).scalar() or 0,
            "total_contacts": session.query(func.count(PeopleMapper.id)).filter(PeopleMapper.user_id == (user.id if user else 1)).scalar() or 0,
            "drafts_pending": session.query(func.count(OutreachLog.id)).filter(OutreachLog.user_id == (user.id if user else 1), 
                OutreachLog.status == "draft").scalar() or 0,
            "approved_pending": session.query(func.count(OutreachLog.id)).filter(OutreachLog.user_id == (user.id if user else 1), 
                OutreachLog.status == "approved").scalar() or 0,
            "messages_sent": session.query(func.count(OutreachLog.id)).filter(OutreachLog.user_id == (user.id if user else 1), 
                OutreachLog.status.in_(["sent", "replied"])).scalar() or 0,
            "sent_today": session.query(func.count(OutreachLog.id)).filter(OutreachLog.user_id == (user.id if user else 1), 
                OutreachLog.sent_at >= today_start,
                OutreachLog.status.in_(["sent", "replied"])).scalar() or 0,
            "replies": session.query(func.count(ResponseTracker.id)).filter(ResponseTracker.user_id == (user.id if user else 1)).scalar() or 0,
            "referrals": session.query(func.count(ResponseTracker.id)).filter(ResponseTracker.user_id == (user.id if user else 1), 
                ResponseTracker.response_type == "referral").scalar() or 0,
            "cvs_generated": session.query(func.count(CVVersion.id)).filter(CVVersion.user_id == (user.id if user else 1)).scalar() or 0,
            "follow_ups_due": len(get_follow_ups_due()),
            "linkedin_quota": get_linkedin_quota_status(),
        })
    finally:
        session.close()


# ── REST API: Global Search ──────────────────────────────────────

@router.get("/api/search")
def api_global_search(q: str = "", limit: int = 20):
    """Global search across jobs, contacts, and outreach. Powers the command palette."""
    if not q or len(q) < 2:
        return JSONResponse({"results": []})

    user = get_current_user(request) if 'request' in locals() else None


    session = get_session()
    try:
        q_lower = f"%{q.lower()}%"
        results = []

        # Search jobs
        jobs = session.query(JobShortlist).filter(JobShortlist.user_id == (user.id if user else 1), 
            (func.lower(JobShortlist.company).like(q_lower)) |
            (func.lower(JobShortlist.role).like(q_lower)) |
            (func.lower(JobShortlist.location).like(q_lower))
        ).limit(limit // 3 + 1).all()
        for j in jobs:
            results.append({
                "type": "job",
                "id": j.id,
                "title": f"{j.company} — {j.role}",
                "subtitle": f"{j.location or ''} · {j.status} · Fit {j.fit_score}/10",
                "url": f"/jobs#job-{j.id}",
                "icon": "briefcase",
            })

        # Search contacts
        contacts = session.query(PeopleMapper).filter(PeopleMapper.user_id == (user.id if user else 1), 
            (func.lower(PeopleMapper.name).like(q_lower)) |
            (func.lower(PeopleMapper.company).like(q_lower)) |
            (func.lower(PeopleMapper.title).like(q_lower))
        ).limit(limit // 3 + 1).all()
        for c in contacts:
            results.append({
                "type": "contact",
                "id": c.id,
                "title": c.name,
                "subtitle": f"{c.title or ''} @ {c.company or ''}",
                "url": f"/contacts/{c.id}",
                "icon": "user",
            })

        # Search outreach messages
        outreach = session.query(OutreachLog).filter(OutreachLog.user_id == (user.id if user else 1), 
            func.lower(OutreachLog.message_body).like(q_lower)
        ).limit(limit // 3 + 1).all()
        for o in outreach:
            person = session.query(PeopleMapper).filter(PeopleMapper.id == o.person_id, PeopleMapper.user_id == (user.id if user else 1)).first()
            results.append({
                "type": "outreach",
                "id": o.id,
                "title": f"Message to {person.name if person else '?'}",
                "subtitle": f"{o.variant} · {o.style} · {o.status}",
                "url": f"/outreach?status={o.status}",
                "icon": "send",
            })

        return JSONResponse({"results": results[:limit], "total": len(results)})
    finally:
        session.close()


# ── Job Intelligence API ─────────────────────────────────────────

@router.get("/api/jobs/{job_id}/intelligence")
def api_job_intelligence(job_id: int):
    """Full intelligence report for a single job — contacts, outreach, application state, timeline."""
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        job = session.query(JobShortlist).filter(JobShortlist.id == job_id, JobShortlist.user_id == (user.id if user else 1)).first()
        if not job:
            return JSONResponse({"error": "Job not found"}, status_code=404)

        # Job details
        job_data = {
            "id": job.id,
            "company": job.company,
            "role": job.role,
            "location": job.location,
            "industry": job.industry,
            "company_stage": job.company_stage,
            "tier": job.tier,
            "fit_score": job.fit_score,
            "status": job.status,
            "is_tier1": job.is_tier1,
            "source": job.source,
            "application_link": job.application_link,
            "description": job.description,
            "keywords": _parse_keywords(job.keywords),
            "sourcer_note": job.sourcer_note,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        }

        # All contacts for this job
        contacts = session.query(PeopleMapper).filter(PeopleMapper.user_id == (user.id if user else 1), 
            PeopleMapper.job_id == job_id
        ).order_by(PeopleMapper.priority).all()
        contacts_data = [{
            "id": c.id,
            "name": c.name,
            "title": c.title,
            "company": c.company,
            "email": c.email,
            "linkedin_url": c.linkedin_url,
            "relationship": c.relationship_type,
            "priority": c.priority,
            "assigned_variant": c.assigned_variant,
            "next_action": c.next_action,
            "last_contact_date": c.last_contact_date.isoformat() if c.last_contact_date else None,
            "next_follow_up": c.next_follow_up.isoformat() if c.next_follow_up else None,
        } for c in contacts]

        # All outreach messages
        outreach = session.query(OutreachLog).filter(OutreachLog.user_id == (user.id if user else 1), 
            OutreachLog.job_id == job_id
        ).order_by(OutreachLog.created_at.desc()).all()
        outreach_data = [{
            "id": o.id,
            "person_id": o.person_id,
            "person_name": next((c.name for c in contacts if c.id == o.person_id), "?"),
            "variant": o.variant,
            "style": o.style,
            "channel": o.channel,
            "message_preview": (o.message_body or "")[:200],
            "status": o.status,
            "sent_at": o.sent_at.isoformat() if o.sent_at else None,
            "follow_up_date": o.follow_up_date.isoformat() if o.follow_up_date else None,
            "follow_up_count": o.follow_up_count,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        } for o in outreach]

        # All responses
        responses = session.query(ResponseTracker).filter(ResponseTracker.user_id == (user.id if user else 1), 
            ResponseTracker.job_id == job_id
        ).order_by(ResponseTracker.created_at.desc()).all()
        responses_data = [{
            "id": r.id,
            "person_id": r.person_id,
            "person_name": next((c.name for c in contacts if c.id == r.person_id), "?"),
            "response_type": r.response_type,
            "action_taken": r.action_taken,
            "notes": r.notes,
            "response_date": r.response_date.isoformat() if r.response_date else None,
        } for r in responses]

        # Application memory (if any)
        app_memory = session.query(ApplicationMemory).filter(ApplicationMemory.user_id == (user.id if user else 1), 
            ApplicationMemory.job_id == job_id
        ).order_by(ApplicationMemory.created_at.desc()).first()
        app_data = None
        if app_memory:
            app_data = {
                "id": app_memory.id,
                "portal": app_memory.portal,
                "portal_status": app_memory.portal_status,
                "application_url": app_memory.application_url,
                "steps_completed": json.loads(app_memory.steps_completed) if app_memory.steps_completed else [],
                "steps_remaining": json.loads(app_memory.steps_remaining) if app_memory.steps_remaining else [],
                "blocked_reason": app_memory.blocked_reason,
                "blocked_step": app_memory.blocked_step,
                "ai_summary": app_memory.ai_summary,
                "last_action": app_memory.last_action,
                "last_action_at": app_memory.last_action_at.isoformat() if app_memory.last_action_at else None,
            }

        # CV versions
        cvs = session.query(CVVersion).filter(CVVersion.user_id == (user.id if user else 1), 
            CVVersion.job_id == job_id
        ).order_by(CVVersion.created_at.desc()).all()
        cvs_data = [{
            "id": cv.id,
            "filename": cv.filename,
            "keywords_used": _parse_keywords(cv.keywords_used),
            "created_at": cv.created_at.isoformat() if cv.created_at else None,
        } for cv in cvs]

        # Build timeline of all events
        timeline = []
        timeline.append({
            "event": "job_added",
            "date": job.created_at.isoformat() if job.created_at else None,
            "detail": f"Job sourced from {job.source or 'unknown'}",
        })
        for c in contacts:
            timeline.append({
                "event": "contact_added",
                "date": c.created_at.isoformat() if c.created_at else None,
                "detail": f"Contact {c.name} ({c.title}) added from {c.source or 'unknown'}",
            })
        for o in outreach:
            if o.status == "draft":
                timeline.append({
                    "event": "draft_created",
                    "date": o.created_at.isoformat() if o.created_at else None,
                    "detail": f"Draft {o.variant} for {next((c.name for c in contacts if c.id == o.person_id), '?')}",
                })
            if o.sent_at:
                timeline.append({
                    "event": "message_sent",
                    "date": o.sent_at.isoformat(),
                    "detail": f"Sent {o.variant} via {o.channel} to {next((c.name for c in contacts if c.id == o.person_id), '?')}",
                })
        for r in responses:
            timeline.append({
                "event": f"response_{r.response_type}",
                "date": (r.response_date or r.created_at).isoformat() if (r.response_date or r.created_at) else None,
                "detail": f"{r.response_type} from {next((c.name for c in contacts if c.id == r.person_id), '?')}: {r.notes or ''}",
            })
        for cv in cvs:
            timeline.append({
                "event": "cv_generated",
                "date": cv.created_at.isoformat() if cv.created_at else None,
                "detail": f"CV tailored: {cv.filename}",
            })
        if app_memory:
            timeline.append({
                "event": f"application_{app_memory.portal_status}",
                "date": (app_memory.last_action_at or app_memory.created_at).isoformat() if (app_memory.last_action_at or app_memory.created_at) else None,
                "detail": f"Application via {app_memory.portal}: {app_memory.portal_status}",
            })

        timeline.sort(key=lambda x: x["date"] or "", reverse=True)

        # AI-generated next action recommendation
        total_sent = sum(1 for o in outreach if o.status in ("sent", "replied"))
        total_replies = sum(1 for o in outreach if o.status == "replied")
        ref_count = sum(1 for r in responses if r.response_type == "referral")
        draft_count = sum(1 for o in outreach if o.status == "draft")

        if job.is_tier1:
            next_action = "TIER 1 — Manual application only. Do not automate."
        elif app_memory and app_memory.portal_status == "completed":
            next_action = "Application submitted. Monitor for interview invitation."
        elif app_memory and app_memory.portal_status == "blocked":
            next_action = f"Application blocked at '{app_memory.blocked_step}': {app_memory.blocked_reason}. Resolve manually."
        elif ref_count > 0:
            next_action = "Referral secured! Apply through the referral channel immediately."
        elif total_replies > 0 and ref_count == 0:
            next_action = "Got replies — follow up and explore the opportunity. Consider applying with tailored CV."
        elif draft_count > 0:
            next_action = f"{draft_count} draft(s) awaiting review. Approve and send."
        elif len(contacts) == 0:
            next_action = "No contacts found. Run enrichment to find decision-makers."
        elif total_sent == 0 and len(contacts) > 0:
            next_action = f"{len(contacts)} contacts ready. Generate outreach messages."
        elif total_sent >= min(len(contacts), 3):
            next_action = "All contacts messaged with no referral. Apply directly now."
        elif total_sent > 0:
            remaining = len(contacts) - total_sent
            next_action = f"{remaining} more contact(s) to reach. Continue outreach."
        else:
            next_action = "Review job and decide on next step."

        return JSONResponse({
            "job": job_data,
            "contacts": contacts_data,
            "outreach": outreach_data,
            "responses": responses_data,
            "application": app_data,
            "cv_versions": cvs_data,
            "timeline": timeline,
            "next_action": next_action,
            "summary": {
                "contacts_count": len(contacts),
                "messages_sent": total_sent,
                "replies": total_replies,
                "referrals": ref_count,
                "drafts_pending": draft_count,
                "cvs_generated": len(cvs),
                "has_application": app_data is not None,
            },
        })
    finally:
        session.close()


@router.get("/api/applications")
def api_applications_list(status: str = "", portal: str = "", limit: int = 50):
    """List all application memory records."""
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        query = session.query(ApplicationMemory).filter(ApplicationMemory.user_id == (user.id if user else 1)).order_by(
            ApplicationMemory.updated_at.desc()
        )
        if status:
            query = query.filter(ApplicationMemory.portal_status == status)
        if portal:
            query = query.filter(func.lower(ApplicationMemory.portal) == portal.lower())

        apps = query.limit(limit).all()
        items = []
        for a in apps:
            job = session.query(JobShortlist).filter(JobShortlist.id == a.job_id, JobShortlist.user_id == (user.id if user else 1)).first()
            items.append({
                "id": a.id,
                "job_id": a.job_id,
                "company": job.company if job else "?",
                "role": job.role if job else "?",
                "portal": a.portal,
                "portal_status": a.portal_status,
                "application_url": a.application_url,
                "blocked_reason": a.blocked_reason,
                "blocked_step": a.blocked_step,
                "ai_summary": a.ai_summary,
                "last_action": a.last_action,
                "last_action_at": a.last_action_at.isoformat() if a.last_action_at else None,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "updated_at": a.updated_at.isoformat() if a.updated_at else None,
            })

        return JSONResponse({"total": len(items), "items": items})
    finally:
        session.close()


@router.get("/api/applications/{app_id}")
def api_application_detail(app_id: int):
    """Full application detail with all memory."""
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        app = session.query(ApplicationMemory).filter(ApplicationMemory.id == app_id, ApplicationMemory.user_id == (user.id if user else 1)).first()
        if not app:
            return JSONResponse({"error": "Application not found"}, status_code=404)

        job = session.query(JobShortlist).filter(JobShortlist.id == app.job_id, JobShortlist.user_id == (user.id if user else 1)).first()

        return JSONResponse({
            "id": app.id,
            "job_id": app.job_id,
            "company": job.company if job else "?",
            "role": job.role if job else "?",
            "job_status": job.status if job else None,
            "portal": app.portal,
            "portal_status": app.portal_status,
            "application_url": app.application_url,
            "form_data": json.loads(app.form_data) if app.form_data else {},
            "documents_uploaded": json.loads(app.documents_uploaded) if app.documents_uploaded else [],
            "steps_completed": json.loads(app.steps_completed) if app.steps_completed else [],
            "steps_remaining": json.loads(app.steps_remaining) if app.steps_remaining else [],
            "blocked_reason": app.blocked_reason,
            "blocked_step": app.blocked_step,
            "ai_summary": app.ai_summary,
            "metadata": json.loads(app.extra_data) if app.extra_data else {},
            "last_action": app.last_action,
            "last_action_at": app.last_action_at.isoformat() if app.last_action_at else None,
            "created_at": app.created_at.isoformat() if app.created_at else None,
            "updated_at": app.updated_at.isoformat() if app.updated_at else None,
        })
    finally:
        session.close()


@router.post("/api/applications/{job_id}/start")
async def api_start_application(job_id: int, request: Request):
    """Start tracking an application for a job."""
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        job = session.query(JobShortlist).filter(JobShortlist.id == job_id, JobShortlist.user_id == (user.id if user else 1)).first()
        if not job:
            return JSONResponse({"error": "Job not found"}, status_code=404)

        # Check if application already exists
        existing = session.query(ApplicationMemory).filter(ApplicationMemory.user_id == (user.id if user else 1), 
            ApplicationMemory.job_id == job_id
        ).first()
        if existing:
            return JSONResponse({
                "error": "Application already exists for this job",
                "existing_id": existing.id,
                "portal_status": existing.portal_status,
            }, status_code=409)

        try:
            body = await request.json()
        except Exception:
            body = {}

        portal = body.get("portal", "manual")
        application_url = body.get("application_url", job.application_link or "")

        app = ApplicationMemory(
            job_id=job_id,
            portal=portal,
            portal_status="pending",
            application_url=application_url,
            steps_completed=json.dumps([]),
            steps_remaining=json.dumps(["fill_form", "upload_cv", "submit"]),
            last_action="application_started",
            last_action_at=datetime.utcnow(),
            ai_summary=f"Application started for {job.role} at {job.company} via {portal}.",
        )
        session.add(app)

        # Update job status to applied if still shortlisted/contacted
        if job.status in ("shortlisted", "contacted", "follow_up"):
            job.status = "applied"
            job.updated_at = datetime.utcnow()

        session.commit()

        return JSONResponse({
            "status": "ok",
            "application_id": app.id,
            "job_id": job_id,
            "company": job.company,
            "role": job.role,
            "portal": portal,
            "portal_status": "pending",
        })
    finally:
        session.close()


@router.patch("/api/applications/{app_id}/update")
async def api_update_application(app_id: int, request: Request):
    """Update application memory (form data, steps, status)."""
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        app = session.query(ApplicationMemory).filter(ApplicationMemory.id == app_id, ApplicationMemory.user_id == (user.id if user else 1)).first()
        if not app:
            return JSONResponse({"error": "Application not found"}, status_code=404)

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        # Update fields if provided
        if "portal_status" in body:
            valid_statuses = ["pending", "in_progress", "completed", "blocked", "manual_needed"]
            if body["portal_status"] not in valid_statuses:
                return JSONResponse({"error": f"Invalid status. Valid: {valid_statuses}"}, status_code=400)
            app.portal_status = body["portal_status"]

        if "form_data" in body:
            app.form_data = json.dumps(body["form_data"]) if isinstance(body["form_data"], dict) else body["form_data"]

        if "documents_uploaded" in body:
            app.documents_uploaded = json.dumps(body["documents_uploaded"]) if isinstance(body["documents_uploaded"], list) else body["documents_uploaded"]

        if "steps_completed" in body:
            app.steps_completed = json.dumps(body["steps_completed"]) if isinstance(body["steps_completed"], list) else body["steps_completed"]

        if "steps_remaining" in body:
            app.steps_remaining = json.dumps(body["steps_remaining"]) if isinstance(body["steps_remaining"], list) else body["steps_remaining"]

        if "blocked_reason" in body:
            app.blocked_reason = body["blocked_reason"]

        if "blocked_step" in body:
            app.blocked_step = body["blocked_step"]

        if "ai_summary" in body:
            app.ai_summary = body["ai_summary"]

        if "metadata" in body:
            app.extra_data = json.dumps(body["metadata"]) if isinstance(body["metadata"], dict) else body["metadata"]

        if "last_action" in body:
            app.last_action = body["last_action"]

        app.last_action_at = datetime.utcnow()
        app.updated_at = datetime.utcnow()
        session.commit()

        return JSONResponse({
            "status": "ok",
            "application_id": app_id,
            "portal_status": app.portal_status,
            "last_action": app.last_action,
        })
    finally:
        session.close()


@router.get("/api/portals")
def api_portals_list():
    """List all portal connectors and their support levels."""
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        portals = session.query(PortalConnector).order_by(
            PortalConnector.support_level, PortalConnector.portal_name
        ).all()

        return JSONResponse({
            "total": len(portals),
            "items": [{
                "id": p.id,
                "portal_name": p.portal_name,
                "display_name": p.display_name,
                "support_level": p.support_level,
                "can_detect_listings": p.can_detect_listings,
                "can_extract_details": p.can_extract_details,
                "can_auto_apply": p.can_auto_apply,
                "can_track_status": p.can_track_status,
                "requires_login": p.requires_login,
                "login_method": p.login_method,
                "base_url": p.base_url,
                "api_endpoint": p.api_endpoint,
                "notes": p.notes,
                "is_active": p.is_active,
                "last_tested": p.last_tested.isoformat() if p.last_tested else None,
            } for p in portals],
        })
    finally:
        session.close()


@router.post("/api/portals/seed")
def api_seed_portals():
    """Seed the portal connectors table with known portals."""
    user = get_current_user(request) if 'request' in locals() else None

    session = get_session()
    try:
        portals_data = [
            {
                "portal_name": "linkedin",
                "display_name": "LinkedIn",
                "support_level": "partial",
                "can_detect_listings": True,
                "can_extract_details": True,
                "can_auto_apply": False,
                "can_track_status": False,
                "requires_login": True,
                "login_method": "oauth",
                "base_url": "https://www.linkedin.com",
                "api_endpoint": "https://api.linkedin.com/v2",
                "notes": "Can detect listings and extract details. Apply manually — Easy Apply not automatable.",
            },
            {
                "portal_name": "indeed",
                "display_name": "Indeed",
                "support_level": "partial",
                "can_detect_listings": True,
                "can_extract_details": True,
                "can_auto_apply": False,
                "can_track_status": False,
                "requires_login": True,
                "login_method": "credentials",
                "base_url": "https://www.indeed.com",
                "api_endpoint": None,
                "notes": "Can detect and extract listings. Manual apply required.",
            },
            {
                "portal_name": "greenhouse",
                "display_name": "Greenhouse",
                "support_level": "partial",
                "can_detect_listings": True,
                "can_extract_details": True,
                "can_auto_apply": True,
                "can_track_status": False,
                "requires_login": False,
                "login_method": None,
                "base_url": "https://boards.greenhouse.io",
                "api_endpoint": "https://boards-api.greenhouse.io/v1",
                "notes": "Public board API available. Partial auto-apply via API for some companies.",
            },
            {
                "portal_name": "lever",
                "display_name": "Lever",
                "support_level": "partial",
                "can_detect_listings": True,
                "can_extract_details": True,
                "can_auto_apply": True,
                "can_track_status": False,
                "requires_login": False,
                "login_method": None,
                "base_url": "https://jobs.lever.co",
                "api_endpoint": "https://api.lever.co/v0",
                "notes": "Public postings API. Partial auto-apply via posting apply endpoint.",
            },
            {
                "portal_name": "workday",
                "display_name": "Workday",
                "support_level": "manual",
                "can_detect_listings": False,
                "can_extract_details": False,
                "can_auto_apply": False,
                "can_track_status": False,
                "requires_login": True,
                "login_method": "credentials",
                "base_url": None,
                "api_endpoint": None,
                "notes": "Heavy anti-automation. Each company has unique Workday instance. Manual only.",
            },
            {
                "portal_name": "bamboohr",
                "display_name": "BambooHR",
                "support_level": "manual",
                "can_detect_listings": False,
                "can_extract_details": False,
                "can_auto_apply": False,
                "can_track_status": False,
                "requires_login": True,
                "login_method": "credentials",
                "base_url": None,
                "api_endpoint": None,
                "notes": "Company-specific portals. Manual application required.",
            },
            {
                "portal_name": "glassdoor",
                "display_name": "Glassdoor",
                "support_level": "partial",
                "can_detect_listings": True,
                "can_extract_details": True,
                "can_auto_apply": False,
                "can_track_status": False,
                "requires_login": True,
                "login_method": "credentials",
                "base_url": "https://www.glassdoor.com",
                "api_endpoint": None,
                "notes": "Can detect listings and extract details. Redirects to external apply.",
            },
            {
                "portal_name": "wellfound",
                "display_name": "AngelList/Wellfound",
                "support_level": "partial",
                "can_detect_listings": True,
                "can_extract_details": True,
                "can_auto_apply": False,
                "can_track_status": False,
                "requires_login": True,
                "login_method": "credentials",
                "base_url": "https://wellfound.com",
                "api_endpoint": None,
                "notes": "Startup-focused. Can detect and extract. Apply through platform.",
            },
            {
                "portal_name": "irishjobs",
                "display_name": "IrishJobs",
                "support_level": "partial",
                "can_detect_listings": True,
                "can_extract_details": True,
                "can_auto_apply": False,
                "can_track_status": False,
                "requires_login": True,
                "login_method": "credentials",
                "base_url": "https://www.irishjobs.ie",
                "api_endpoint": None,
                "notes": "Ireland-focused board. Can detect and extract. Manual apply.",
            },
            {
                "portal_name": "adzuna",
                "display_name": "Adzuna",
                "support_level": "full",
                "can_detect_listings": True,
                "can_extract_details": True,
                "can_auto_apply": False,
                "can_track_status": False,
                "requires_login": False,
                "login_method": None,
                "base_url": "https://www.adzuna.ie",
                "api_endpoint": "https://api.adzuna.com/v1",
                "notes": "Full API access for detection and extraction. Aggregator — redirects to source for apply.",
            },
        ]

        created = 0
        skipped = 0
        for pdata in portals_data:
            existing = session.query(PortalConnector).filter(
                PortalConnector.portal_name == pdata["portal_name"]
            ).first()
            if existing:
                skipped += 1
                continue

            portal = PortalConnector(**pdata)
            session.add(portal)
            created += 1

        session.commit()

        return JSONResponse({
            "status": "ok",
            "created": created,
            "skipped": skipped,
            "total": created + skipped,
        })
    finally:
        session.close()


# ── JSON API: Auth ────────────────────────────────────────────────

@api_router.post("/auth/login")
async def api_login(request: Request):
    data = await request.json()
    username = data.get("username")
    password = data.get("password")
    
    user = authenticate_user(username, password)
    if not user:
        return _json_error("Invalid username or password", 401)
        
    token = create_session_token(user.id)
    response = _json_success({"token": token, "user": {"id": user.id, "username": user.username, "full_name": user.full_name}})
    response.set_cookie(COOKIE_NAME, token, max_age=86400 * 7, httponly=True, samesite="lax")
    return response

@api_router.post("/auth/register")
async def api_register(request: Request):
    data = await request.json()
    username = data.get("username")
    password = data.get("password")
    email = data.get("email")
    full_name = data.get("full_name")
    
    if len(password) < 6:
        return _json_error("Password must be at least 6 characters")
        
    result = register_user(username, email, password, full_name)
    if isinstance(result, str):
        return _json_error(result)
        
    token = create_session_token(result.id)
    response = _json_success({"token": token, "user": {"id": result.id, "username": result.username, "full_name": result.full_name}})
    response.set_cookie(COOKIE_NAME, token, max_age=86400 * 7, httponly=True, samesite="lax")
    return response

@api_router.get("/auth/me")
def api_me(request: Request):
    user = get_current_user(request)
    if not user:
        return _json_error("Not authenticated", 401)
    return _json_success({"id": user.id, "username": user.username, "full_name": user.full_name, "email": user.email})

@api_router.post("/auth/logout")
def api_logout():
    response = _json_success()
    response.delete_cookie(COOKIE_NAME)
    return response


# ── JSON API: Dashboard & Jobs ────────────────────────────────────

@api_router.get("/dashboard/stats")
def api_stats(request: Request):
    user = get_current_user(request)
    if not user: return _json_error("Unauthorized", 401)
    
    session = get_session()
    try:
        today_start = datetime.combine(date.today(), datetime.min.time())
        # We reuse existing logic here
        from src.dashboard.routes import _build_recent_activity, _build_priority_queue, _get_api_health
        
        # This is a bit hacky but we'll manually call the stats logic or refactor it
        # For now, let's just return a subset to test the Next.js connection
        stats = {
            "sent_today": session.query(func.count(OutreachLog.id)).filter(OutreachLog.user_id == user.id, OutreachLog.sent_at >= today_start).scalar() or 0,
            "total_jobs": session.query(func.count(JobShortlist.id)).filter(JobShortlist.user_id == user.id).scalar() or 0,
            "total_contacts": session.query(func.count(PeopleMapper.id)).filter(PeopleMapper.user_id == user.id).scalar() or 0,
            "drafts": session.query(func.count(OutreachLog.id)).filter(OutreachLog.user_id == user.id, OutreachLog.status == "draft").scalar() or 0,
            "recent_activity": _build_recent_activity(session, today_start),
            "priority_queue": _build_priority_queue(session, today_start),
            "api_health": _get_api_health(),
        }
        return _json_success(stats)
    finally:
        session.close()

@api_router.get("/jobs")
def api_jobs(request: Request):
    user = get_current_user(request)
    if not user: return _json_error("Unauthorized", 401)
    
    session = get_session()
    try:
        jobs = session.query(JobShortlist).filter(JobShortlist.user_id == user.id).all()
        return _json_success([
            {
                "id": j.id,
                "company": j.company,
                "role": j.role,
                "status": j.status,
                "fit_score": j.fit_score,
                "location": j.location,
            } for j in jobs
        ])
    finally:
        session.close()


# ── JSON API: Agentic Career Coach ───────────────────────────────

@api_router.post("/coach/chat")
async def api_coach_chat(request: Request):
    user = get_current_user(request)
    if not user: return _json_error("Unauthorized", 401)
    
    data = await request.json()
    message = data.get("message", "")
    voice_mode = data.get("voice", False)
    
    # Placeholder for Claude Agentic Logic
    # In Phase 5, we will implement the actual tool-calling loop here.
    # For now, we'll return a simple AI response.
    
    response_text = f"Hello {user.full_name or user.username}! I am your AI Career Coach. I heard you say: '{message}'. Currently, I am in setup mode, but soon I will be able to help you source jobs and send outreach via voice!"
    
    return _json_success({
        "response": response_text,
        "actions_taken": [],
        "suggested_next_steps": ["Complete onboarding", "Connect your Anthropic API key"]
    })
