"""Sage AI Copilot — intelligent chat engine with action execution.

Sage can:
- Answer questions about pipeline data (jobs, contacts, outreach, analytics)
- Execute actions (edit drafts, approve messages, change settings, run pipeline)
- Provide strategic recommendations with company intelligence
- Ask clarifying questions before modifying data
"""

import json
import logging
from datetime import datetime, timedelta
from sqlalchemy import func

from src.db.session import get_session
from src.db.models import (
    JobShortlist, PeopleMapper, OutreachLog, ResponseTracker, CVVersion,
    ApplicationMemory, PortalConnector,
)

log = logging.getLogger("sage")

# ── Tool Definitions for Claude API ─────────────────────────────

SAGE_TOOLS = [
    {
        "name": "search_pipeline",
        "description": "Search for jobs, contacts, or outreach messages. Use when user asks about specific companies, roles, people, or messages.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity": {
                    "type": "string",
                    "enum": ["jobs", "contacts", "outreach"],
                    "description": "What to search",
                },
                "query": {
                    "type": "string",
                    "description": "Search term (company, role, person name, etc.)",
                },
                "status": {
                    "type": "string",
                    "description": "Optional status filter",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 10)",
                },
            },
            "required": ["entity", "query"],
        },
    },
    {
        "name": "get_company_report",
        "description": "Get full intelligence on a company — jobs, contacts reached, outreach history, responses, and what to do next. Use when user asks about a specific company's status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {
                    "type": "string",
                    "description": "Company name",
                },
            },
            "required": ["company"],
        },
    },
    {
        "name": "edit_draft",
        "description": "Edit the message body of a draft outreach message. Only works on drafts (not sent messages).",
        "input_schema": {
            "type": "object",
            "properties": {
                "outreach_id": {
                    "type": "integer",
                    "description": "ID of the draft to edit",
                },
                "new_message": {
                    "type": "string",
                    "description": "The updated message text",
                },
            },
            "required": ["outreach_id", "new_message"],
        },
    },
    {
        "name": "approve_drafts",
        "description": "Approve draft outreach messages for sending. Can approve a single draft by ID or all drafts at once.",
        "input_schema": {
            "type": "object",
            "properties": {
                "outreach_id": {
                    "type": "integer",
                    "description": "Specific draft ID to approve (omit for all)",
                },
                "approve_all": {
                    "type": "boolean",
                    "description": "True to approve all pending drafts",
                },
            },
        },
    },
    {
        "name": "update_setting",
        "description": "Update a configuration setting. Valid settings: daily_message_limit, daily_linkedin_limit, weekly_linkedin_limit, follow_up_days, max_follow_ups, max_contacts_per_company, search_roles (comma-separated), search_locations (comma-separated), search_industries (comma-separated).",
        "input_schema": {
            "type": "object",
            "properties": {
                "setting": {
                    "type": "string",
                    "description": "Setting name",
                },
                "value": {
                    "type": "string",
                    "description": "New value",
                },
            },
            "required": ["setting", "value"],
        },
    },
    {
        "name": "run_pipeline_action",
        "description": "Run a pipeline stage: source (find new jobs), enrich (find contacts via Apollo), generate (create message drafts), check-replies (process responses), ab-report (variant analysis), digest (daily summary email).",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "source", "enrich", "generate",
                        "check-replies", "ab-report", "digest",
                    ],
                    "description": "Pipeline action to run",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "navigate_to",
        "description": "Navigate the user to a dashboard page. Use when user says 'show me', 'go to', 'open' etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "page": {
                    "type": "string",
                    "enum": [
                        "dashboard", "jobs", "contacts", "outreach",
                        "analytics", "cvs", "settings",
                    ],
                    "description": "Page to navigate to",
                },
                "filters": {
                    "type": "string",
                    "description": "Optional URL query params like '?status=draft'",
                },
            },
            "required": ["page"],
        },
    },
    {
        "name": "update_job_status",
        "description": "Change the status of a job (shortlisted → contacted → applied → interviewing → offer/rejected).",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "integer",
                    "description": "Job ID",
                },
                "new_status": {
                    "type": "string",
                    "enum": [
                        "shortlisted", "contacted", "follow_up",
                        "applied", "interviewing", "rejected", "offer",
                    ],
                    "description": "New status",
                },
            },
            "required": ["job_id", "new_status"],
        },
    },
    {
        "name": "get_recommendations",
        "description": "Get smart recommendations for what to do next based on current pipeline state, overdue items, and strategy.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_job_intelligence",
        "description": "Get full intelligence report on a specific job — contacts, outreach, application state, timeline, and next action recommendation. Use when user asks about a specific job by ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "integer",
                    "description": "The job ID to get intelligence on",
                },
            },
            "required": ["job_id"],
        },
    },
    {
        "name": "get_application_status",
        "description": "Check application status for a job — whether an application has been started, its current state, blocked steps, and progress.",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "integer",
                    "description": "The job ID to check application status for",
                },
            },
            "required": ["job_id"],
        },
    },
    {
        "name": "start_application",
        "description": "Begin tracking an application for a specific job. Creates an application memory record and updates the job status to 'applied'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "integer",
                    "description": "The job ID to start an application for",
                },
                "portal": {
                    "type": "string",
                    "description": "The portal to apply through (linkedin/indeed/greenhouse/lever/workday/manual)",
                },
                "application_url": {
                    "type": "string",
                    "description": "URL of the application page (optional, defaults to job's application_link)",
                },
            },
            "required": ["job_id"],
        },
    },
    {
        "name": "list_portals",
        "description": "Show all supported job portals and their automation levels — which portals can detect listings, extract details, auto-apply, etc.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "compare_jobs",
        "description": "Compare two jobs side by side — fit scores, contacts, outreach progress, application status, and which to prioritise.",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id_a": {
                    "type": "integer",
                    "description": "First job ID to compare",
                },
                "job_id_b": {
                    "type": "integer",
                    "description": "Second job ID to compare",
                },
            },
            "required": ["job_id_a", "job_id_b"],
        },
    },
]

