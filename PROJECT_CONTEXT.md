# Outreach Agent — Project Context for Claude Chat

## What This Is

A local Python app that automates my job search like a sales pipeline. It sources jobs, finds contacts at target companies, generates personalised outreach messages (10 A/B tested variants), manages LinkedIn + email outreach, tailors CVs per role, and tracks everything through a web dashboard.

**Owner:** Ratin Sharma — Senior AE, 7+ years sales (4+ SaaS), Dublin Ireland. Targeting AE/Sales Manager/Founding AE roles at SaaS startups in Europe.

**Machine:** Windows 11, Python 3.11+, runs locally on localhost:8000.

---

## Current State (Live Data)

- 105 jobs sourced (via Adzuna API across GB, DE, NL, FR)
- 46 contacts enriched (via Hunter.io + Apollo + Snov.io + mock fallback)
- 46 outreach messages generated (Claude-personalised, 10 variants)
- 4 tailored CVs generated
- Dashboard running at localhost:8000 with auth system

---

## Tech Stack

- **Backend:** Python 3.11, FastAPI, SQLAlchemy + SQLite
- **Frontend:** Jinja2 templates, Tailwind CDN, vanilla JS
- **AI:** Claude API (claude-sonnet-4-20250514) for message personalisation + CV tailoring
- **APIs:** Adzuna (jobs), Hunter.io (contacts), Apollo.io (domains), Snov.io (emails), Gmail API (outreach)
- **LinkedIn:** Manual copy-paste mode with quota tracking (API too restricted on free tier)
- **CV Generation:** python-docx with region-aware formatting (7 regions)

---

## Database (6 Tables)

**job_shortlist** — Target roles. Key fields: company, role, location, fit_score (1-10), status (shortlisted/contacted/follow_up/applied/interviewing/rejected/offer), description, keywords (JSON), is_tier1, source, application_link.

**people_mapper** — Contacts per company (max 3). Key fields: job_id (FK), name, title, company, linkedin_url, email, relationship_type (hiring_manager/recruiter/peer/team_lead), priority (1-3), assigned_variant (V1-V10), next_action, source.

**outreach_log** — Every message. Key fields: person_id (FK), job_id (FK), variant (V1-V10), style (referral/value_first/conversational), channel (linkedin/email), message_body, status (draft/approved/sent/replied/no_reply), follow_up_date.

**response_tracker** — Reply outcomes. Key fields: outreach_id (FK), response_type (referral/interest/no_reply/not_fit/connected), action_taken.

**cv_versions** — Tailored CVs. Key fields: job_id (FK), filename, file_path, keywords_used (JSON), tailored_bullets (JSON).

**users** — Dashboard auth. Key fields: username, email, password_hash, full_name, settings (JSON blob for per-user config).

---

## Project Structure

```
job app auto/
├── main.py                     # Typer CLI (source, enrich, generate, send, tailor, etc.)
├── config.yaml                 # Agent settings, search criteria, variant weights
├── .env                        # API keys (Anthropic, Adzuna, Hunter, Snov, Apollo, Gmail)
├── outreach.db                 # SQLite database
├── src/
│   ├── config.py               # Loads .env + YAML configs
│   ├── auth.py                 # Login/register, password hashing, session cookies
│   ├── db/models.py            # 6 SQLAlchemy models
│   ├── db/session.py           # SQLite connection + WAL mode
│   ├── sourcing/adzuna.py      # Multi-country job search (GB, DE, NL, FR)
│   ├── sourcing/fit_scorer.py  # Auto fit-score 1-10 based on profile keyword match
│   ├── enrichment/apollo.py    # Multi-source: Hunter → Apollo domain → Snov email → mock
│   ├── messaging/generator.py  # Claude API message personalisation
│   ├── messaging/variants.py   # 10 variant templates + weighted random assignment
│   ├── outreach/gmail.py       # Gmail API send + thread tracking
│   ├── outreach/linkedin.py    # LinkedIn quota tracking (manual mode)
│   ├── cv/tailor.py            # Claude API keyword extraction + bullet rewriting
│   ├── cv/builder.py           # python-docx CV builder (region-aware)
│   ├── cv/cover_letter.py      # Claude-generated cover letters
│   ├── cv/regions.py           # 7 region formats (US, UK, DACH, Nordics, etc.)
│   ├── testing/ab_engine.py    # A/B test tracking + statistical stopping rules
│   ├── tracking/response_handler.py  # Reply classification + next-action routing
│   ├── digest/daily.py         # Daily KPI email
│   └── dashboard/
│       ├── app.py              # FastAPI app
│       ├── routes.py           # All routes + auth + settings + chat API
│       └── templates/          # 10 Jinja2 templates (base, dashboard, jobs, contacts,
│                               #   outreach, analytics, cv, login, register, settings)
├── data/
│   ├── master_profile.yaml     # Full career profile for CV tailoring
│   └── tier1_exclusions.yaml   # 46 companies excluded from automation
└── exports/                    # Generated CV PDFs
```

---

## 8-Stage Pipeline