SAGE_SYSTEM_PROMPT = """\
You are **Sage**, the AI copilot for an outreach-based job search platform. \
You help the user manage their entire job search pipeline — sourcing, contacts, \
outreach, A/B testing, and applications.

PERSONALITY: Smart, direct, proactive. You're a strategic sales operations partner.

CAPABILITIES (use the provided tools):
- Search & query pipeline data (jobs, contacts, outreach messages)
- Get full job intelligence reports (contacts, outreach, applications, timeline)
- Check and start application tracking for jobs
- Compare two jobs side by side with prioritisation recommendations
- List supported job portals and their automation levels
- Show company intelligence (who was contacted, responses, next steps)
- Edit draft messages before they're sent
- Approve drafts for sending
- Run pipeline actions (source jobs, enrich contacts, generate messages, etc.)
- Update settings and strategy (limits, search criteria, variant weights)
- Navigate the user to specific dashboard pages
- Provide strategic recommendations

IMPORTANT RULES:
1. Before modifying data (editing, approving, changing settings), ALWAYS confirm \
with the user first. Say what you'll do and ask "Should I go ahead?"
2. When showing data, format it clearly with bullet points or tables.
3. When the user asks about a company, use get_company_report to show full intelligence.
4. Be proactive — if you see issues (overdue follow-ups, exhausted contacts), mention them.
5. Keep responses concise but informative. Use numbers and specifics.
6. When the user asks to change strategy or settings, explain the impact before making changes.
7. If the user's request is ambiguous, ask a clarifying question.
"""


# ── Context Builder ─────────────────────────────────────────────

def build_sage_context(session):
    """Build comprehensive pipeline context for Sage."""
    today = datetime.utcnow().replace(hour=0, minute=0, second=0)

    total_jobs = session.query(func.count(JobShortlist.id)).scalar() or 0
    jobs_today = session.query(func.count(JobShortlist.id)).filter(
        JobShortlist.created_at >= today).scalar() or 0
    total_contacts = session.query(func.count(PeopleMapper.id)).scalar() or 0
    drafts = session.query(func.count(OutreachLog.id)).filter(
        OutreachLog.status == "draft").scalar() or 0
    approved = session.query(func.count(OutreachLog.id)).filter(
        OutreachLog.status == "approved").scalar() or 0
    sent = session.query(func.count(OutreachLog.id)).filter(
        OutreachLog.status.in_(["sent", "replied"])).scalar() or 0
    replies = session.query(func.count(ResponseTracker.id)).scalar() or 0
    referrals = session.query(func.count(ResponseTracker.id)).filter(
        ResponseTracker.response_type == "referral").scalar() or 0

    statuses = session.query(
        JobShortlist.status, func.count(JobShortlist.id)
    ).group_by(JobShortlist.status).all()

    top_jobs = session.query(JobShortlist).order_by(
        JobShortlist.fit_score.desc()).limit(10).all()

    # Pending drafts with company intelligence
    pending_drafts = session.query(OutreachLog).filter(
        OutreachLog.status == "draft"
    ).order_by(OutreachLog.created_at.desc()).limit(15).all()

    draft_lines = []
    for d in pending_drafts:
        person = session.get(PeopleMapper, d.person_id)
        job = session.get(JobShortlist, d.job_id)
        company = person.company if person else "?"
        company_total = session.query(func.count(PeopleMapper.id)).filter(
            PeopleMapper.company == company).scalar() or 0
        company_sent = session.query(func.count(OutreachLog.id)).filter(
            OutreachLog.status.in_(["sent", "replied"]),
            OutreachLog.person_id.in_(
                session.query(PeopleMapper.id).filter(
                    PeopleMapper.company == company)
            ),
        ).scalar() or 0
        draft_lines.append(
            f"  ID:{d.id} | {person.name if person else '?'} @ {company} | "
            f"{job.role if job else '?'} | {d.variant} ({d.style}) via {d.channel} | "
            f"Company outreach: {company_sent}/{company_total} contacted | "
            f"Preview: {(d.message_body or '')[:120]}..."
        )

    # Overdue follow-ups
    from src.tracking.response_handler import get_follow_ups_due
    follow_ups = get_follow_ups_due()

    # Variant performance
    from src.testing.ab_engine import get_variant_performance
    variants = get_variant_performance()

    context = (
        f"PIPELINE STATUS ({datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}):\n"
        f"Total jobs: {total_jobs} | Added today: {jobs_today}\n"
        f"Total contacts: {total_contacts}\n"
        f"Drafts pending: {drafts} | Approved: {approved} | Sent: {sent}\n"
        f"Replies: {replies} | Referrals: {referrals}\n\n"
        f"JOB STATUS: {', '.join(f'{s}: {c}' for s, c in statuses) or 'none'}\n\n"
        f"TOP 10 JOBS:\n"
        + ("\n".join(
            f"  ID:{j.id} | {j.company} | {j.role} | fit={j.fit_score} | "
            f"{j.status} | {j.location}"
            + (" [TIER1]" if j.is_tier1 else "")
            for j in top_jobs
        ) or "  (none)")
        + f"\n\nPENDING DRAFTS ({len(draft_lines)}):\n"
        + ("\n".join(draft_lines) or "  (none)")
        + f"\n\nOVERDUE FOLLOW-UPS: {len(follow_ups) if isinstance(follow_ups, list) else 0}\n"
        + f"\nVARIANT PERFORMANCE:\n"
        + ("\n".join(
            f"  {v.variant_id} ({v.style}): {v.sends} sends, {v.replies} replies, "
            f"{v.reply_rate:.0f}% reply rate"
            + (" [ACTIVE]" if v.active else " [RETIRED]")
            for v in variants
        ) or "  (none)")
    )
    return context


# ── Tool Executors ──────────────────────────────────────────────

def execute_tool(tool_name, tool_input, session):
    """Execute a Sage tool and return the result as a dict."""
    executors = {
        "search_pipeline": _exec_search,
        "get_company_report": _exec_company_report,
        "edit_draft": _exec_edit_draft,
        "approve_drafts": _exec_approve_drafts,
        "update_setting": _exec_update_setting,
        "run_pipeline_action": _exec_run_action,
        "navigate_to": _exec_navigate,
        "update_job_status": _exec_update_job_status,
        "get_recommendations": _exec_recommendations,
        "get_job_intelligence": _exec_job_intelligence,
        "get_application_status": _exec_application_status,
        "start_application": _exec_start_application,
        "list_portals": _exec_list_portals,
        "compare_jobs": _exec_compare_jobs,
    }
    executor = executors.get(tool_name)
    if not executor:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        return executor(session, tool_input)
    except Exception as e:
        log.exception("Sage tool %s failed", tool_name)
        return {"error": str(e)}


def _exec_search(session, inp):
    entity = inp.get("entity", "jobs")
    q = inp.get("query", "").lower()
    status = inp.get("status", "")
    limit = min(inp.get("limit", 10), 25)

    if entity == "jobs":
        query = session.query(JobShortlist)
        if q:
            query = query.filter(
                (func.lower(JobShortlist.company).like(f"%{q}%")) |
                (func.lower(JobShortlist.role).like(f"%{q}%")) |
                (func.lower(JobShortlist.location).like(f"%{q}%"))
            )
        if status:
            query = query.filter(JobShortlist.status == status)
        jobs = query.order_by(JobShortlist.fit_score.desc()).limit(limit).all()
        return {
            "results": [
                {
                    "id": j.id, "company": j.company, "role": j.role,
                    "fit_score": j.fit_score, "status": j.status,
                    "location": j.location, "is_tier1": j.is_tier1,
                    "source": j.source,
                }
                for j in jobs
            ],
            "count": len(jobs),
        }

    elif entity == "contacts":
        query = session.query(PeopleMapper)
        if q:
            query = query.filter(
                (func.lower(PeopleMapper.name).like(f"%{q}%")) |
                (func.lower(PeopleMapper.company).like(f"%{q}%"))
            )
        contacts = query.limit(limit).all()
        return {
            "results": [
                {
                    "id": c.id, "name": c.name, "company": c.company,
                    "title": c.title, "next_action": c.next_action,
                    "priority": c.priority, "email": c.email,
                    "linkedin_url": c.linkedin_url,
                }
                for c in contacts
            ],
            "count": len(contacts),
        }

    elif entity == "outreach":
        query = session.query(OutreachLog)
        if status:
            query = query.filter(OutreachLog.status == status)
        if q:
            query = query.filter(
                OutreachLog.person_id.in_(
                    session.query(PeopleMapper.id).filter(
                        (func.lower(PeopleMapper.name).like(f"%{q}%")) |
                        (func.lower(PeopleMapper.company).like(f"%{q}%"))
                    )
                )
            )
        msgs = query.order_by(OutreachLog.created_at.desc()).limit(limit).all()
        results = []
        for o in msgs:
            person = session.get(PeopleMapper, o.person_id)
            results.append({
                "id": o.id,
                "person": person.name if person else "?",
                "company": person.company if person else "?",
                "variant": o.variant, "status": o.status,
                "channel": o.channel, "style": o.style,
                "message_preview": (o.message_body or "")[:120],
            })
        return {"results": results, "count": len(results)}

    return {"error": "Invalid entity"}


def _exec_company_report(session, inp):
    company = inp.get("company", "")
    if not company:
        return {"error": "Company name required"}

    jobs = session.query(JobShortlist).filter(
        func.lower(JobShortlist.company).like(f"%{company.lower()}%")
    ).all()

    contacts = session.query(PeopleMapper).filter(
        func.lower(PeopleMapper.company).like(f"%{company.lower()}%")
    ).all()

    contact_ids = [c.id for c in contacts]
    outreach = []
    if contact_ids:
        outreach = session.query(OutreachLog).filter(
            OutreachLog.person_id.in_(contact_ids)
        ).order_by(OutreachLog.created_at.desc()).all()

    responses = []
    if contact_ids:
        responses = session.query(ResponseTracker).filter(
            ResponseTracker.person_id.in_(contact_ids)
        ).all()

    total_sent = sum(1 for o in outreach if o.status in ("sent", "replied"))
    total_replies = sum(1 for o in outreach if o.status == "replied")
    ref_count = sum(1 for r in responses if r.response_type == "referral")
    draft_count = sum(1 for o in outreach if o.status == "draft")

    # Smart recommendation
    rec = "No data yet."
    if not contacts:
        rec = "No contacts enriched. Run enrichment to find decision-makers."
    elif total_sent == 0 and draft_count > 0:
        rec = f"{draft_count} draft(s) waiting — review and approve them."
    elif total_sent == 0:
        rec = f"{len(contacts)} contacts found but none contacted yet. Generate messages."
    elif ref_count > 0:
        rec = "Referral secured! Apply through the referral channel immediately."
    elif total_replies > 0:
        rec = "Got replies — follow up and explore the opportunity."
    elif total_sent >= min(len(contacts), 3):
        rec = (
            f"All {total_sent} contacts messaged with no referral. "
            "Apply directly now."
        )
    elif total_sent > 0:
        remaining = len(contacts) - total_sent
        rec = f"{remaining} more contact(s) to reach. Continue outreach."

    return {
        "company": company,
        "jobs": [
            {
                "id": j.id, "role": j.role, "status": j.status,
                "fit_score": j.fit_score, "is_tier1": j.is_tier1,
            }
            for j in jobs
        ],
        "contacts": [
            {
                "id": c.id, "name": c.name, "title": c.title,
                "next_action": c.next_action, "priority": c.priority,
            }
            for c in contacts
        ],
        "outreach": {
            "total": len(outreach),
            "drafts": draft_count,
            "sent": total_sent,
            "replied": total_replies,
        },
        "responses": {
            "total": len(responses),
            "referrals": ref_count,
            "interest": sum(
                1 for r in responses if r.response_type == "interest"
            ),
        },
        "recommendation": rec,
        "ratio": f"{total_sent}/{len(contacts)} contacted",
    }