1. **Source Jobs** — Adzuna API searches for AE/Sales roles across 4 countries. Auto-scores fit, flags 46 Tier 1 companies for manual-only.
2. **Enrich Contacts** — Hunter.io (primary, 50 free/month) → Apollo (domain lookup) → Snov.io (email by name) → mock fallback. Max 3 contacts/company, prioritised by role.
3. **Generate Messages** — Claude API personalises 1 of 10 variant templates per contact. Stores as draft. Max 20/day.
4. **Send Outreach** — All drafts require manual approval. Gmail API for email, manual copy-paste for LinkedIn. Rate-limited (15 LinkedIn/day, 100/week).
5. **Handle Responses** — Classifies replies (referral/interest/no_reply/declined), routes next actions.
6. **Tailor CVs** — Claude extracts JD keywords, rewrites bullets to match, builds ATS-friendly docx+PDF. Region-aware formatting.
7. **A/B Testing** — Tracks 10 variants. After 30+ replies, kills underperformers (30% below best), boosts winners. Min 4 active variants.
8. **Daily Digest** — KPI email with stats, top variants, Tier 1 flags, tomorrow's plan.

---

## 10 Message Variants

**Referral style (V1-V3):** Ask for advice/referral before applying. Warm intro, mutual connections, company news hooks.

**Value-first style (V4-V6):** Lead with achievements (150% quota, $480K contracts). Position as a fit, request quick chat.

**Conversational style (V7-V10):** Open dialogue, request insight. Post-based, event-based, open asks, relational.

Each uses tokens: {Name}, {Company}, {Role}, {Topic}, {Event}, {Mutual}, {Achievement}. Claude personalises each to sound human-written.

---

## Dashboard (localhost:8000)

Light theme, sidebar navigation, Inter font. 10 pages:

- **Login/Register** — Session-based auth with bcrypt passwords
- **Dashboard** — KPI cards, pipeline funnel, today's activity, top jobs, quick actions
- **Jobs** — Table with search, filters (score/source/status), sort. LinkedIn + Indeed links, apply button, expandable JD, CV generator
- **Contacts** — Table with filters (priority/relationship/status/source), LinkedIn profiles, email links
- **Outreach** — Message cards with approve/send workflow, copy-to-clipboard for LinkedIn, filter by variant/style/channel
- **Analytics** — A/B variant performance table + bar chart, response breakdown
- **CVs** — Download table with keyword badges, search + sort
- **Settings** — Full config: API keys (13 fields), search preferences, outreach limits, A/B testing params, Tier 1 companies. Saves to DB + .env file.
- **Chat Widget** — Claude-powered chatbot with full pipeline data context on every page

---

## Critical Rules

1. All outreach starts as DRAFT — manual approval required before sending
2. 46 Tier 1 companies always excluded from automation (Salesforce, Google, HubSpot, etc.)
3. LinkedIn limits hard-enforced: 15 invites/day, 100/week, 5-min gaps
4. Every message must sound human-written, not template-filled
5. Max 1 contact per company per day, max 1 follow-up per contact
6. Everything stored locally in SQLite — no cloud, no external DB
7. Rate limit all API calls (Apollo 1/sec, LinkedIn 5-min gaps)

---

## CLI Commands

```
py -3 main.py run                     # Full pipeline
py -3 main.py source                  # Source jobs from Adzuna
py -3 main.py enrich                  # Enrich contacts (Hunter/Apollo/Snov)
py -3 main.py generate                # Generate Claude-personalised drafts
py -3 main.py send                    # Send approved messages
py -3 main.py check-replies           # Process Gmail replies
py -3 main.py tailor --job-id 42      # Tailor CV for specific job
py -3 main.py ab-report               # Print A/B test performance
py -3 main.py digest                  # Send daily digest email
py -3 main.py dashboard               # Start web UI at localhost:8000
py -3 main.py seed                    # Seed with test data
```

---

## Key Config

**API Keys (.env):** ANTHROPIC_API_KEY, ADZUNA_APP_ID, ADZUNA_APP_KEY, APOLLO_API_KEY, HUNTER_API_KEY, SNOV_USER_ID, SNOV_SECRET, GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN

**Search (config.yaml):** Roles: Account Executive, Sales Manager, BDM, Founding AE, Senior AE. Locations: Ireland, Remote Europe, Dublin, London. Industries: AI, SaaS, Fintech, Cybersecurity. Excludes: intern, junior, entry level, graduate.

**Limits:** 20 messages/day, 15 LinkedIn invites/day, 100/week, 4-day follow-up, max 1 follow-up, max 3 contacts/company.

---

## Profile Summary (for context)

Ratin Sharma — Senior AE with 7+ years experience (4+ SaaS). Based in Dublin, Ireland. MBA from Griffith College Dublin. Key achievements: $750K+ deals closed, $480K international contracts (APAC/Middle East), $540K ARR from zero, 150%+ quota consistently. Skills: MEDDIC, Salesforce, HubSpot, consultative selling, founder-led sales, SMB/mid-market, AI/SaaS selling. Previous roles at With Taste (AE), Fund Admin Co (Payments Lead), Brand Bing (International Sales Manager), Simplilearn (Inside Sales).