def _exec_edit_draft(session, inp):
    oid = inp.get("outreach_id")
    new_msg = inp.get("new_message", "")
    if not oid:
        return {"error": "outreach_id required"}
    o = session.get(OutreachLog, oid)
    if not o:
        return {"error": f"Outreach #{oid} not found"}
    if o.status != "draft":
        return {"error": f"Can only edit drafts. This message is '{o.status}'."}
    old_preview = (o.message_body or "")[:80]
    o.message_body = new_msg
    session.commit()
    return {
        "status": "ok", "outreach_id": oid,
        "old_preview": old_preview,
        "new_preview": new_msg[:80],
    }


def _exec_approve_drafts(session, inp):
    approve_all = inp.get("approve_all", False)
    oid = inp.get("outreach_id")

    if approve_all:
        drafts = session.query(OutreachLog).filter(
            OutreachLog.status == "draft").all()
        for d in drafts:
            d.status = "approved"
        session.commit()
        return {"status": "ok", "approved_count": len(drafts)}
    elif oid:
        o = session.get(OutreachLog, oid)
        if not o:
            return {"error": f"Outreach #{oid} not found"}
        if o.status != "draft":
            return {"error": f"Already '{o.status}'"}
        o.status = "approved"
        session.commit()
        person = session.get(PeopleMapper, o.person_id)
        return {
            "status": "ok", "outreach_id": oid,
            "person": person.name if person else "?",
        }
    return {"error": "Provide outreach_id or set approve_all=true"}


def _exec_update_setting(session, inp):
    setting = inp.get("setting", "")
    value = inp.get("value", "")

    valid = {
        "daily_message_limit": "int",
        "daily_linkedin_limit": "int",
        "weekly_linkedin_limit": "int",
        "follow_up_days": "int",
        "max_follow_ups": "int",
        "max_contacts_per_company": "int",
        "search_roles": "list",
        "search_locations": "list",
        "search_industries": "list",
    }
    if setting not in valid:
        return {
            "error": f"Unknown setting: {setting}. "
            f"Valid: {', '.join(valid.keys())}",
        }

    try:
        import yaml
        from src.config import PROJECT_ROOT

        config_path = PROJECT_ROOT / "config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}

        vtype = valid[setting]
        if vtype == "int":
            parsed = int(value)
        elif vtype == "list":
            parsed = [v.strip() for v in value.split(",") if v.strip()]
        else:
            parsed = value

        if setting.startswith("search_"):
            key = setting.replace("search_", "")
            config.setdefault("search", {})[key] = parsed
        else:
            config.setdefault("agent", {})[setting] = parsed

        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)

        return {"status": "ok", "setting": setting, "new_value": str(parsed)}
    except Exception as e:
        return {"error": f"Failed: {e}"}


def _exec_run_action(session, inp):
    import subprocess
    import sys
    from src.config import PROJECT_ROOT

    action = inp.get("action", "")
    allowed = [
        "source", "enrich", "generate",
        "check-replies", "ab-report", "digest",
    ]
    if action not in allowed:
        return {"error": f"Invalid action: {action}"}

    try:
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "main.py"), action],
            capture_output=True, text=True, timeout=120,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode == 0:
            return {
                "status": "ok", "action": action,
                "output": result.stdout[-500:] if result.stdout else "Completed.",
            }
        return {
            "status": "error", "action": action,
            "error": result.stderr[-300:] if result.stderr else "Failed",
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": f"{action} timed out (120s)"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _exec_navigate(session, inp):
    page = inp.get("page", "dashboard")
    filters = inp.get("filters", "")
    urls = {
        "dashboard": "/", "jobs": "/jobs", "contacts": "/contacts",
        "outreach": "/outreach", "analytics": "/analytics",
        "cvs": "/cvs", "settings": "/settings",
    }
    url = urls.get(page, "/")
    if filters:
        url += filters if filters.startswith("?") else f"?{filters}"
    return {"status": "ok", "url": url, "page": page}


def _exec_update_job_status(session, inp):
    job_id = inp.get("job_id")
    new_status = inp.get("new_status")
    job = session.get(JobShortlist, job_id)
    if not job:
        return {"error": f"Job #{job_id} not found"}
    old = job.status
    job.status = new_status
    job.updated_at = datetime.utcnow()
    session.commit()
    return {
        "status": "ok",
        "job": f"{job.company} — {job.role}",
        "old_status": old, "new_status": new_status,
    }


def _exec_recommendations(session, inp):
    today = datetime.utcnow().date()
    recs = []

    # Overdue follow-ups
    overdue = session.query(OutreachLog).filter(
        OutreachLog.status == "sent",
        OutreachLog.follow_up_date <= today,
        OutreachLog.follow_up_count == 0,
    ).all()
    if overdue:
        for o in overdue[:3]:
            person = session.get(PeopleMapper, o.person_id)
            recs.append(
                f"Follow up with {person.name if person else '?'} "
                f"@ {person.company if person else '?'} — sent {o.channel}, "
                f"overdue by {(today - o.follow_up_date).days} days"
            )

    # High-score uncontacted
    high_jobs = session.query(JobShortlist).filter(
        JobShortlist.status == "shortlisted",
        JobShortlist.fit_score >= 7,
        JobShortlist.is_tier1 == False,
    ).order_by(JobShortlist.fit_score.desc()).limit(3).all()
    for j in high_jobs:
        contacts = session.query(func.count(PeopleMapper.id)).filter(
            PeopleMapper.job_id == j.id).scalar() or 0
        if contacts == 0:
            recs.append(
                f"Enrich {j.company} — {j.role} (fit score {j.fit_score}/10). "
                "No contacts found yet."
            )
        else:
            recs.append(
                f"Start outreach for {j.company} — {j.role} "
                f"(fit {j.fit_score}/10, {contacts} contacts ready)"
            )

    # Drafts to review
    draft_count = session.query(func.count(OutreachLog.id)).filter(
        OutreachLog.status == "draft").scalar() or 0
    if draft_count > 0:
        recs.append(f"Review and approve {draft_count} pending draft(s)")

    # Approved ready to send
    approved = session.query(func.count(OutreachLog.id)).filter(
        OutreachLog.status == "approved").scalar() or 0
    if approved > 0:
        recs.append(f"Send {approved} approved message(s)")

    # Variant insight
    from src.testing.ab_engine import get_variant_performance
    variants = get_variant_performance()
    active = [v for v in variants if v.active and v.sends >= 5]
    if active:
        best = max(active, key=lambda v: v.reply_rate)
        if best.reply_rate > 0:
            recs.append(
                f"Best variant: {best.variant_id} ({best.style}) at "
                f"{best.reply_rate:.0f}% reply rate — consider boosting it"
            )

    if not recs:
        recs.append("Pipeline looks good! Source new jobs or check analytics.")

    return {"recommendations": recs}


def _exec_job_intelligence(session, inp):
    """Get full intelligence report on a specific job."""
    job_id = inp.get("job_id")
    if not job_id:
        return {"error": "job_id required"}

    job = session.get(JobShortlist, job_id)
    if not job:
        return {"error": f"Job #{job_id} not found"}

    # Contacts
    contacts = session.query(PeopleMapper).filter(
        PeopleMapper.job_id == job_id
    ).order_by(PeopleMapper.priority).all()

    # Outreach
    outreach = session.query(OutreachLog).filter(
        OutreachLog.job_id == job_id
    ).order_by(OutreachLog.created_at.desc()).all()

    # Responses
    responses = session.query(ResponseTracker).filter(
        ResponseTracker.job_id == job_id
    ).all()

    # Application memory
    app_memory = session.query(ApplicationMemory).filter(
        ApplicationMemory.job_id == job_id
    ).first()

    # CV versions
    cvs = session.query(CVVersion).filter(
        CVVersion.job_id == job_id
    ).all()

    total_sent = sum(1 for o in outreach if o.status in ("sent", "replied"))
    total_replies = sum(1 for o in outreach if o.status == "replied")
    ref_count = sum(1 for r in responses if r.response_type == "referral")
    draft_count = sum(1 for o in outreach if o.status == "draft")

    # Build next action recommendation
    if job.is_tier1:
        next_action = "TIER 1 — Manual application only. Do not automate."
    elif app_memory and app_memory.portal_status == "completed":
        next_action = "Application submitted. Monitor for interview invitation."
    elif app_memory and app_memory.portal_status == "blocked":
        next_action = f"Application blocked at '{app_memory.blocked_step}': {app_memory.blocked_reason}. Resolve manually."
    elif ref_count > 0:
        next_action = "Referral secured! Apply through the referral channel immediately."
    elif total_replies > 0:
        next_action = "Got replies — follow up and explore the opportunity."
    elif draft_count > 0:
        next_action = f"{draft_count} draft(s) awaiting review. Approve and send."
    elif len(contacts) == 0:
        next_action = "No contacts found. Run enrichment to find decision-makers."
    elif total_sent == 0:
        next_action = f"{len(contacts)} contacts ready. Generate outreach messages."
    elif total_sent >= min(len(contacts), 3):
        next_action = "All contacts messaged with no referral. Apply directly now."
    else:
        remaining = len(contacts) - total_sent
        next_action = f"{remaining} more contact(s) to reach. Continue outreach."

    # Build timeline
    timeline = []
    timeline.append(f"[{job.created_at}] Job sourced from {job.source or 'unknown'}")
    for c in contacts:
        timeline.append(f"[{c.created_at}] Contact added: {c.name} ({c.title})")
    for o in outreach:
        if o.sent_at:
            person = session.get(PeopleMapper, o.person_id)
            timeline.append(
                f"[{o.sent_at}] Sent {o.variant} via {o.channel} to {person.name if person else '?'}"
            )
    for r in responses:
        person = session.get(PeopleMapper, r.person_id)
        timeline.append(
            f"[{r.response_date or r.created_at}] {r.response_type} from {person.name if person else '?'}"
        )
    if app_memory:
        timeline.append(
            f"[{app_memory.last_action_at or app_memory.created_at}] "
            f"Application via {app_memory.portal}: {app_memory.portal_status}"
        )

    return {
        "job": {
            "id": job.id,
            "company": job.company,
            "role": job.role,
            "location": job.location,
            "fit_score": job.fit_score,
            "status": job.status,
            "is_tier1": job.is_tier1,
            "source": job.source,
            "keywords": job.keywords,
        },
        "contacts": [
            {
                "id": c.id, "name": c.name, "title": c.title,
                "priority": c.priority, "next_action": c.next_action,
            }
            for c in contacts
        ],
        "outreach_summary": {
            "total": len(outreach),
            "drafts": draft_count,
            "sent": total_sent,
            "replied": total_replies,
        },
        "responses_summary": {
            "total": len(responses),
            "referrals": ref_count,
            "interest": sum(1 for r in responses if r.response_type == "interest"),
        },
        "application": {
            "exists": app_memory is not None,
            "portal": app_memory.portal if app_memory else None,
            "status": app_memory.portal_status if app_memory else None,
            "blocked_reason": app_memory.blocked_reason if app_memory else None,
            "ai_summary": app_memory.ai_summary if app_memory else None,
        },
        "cv_versions": len(cvs),
        "timeline": timeline[-10:],  # Last 10 events
        "next_action": next_action,
    }


def _exec_application_status(session, inp):
    """Check application status for a job."""
    job_id = inp.get("job_id")
    if not job_id:
        return {"error": "job_id required"}

    job = session.get(JobShortlist, job_id)
    if not job:
        return {"error": f"Job #{job_id} not found"}

    app = session.query(ApplicationMemory).filter(
        ApplicationMemory.job_id == job_id
    ).first()

    if not app:
        return {
            "job_id": job_id,
            "company": job.company,
            "role": job.role,
            "has_application": False,
            "message": "No application started yet for this job.",
            "job_status": job.status,
        }

    try:
        steps_completed = json.loads(app.steps_completed) if app.steps_completed else []
    except (json.JSONDecodeError, TypeError):
        steps_completed = []
    try:
        steps_remaining = json.loads(app.steps_remaining) if app.steps_remaining else []
    except (json.JSONDecodeError, TypeError):
        steps_remaining = []

    return {
        "job_id": job_id,
        "company": job.company,
        "role": job.role,
        "has_application": True,
        "application_id": app.id,
        "portal": app.portal,
        "portal_status": app.portal_status,
        "application_url": app.application_url,
        "steps_completed": steps_completed,
        "steps_remaining": steps_remaining,
        "blocked_reason": app.blocked_reason,
        "blocked_step": app.blocked_step,
        "ai_summary": app.ai_summary,
        "last_action": app.last_action,
        "last_action_at": str(app.last_action_at) if app.last_action_at else None,
        "job_status": job.status,
    }


def _exec_start_application(session, inp):
    """Start tracking an application for a job."""
    job_id = inp.get("job_id")
    if not job_id:
        return {"error": "job_id required"}

    job = session.get(JobShortlist, job_id)
    if not job:
        return {"error": f"Job #{job_id} not found"}

    # Check if already exists
    existing = session.query(ApplicationMemory).filter(
        ApplicationMemory.job_id == job_id
    ).first()
    if existing:
        return {
            "error": "Application already exists for this job",
            "existing_id": existing.id,
            "portal_status": existing.portal_status,
        }

    portal = inp.get("portal", "manual")
    application_url = inp.get("application_url", job.application_link or "")

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

    # Update job status
    if job.status in ("shortlisted", "contacted", "follow_up"):
        job.status = "applied"
        job.updated_at = datetime.utcnow()

    session.commit()

    return {
        "status": "ok",
        "application_id": app.id,
        "job_id": job_id,
        "company": job.company,
        "role": job.role,
        "portal": portal,
        "portal_status": "pending",
        "message": f"Application tracking started for {job.role} at {job.company}.",
    }


def _exec_list_portals(session, inp):
    """List all supported portals and their automation levels."""
    portals = session.query(PortalConnector).filter(
        PortalConnector.is_active == True
    ).order_by(PortalConnector.support_level, PortalConnector.portal_name).all()

    if not portals:
        return {
            "portals": [],
            "message": "No portals configured. Use the seed endpoint to populate defaults.",
        }

    return {
        "portals": [
            {
                "name": p.portal_name,
                "display_name": p.display_name,
                "support_level": p.support_level,
                "can_detect": p.can_detect_listings,
                "can_extract": p.can_extract_details,
                "can_auto_apply": p.can_auto_apply,
                "can_track": p.can_track_status,
                "requires_login": p.requires_login,
                "login_method": p.login_method,
                "notes": p.notes,
            }
            for p in portals
        ],
        "total": len(portals),
        "full_support": sum(1 for p in portals if p.support_level == "full"),
        "partial_support": sum(1 for p in portals if p.support_level == "partial"),
        "manual_only": sum(1 for p in portals if p.support_level == "manual"),
    }


def _exec_compare_jobs(session, inp):
    """Compare two jobs side by side."""
    job_id_a = inp.get("job_id_a")
    job_id_b = inp.get("job_id_b")

    if not job_id_a or not job_id_b:
        return {"error": "Both job_id_a and job_id_b are required"}

    job_a = session.get(JobShortlist, job_id_a)
    job_b = session.get(JobShortlist, job_id_b)

    if not job_a:
        return {"error": f"Job #{job_id_a} not found"}
    if not job_b:
        return {"error": f"Job #{job_id_b} not found"}

    def _job_summary(job):
        contacts = session.query(PeopleMapper).filter(
            PeopleMapper.job_id == job.id).all()
        outreach = session.query(OutreachLog).filter(
            OutreachLog.job_id == job.id).all()
        responses = session.query(ResponseTracker).filter(
            ResponseTracker.job_id == job.id).all()
        app = session.query(ApplicationMemory).filter(
            ApplicationMemory.job_id == job.id).first()
        cvs = session.query(CVVersion).filter(
            CVVersion.job_id == job.id).all()

        sent = sum(1 for o in outreach if o.status in ("sent", "replied"))
        replies = sum(1 for o in outreach if o.status == "replied")
        referrals = sum(1 for r in responses if r.response_type == "referral")

        return {
            "id": job.id,
            "company": job.company,
            "role": job.role,
            "location": job.location,
            "industry": job.industry,
            "company_stage": job.company_stage,
            "fit_score": job.fit_score,
            "status": job.status,
            "is_tier1": job.is_tier1,
            "source": job.source,
            "contacts_count": len(contacts),
            "messages_sent": sent,
            "replies": replies,
            "referrals": referrals,
            "drafts_pending": sum(1 for o in outreach if o.status == "draft"),
            "has_application": app is not None,
            "application_status": app.portal_status if app else None,
            "cv_versions": len(cvs),
        }

    summary_a = _job_summary(job_a)
    summary_b = _job_summary(job_b)

    # Generate recommendation
    score_a = (job_a.fit_score or 0) * 2
    score_b = (job_b.fit_score or 0) * 2

    # Boost for referrals
    if summary_a["referrals"] > 0:
        score_a += 20
    if summary_b["referrals"] > 0:
        score_b += 20

    # Boost for replies
    score_a += summary_a["replies"] * 5
    score_b += summary_b["replies"] * 5

    # Penalty for tier1 (needs manual effort)
    if job_a.is_tier1:
        score_a -= 5
    if job_b.is_tier1:
        score_b -= 5

    if score_a > score_b:
        recommendation = (
            f"Prioritise {job_a.company} — {job_a.role} "
            f"(score {score_a} vs {score_b}). "
            f"{'Has referral!' if summary_a['referrals'] > 0 else ''} "
            f"Fit score {job_a.fit_score}/10."
        )
    elif score_b > score_a:
        recommendation = (
            f"Prioritise {job_b.company} — {job_b.role} "
            f"(score {score_b} vs {score_a}). "
            f"{'Has referral!' if summary_b['referrals'] > 0 else ''} "
            f"Fit score {job_b.fit_score}/10."
        )
    else:
        recommendation = (
            f"Both jobs score equally ({score_a}). "
            f"Consider which company/role aligns better with your goals."
        )

    return {
        "job_a": summary_a,
        "job_b": summary_b,
        "recommendation": recommendation,
    }


# ── Notification Builder ────────────────────────────────────────

def build_notifications(session):
    """Build smart notification alerts with company intelligence."""
    notifications = []
    today = datetime.utcnow().date()

    # 1. Drafts needing review (grouped by company with intelligence)
    drafts = session.query(OutreachLog).filter(
        OutreachLog.status == "draft").all()
    if drafts:
        companies_seen = {}
        for d in drafts:
            person = session.get(PeopleMapper, d.person_id)
            company = person.company if person else "Unknown"
            if company not in companies_seen:
                companies_seen[company] = 0
            companies_seen[company] += 1

        for company, count in companies_seen.items():
            total_c = session.query(func.count(PeopleMapper.id)).filter(
                PeopleMapper.company == company).scalar() or 0
            sent_c = session.query(func.count(OutreachLog.id)).filter(
                OutreachLog.status.in_(["sent", "replied"]),
                OutreachLog.person_id.in_(
                    session.query(PeopleMapper.id).filter(
                        PeopleMapper.company == company)
                ),
            ).scalar() or 0

            notifications.append({
                "id": f"draft-{company}",
                "type": "draft_review",
                "severity": "warning",
                "icon": "file-edit",
                "title": f"{count} draft{'s' if count > 1 else ''} for {company}",
                "detail": f"Already contacted {sent_c}/{total_c} people there",
                "action_url": "/outreach?status=draft",
                "action_label": "Review",
            })

    # 2. Approved ready to send
    approved_n = session.query(func.count(OutreachLog.id)).filter(
        OutreachLog.status == "approved").scalar() or 0
    if approved_n:
        notifications.append({
            "id": "approved-send",
            "type": "send_ready",
            "severity": "urgent",
            "icon": "send",
            "title": f"{approved_n} message{'s' if approved_n > 1 else ''} ready to send",
            "detail": "Approved and waiting for dispatch",
            "action_url": "/outreach?status=approved",
            "action_label": "Send",
        })

    # 3. Overdue follow-ups
    overdue = session.query(OutreachLog).filter(
        OutreachLog.status == "sent",
        OutreachLog.follow_up_date <= today,
        OutreachLog.follow_up_count == 0,
    ).all()
    for o in overdue[:5]:
        person = session.get(PeopleMapper, o.person_id)
        days_ago = (today - o.follow_up_date).days if o.follow_up_date else 0
        notifications.append({
            "id": f"followup-{o.id}",
            "type": "follow_up",
            "severity": "urgent",
            "icon": "clock",
            "title": f"Follow up: {person.name if person else '?'}",
            "detail": (
                f"@ {person.company if person else '?'} — "
                f"sent {days_ago + 4} days ago, no reply"
            ),
            "action_url": f"/contacts/{o.person_id}" if person else "/outreach",
            "action_label": "View",
        })

    # 4. Apply-now triggers (exhausted contacts, no referral)
    companies = session.query(
        PeopleMapper.company,
        func.count(PeopleMapper.id).label("total"),
    ).group_by(PeopleMapper.company).having(
        func.count(PeopleMapper.id) >= 2
    ).all()

    for company, total in companies:
        if not company:
            continue
        cids = session.query(PeopleMapper.id).filter(
            PeopleMapper.company == company)
        sent_n = session.query(func.count(OutreachLog.id)).filter(
            OutreachLog.status.in_(["sent", "replied", "no_reply"]),
            OutreachLog.person_id.in_(cids),
        ).scalar() or 0
        ref_n = session.query(func.count(ResponseTracker.id)).filter(
            ResponseTracker.response_type == "referral",
            ResponseTracker.person_id.in_(cids),
        ).scalar() or 0

        if sent_n >= min(total, 3) and ref_n == 0:
            jobs = session.query(JobShortlist).filter(
                JobShortlist.company == company,
                JobShortlist.status.in_(["shortlisted", "contacted", "follow_up"]),
            ).all()
            for j in jobs:
                notifications.append({
                    "id": f"apply-{j.id}",
                    "type": "apply_now",
                    "severity": "info",
                    "icon": "target",
                    "title": f"Apply directly: {company}",
                    "detail": (
                        f"{sent_n}/{total} contacted, no referral. "
                        f"Apply for {j.role}."
                    ),
                    "action_url": j.application_link or f"/jobs#job-{j.id}",
                    "action_label": "Apply",
                })

    # 5. High-value jobs needing enrichment
    high_jobs = session.query(JobShortlist).filter(
        JobShortlist.status == "shortlisted",
        JobShortlist.fit_score >= 8,
        JobShortlist.is_tier1 == False,
    ).order_by(JobShortlist.fit_score.desc()).limit(3).all()
    for j in high_jobs:
        has_c = session.query(func.count(PeopleMapper.id)).filter(
            PeopleMapper.job_id == j.id).scalar() or 0
        if has_c == 0:
            notifications.append({
                "id": f"enrich-{j.id}",
                "type": "enrich_needed",
                "severity": "info",
                "icon": "search",
                "title": f"Enrich: {j.company} (score {j.fit_score})",
                "detail": f"{j.role} — no contacts found yet",
                "action_url": f"/jobs#job-{j.id}",
                "action_label": "Enrich",
            })

    # Sort: urgent → warning → info
    order = {"urgent": 0, "warning": 1, "info": 2, "muted": 3}
    notifications.sort(key=lambda n: order.get(n["severity"], 99))
    return notifications


# ── Main Sage Chat Handler ──────────────────────────────────────

def process_sage_message(user_message, history=None, page_context="dashboard", api_key_override=""):
    """Process a message through Sage and return response with actions."""
    from src.config import Secrets

    session = get_session()
    try:
        context = build_sage_context(session)

        api_key = api_key_override or getattr(Secrets, "ANTHROPIC_API_KEY", "")
        if not api_key:
            return _fallback_response(user_message, context, session)

        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        # Build messages
        messages = []
        if history:
            for h in history[-10:]:  # Keep last 10 turns
                messages.append({
                    "role": h.get("role", "user"),
                    "content": h.get("content", ""),
                })
        messages.append({
            "role": "user",
            "content": (
                f"[Current page: {page_context}]\n"
                f"[Pipeline data]\n{context}\n\n"
                f"{user_message}"
            ),
        })

        # Call Claude with tools
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=SAGE_SYSTEM_PROMPT,
            tools=SAGE_TOOLS,
            messages=messages,
        )

        # Process response — handle tool use loops
        actions = []
        final_text = ""
        max_iterations = 5
        current_response = response

        for _ in range(max_iterations):
            has_tool_use = False

            for block in current_response.content:
                if block.type == "text":
                    final_text += block.text
                elif block.type == "tool_use":
                    has_tool_use = True
                    tool_result = execute_tool(
                        block.name, block.input, session
                    )

                    # Track actions for frontend
                    actions.append({
                        "tool": block.name,
                        "input": block.input,
                        "result": tool_result,
                    })

                    # Continue conversation with tool result
                    messages.append({
                        "role": "assistant",
                        "content": current_response.content,
                    })
                    messages.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(tool_result),
                        }],
                    })

            if not has_tool_use or current_response.stop_reason == "end_turn":
                break

            # Continue to get final text response
            current_response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                system=SAGE_SYSTEM_PROMPT,
                tools=SAGE_TOOLS,
                messages=messages,
            )

        # Extract frontend actions from tool results
        frontend_actions = []
        for a in actions:
            if a["tool"] == "navigate_to" and "url" in a["result"]:
                frontend_actions.append({
                    "type": "navigate",
                    "url": a["result"]["url"],
                })
            elif a["tool"] in ("edit_draft", "approve_drafts"):
                frontend_actions.append({
                    "type": "refresh",
                    "section": "outreach",
                })
            elif a["tool"] == "update_job_status":
                frontend_actions.append({
                    "type": "refresh",
                    "section": "jobs",
                })
            elif a["tool"] == "update_setting":
                frontend_actions.append({
                    "type": "refresh",
                    "section": "settings",
                })
            elif a["tool"] == "run_pipeline_action":
                frontend_actions.append({
                    "type": "toast",
                    "message": (
                        f"Pipeline action '{a['input'].get('action', '')}' "
                        + ("completed" if a["result"].get("status") == "ok" else "failed")
                    ),
                    "toast_type": (
                        "success" if a["result"].get("status") == "ok" else "error"
                    ),
                })
            elif a["tool"] == "start_application":
                frontend_actions.append({
                    "type": "refresh",
                    "section": "jobs",
                })

        # Build suggestions based on context
        suggestions = _build_suggestions(actions, page_context)

        return {
            "reply": final_text,
            "actions": frontend_actions,
            "suggestions": suggestions,
        }

    except Exception as e:
        log.exception("Sage error")
        return {
            "reply": f"I encountered an error: {e}\n\nTry asking again or check your API key in Settings.",
            "actions": [],
            "suggestions": ["Check settings", "Pipeline summary"],
        }
    finally:
        session.close()


def _fallback_response(user_message, context, session):
    """Simple keyword-based response when no Claude API key is set."""
    msg = user_message.lower()
    reply = ""

    if any(w in msg for w in ["status", "summary", "pipeline", "stats", "overview"]):
        reply = f"Here's your pipeline data:\n\n```\n{context}\n```"
    elif any(w in msg for w in ["draft", "pending", "review", "approve"]):
        drafts = session.query(func.count(OutreachLog.id)).filter(
            OutreachLog.status == "draft").scalar() or 0
        reply = (
            f"You have **{drafts}** pending drafts. "
            "Go to Outreach → Drafts to review them."
        )
    elif any(w in msg for w in ["recommend", "what should", "next", "today", "plan"]):
        result = _exec_recommendations(session, {})
        recs = result.get("recommendations", [])
        reply = "**Here's what I recommend:**\n\n" + "\n".join(
            f"• {r}" for r in recs
        )
    else:
        reply = (
            f"I need a Claude API key to give intelligent answers. "
            f"Set it in Settings → API Keys.\n\n"
            f"Quick stats: {context[:300]}..."
        )

    return {"reply": reply, "actions": [], "suggestions": [
        "Pipeline summary", "Show recommendations",
        "Show top jobs", "Check drafts",
    ]}


def _build_suggestions(actions, page_context):
    """Build contextual suggested prompts based on what just happened."""
    suggestions = []

    # Page-specific defaults
    page_suggestions = {
        "dashboard": [
            "What should I do today?",
            "Show high-priority jobs",
            "Pipeline summary",
        ],
        "jobs": [
            "Show top scoring jobs",
            "Find remote EU jobs",
            "Source new jobs",
        ],
        "contacts": [
            "Who needs follow-up?",
            "Company report for...",
            "Enrich new contacts",
        ],
        "outreach": [
            "Show pending drafts",
            "Approve all drafts",
            "Best performing variant?",
        ],
        "analytics": [
            "Which variant is best?",
            "Show conversion funnel",
            "A/B test report",
        ],
        "settings": [
            "Change daily limit to 25",
            "Update search roles",
            "Test API connections",
        ],
    }

    # If actions were taken, suggest follow-ups
    if actions:
        last_tool = actions[-1]["tool"]
        if last_tool == "approve_drafts":
            suggestions = ["Send approved messages", "Show outreach log", "What's next?"]
        elif last_tool == "edit_draft":
            suggestions = ["Approve this draft", "Show all drafts", "Edit another"]
        elif last_tool == "run_pipeline_action":
            suggestions = ["Show results", "Pipeline summary", "What's next?"]
        elif last_tool == "get_company_report":
            suggestions = ["Show drafts for this company", "Approve messages", "Apply directly"]
        elif last_tool == "search_pipeline":
            suggestions = ["Show details", "Company report", "Generate messages"]
        elif last_tool == "get_job_intelligence":
            suggestions = ["Start application", "Compare with another job", "Show contacts"]
        elif last_tool == "get_application_status":
            suggestions = ["Update application", "Show job intelligence", "What's next?"]
        elif last_tool == "start_application":
            suggestions = ["Check application status", "Generate CV", "Show job intelligence"]
        elif last_tool == "list_portals":
            suggestions = ["Start an application", "Show all jobs", "Which portal for...?"]
        elif last_tool == "compare_jobs":
            suggestions = ["Start application for winner", "Show job intelligence", "What's next?"]
    else:
        suggestions = page_suggestions.get(page_context, page_suggestions["dashboard"])

    return suggestions[:4]
