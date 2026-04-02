# Job Search Execution Agent — CLAUDE.md

## What This Is
A **local-first Python automation agent** that treats job applications like a sales pipeline. It sources roles, enriches contacts, generates personalised outreach (10 A/B tested variants), manages LinkedIn + email outreach within platform limits, tailors CVs per role, tracks responses, and sends daily digest reports.

**Owner:** Ratin Sharma — Senior AE, 7+ years sales (4+ SaaS), Dublin Ireland. Targeting AE/Sales Manager/Founding AE roles at SaaS startups and mid-market companies in Europe.

**Machine:** Windows 11, Lenovo Yoga 7, AMD Ryzen AI 7, 24GB RAM. Runs locally. No Docker, no cloud.

---

## Architecture

### Tech Stack
| Function | Tool |
|---|---|
| Language | Python 3.11+ |
| Database | SQLite + SQLAlchemy |
| Local Dashboard | FastAPI + Jinja2 (localhost:8000) |
| AI Engine | Anthropic Claude API (`claude-sonnet-4-20250514`) via `anthropic` SDK |
| Contact Enrichment | Apollo.io API |
| Email Outreach | Gmail API (OAuth2) |
| LinkedIn Outreach | LinkedIn API (OAuth2) — `POST /v2/invitations`, `POST /v2/messages` |
| Job Sourcing | Indeed API + CSV import (LinkedIn exports, IrishJobs) |
| CV Generation | python-docx → PDF |
| Scheduling | APScheduler |
| Config | .env (secrets) + YAML (settings) |

### Project Structure
```
outreach-agent/
├── CLAUDE.md
├── .env.example
├── config.yaml
├── requirements.txt
├── main.py                    # CLI entry point (Typer)
├── src/
│   ├── __init__.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py          # SQLAlchemy models (5 tables)
│   │   └── session.py         # DB connection + migrations
│   ├── sourcing/
│   │   ├── __init__.py
│   │   ├── indeed.py          # Indeed API job search
│   │   └── csv_import.py      # Import LinkedIn/IrishJobs CSV exports
│   ├── enrichment/
│   │   ├── __init__.py
│   │   └── apollo.py          # Apollo.io people finder
│   ├── messaging/
│   │   ├── __init__.py
│   │   ├── generator.py       # Claude API message personalisation
│   │   └── variants.py        # 10 variant definitions + weighting
│   ├── outreach/
│   │   ├── __init__.py
│   │   ├── gmail.py           # Gmail send + thread tracking
│   │   └── linkedin.py        # LinkedIn API invites + DMs
│   ├── cv/
│   │   ├── __init__.py
│   │   ├── tailor.py          # Claude API keyword extraction + bullet rewriting
│   │   └── builder.py         # python-docx CV builder → PDF
│   ├── testing/
│   │   ├── __init__.py
│   │   └── ab_engine.py       # A/B test tracking + statistical stopping rules
│   ├── tracking/
│   │   ├── __init__.py
│   │   └── response_handler.py # Reply classification + next-action routing
│   ├── digest/
│   │   ├── __init__.py
│   │   └── daily.py           # Daily KPI email
│   ├── scheduler/
│   │   ├── __init__.py
│   │   └── jobs.py            # APScheduler cron definitions
│   └── dashboard/
│       ├── __init__.py
│       ├── app.py             # FastAPI app
│       ├── routes.py
│       └── templates/
│           ├── base.html
│           ├── dashboard.html  # KPIs + daily summary
│           ├── jobs.html       # Job shortlist table
│           ├── contacts.html   # People mapper
│           ├── outreach.html   # Outreach log + approve/send
│           ├── analytics.html  # A/B test results + charts
│           └── cv.html         # CV versions table
├── data/
│   ├── master_profile.yaml    # Full career profile for CV tailoring
│   └── tier1_exclusions.yaml  # 46 companies excluded from automation
├── exports/                   # Generated CVs saved here
│   └── .gitkeep
└── tests/
    ├── test_sourcing.py
    ├── test_messaging.py
    ├── test_ab_engine.py
    └── test_cv_tailor.py
```

---

## Database Schema (5 Tables)

### 1. job_shortlist
Tracks every target role. Inspired by BeamJobs tracker fields.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | Auto |
| company | TEXT NOT NULL | |
| role | TEXT NOT NULL | Job title |
| location | TEXT | Ireland / Remote EU / Dublin / London |
| industry | TEXT | AI/SaaS, Fintech, etc. |
| company_stage | TEXT | Seed, Series A/B, Growth, Public |
| tier | INTEGER | 1 = high priority, 2 = medium, 3 = low |
| desired_segment | TEXT | SMB / Mid-Market / Enterprise |
| fit_score | INTEGER | 1-10 manual or auto score |
| status | TEXT | shortlisted / contacted / follow_up / applied / interviewing / rejected / offer |
| application_link | TEXT | URL to apply |
| description | TEXT | Full JD text |
| keywords | TEXT | JSON array of extracted JD keywords |
| is_tier1 | BOOLEAN DEFAULT FALSE | True = excluded from automation, manual apply only |
| sourcer_note | TEXT | Why this role is a fit |
| source | TEXT | indeed / linkedin / irishjobs / manual |
| created_at | DATETIME | |
| updated_at | DATETIME | |

### 2. people_mapper
Contacts at each target company. Up to 3 contacts per company.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| job_id | INTEGER FK → job_shortlist | |
| name | TEXT NOT NULL | |
| title | TEXT | Their role (Hiring Manager, Team Lead, Recruiter, etc.) |
| company | TEXT | |
| linkedin_url | TEXT | |
| email | TEXT | From Apollo |
| relationship | TEXT | hiring_manager / recruiter / peer / team_lead |
| priority | INTEGER | 1 = contact first, 2 = second, 3 = last resort |
| assigned_variant | TEXT | V1–V10 |
| next_action | TEXT | to_contact / contacted / follow_up / replied / archived |
| last_contact_date | DATE | |
| next_follow_up | DATE | |
| source | TEXT | apollo / manual |
| notes | TEXT | |
| created_at | DATETIME | |

### 3. outreach_log
Every message sent, with variant tracking for A/B testing.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| person_id | INTEGER FK → people_mapper | |
| job_id | INTEGER FK → job_shortlist | |
| variant | TEXT NOT NULL | V1–V10 |
| style | TEXT | referral / value_first / conversational |
| channel | TEXT | linkedin_dm / linkedin_inmail / email |
| message_body | TEXT | Full generated message |
| status | TEXT | draft / approved / sent / replied / no_reply |
| sent_at | DATETIME | Null if draft |
| follow_up_date | DATE | sent_at + 4 days |
| follow_up_count | INTEGER DEFAULT 0 | Max 1 follow-up |
| created_at | DATETIME | |

### 4. response_tracker
Outcomes from outreach. Connects contacts to referrals/interviews.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| outreach_id | INTEGER FK → outreach_log | |
| person_id | INTEGER FK → people_mapper | |
| job_id | INTEGER FK → job_shortlist | |
| response_type | TEXT | referral / interest / no_reply / not_fit / connected |
| response_date | DATETIME | |
| action_taken | TEXT | referral_to_apply / interview_scheduled / applied_direct / archived |
| notes | TEXT | |
| created_at | DATETIME | |

### 5. cv_versions
Tailored CV files per role.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| job_id | INTEGER FK → job_shortlist | |
| filename | TEXT | Ratin_Sharma_{Company}_{Role}_{Date}.pdf |
| file_path | TEXT | Full path in exports/ folder |
| tailored_bullets | TEXT | JSON of modified bullets |
| keywords_used | TEXT | JSON of JD keywords incorporated |
| created_at | DATETIME | |

---

## Message Testing Framework — 10 Variants

Three styles, 10 variants. Each uses personalisation tokens: `{Name}`, `{Company}`, `{Role}`, `{Topic}`, `{Event}`, `{Mutual}`, `{Achievement}`.

Claude API generates the final personalised version using the variant template + JD keywords + contact context.

### Style 1: Referral (V1–V3) — Ask for advice/referral before applying

**V1 — Referral-Warm (mutual connection)**
> Hi {Name}, {Mutual} suggested I connect. I see {Company} is hiring a {Role}. As an AI/SaaS sales rep with 7+ years closing $750K+, I'd value your advice. Could you possibly refer me? Can we chat this week?

**V2 — Referral-Direct**
> Hi {Name}, can you advise? I applied for {Role} at {Company}. I'm an experienced quota-hitting rep in AI/SaaS. Would love any tips or referrals. Might you have time for a quick call?

**V3 — Referral-Value (anchored to company news)**
> Quick question, {Name}. Congrats on {Company}'s recent {Achievement}! I helped SMBs scale SaaS sales to 150% quota. Could a referral get my resume seen? Should I send over my CV?

### Style 2: Value-First (V4–V6) — Lead with achievement

**V4 — Value-First**
> {Company} caught my eye for how you're approaching {Topic}. In 2025 I hit 150% quota selling SaaS to SMBs across Ireland. With that AI-selling experience, I'd love to discuss fit for {Role}. Can we set a 10-min chat?

**V5 — Value-First-Pitch**
> Driving SMB growth at {Company}? Hi {Name}, I've taken small startups to new markets (130% quota, $480K international contracts). With your product launch, my skills align well. Interested in an intro?

**V6 — Value-Question**
> Curious about {Company}'s SMB strategy. I've helped startups expand EU sales via consultative selling and MEDDIC. How is {Company} approaching SMB growth? Happy to swap notes!

### Style 3: Conversational (V7–V10) — Open dialogue, request insight

**V7 — Conversational (post-based)**
> Enjoyed your recent post on {Topic}. Hi {Name}, I'm a sales professional in AI/SaaS selling to SMBs. Any advice on breaking into your industry would be great! Could we connect?

**V8 — Conversational-Ask (event-based)**
> Congrats on {Event}, {Name}! I'm exploring roles like {Role} at {Company}. Can you share what makes a candidate stand out in applications? Would love 5 mins of advice.

**V9 — Conversational-Open**
> Hi {Name}, quick favour? I noticed {Company} looks for AI-savvy sales reps. What's the best way to express that fit in an application? Could you share your thoughts?

**V10 — Conversational-Relational (mutual connection)**
> Hi {Name}, saw we both know {Mutual}. I'm targeting a {Role} at {Company}. As someone in sales/AI, I'd appreciate any referral or insight you can offer. Open to a brief chat?

### Variant Assignment Rules
- Each new prospect gets ONE randomly assigned variant
- Balance: ensure roughly equal distribution across active variants
- Track: variant, style, reply (yes/no), referral (yes/no), channel

### A/B Testing Statistical Rules
These rules live in `src/testing/ab_engine.py`:

1. **Minimum sample:** Each variant needs at least 10 sends before evaluation
2. **Stopping rule:** After ≥30 total replies across all variants, compare reply rates
3. **Kill threshold:** If a variant's reply rate is ≥30% lower than the best performer → deactivate it
4. **Winner threshold:** If a variant's reply rate is ≥30% higher than average → increase its weight (double the assignment probability)
5. **Rebalance:** When a variant is killed, redistribute its weight proportionally to surviving variants
6. **Weekly report:** Dashboard shows variant performance table + bar chart
7. **Never kill below 4 variants:** Always keep at least 4 active variants for continued testing

---

## Pipeline Stages (Daily Run)

### Stage 1: Job Sourcing (08:00)
- Query Indeed API: "Account Executive", "Sales Manager", "BDM", "Founding AE" in Ireland/Remote Europe
- Accept CSV imports from LinkedIn job search exports
- Deduplicate by company + title combo
- Auto-flag Tier 1 companies (tier1_exclusions.yaml) → is_tier1=True, skip all automation
- Auto-score fit (1-10) based on keyword match to master_profile.yaml
- Store in `job_shortlist` with status="shortlisted"

### Stage 2: Contact Enrichment — Apollo.io (08:30)
- For each new non-Tier1 job, query Apollo.io:
  - Search: company name + titles: "Head of Sales", "VP Sales", "CRO", "Sales Director", "Hiring Manager", "Talent Acquisition", "Team Lead"
  - Return: name, email, LinkedIn URL, title
- Store in `people_mapper`, max 3 contacts per company
- Set priority: 1 = hiring manager, 2 = team lead/peer, 3 = recruiter
- Skip if no contacts found (log it, flag for manual research)

### Stage 3: Message Generation — Claude API (09:00)
- For each contact with next_action="to_contact":
  - Randomly assign a variant (V1–V10) using current weights
  - Call Claude API with system prompt containing:
    - Ratin's profile summary
    - The JD text + extracted keywords
    - The contact's name, title, relationship
    - The variant template
    - Instruction: "Personalise this message naturally. Use the contact's role and company context. Do NOT just fill in blanks — make it sound like a real human wrote it. Keep it under 100 words."
  - Store generated message in `outreach_log` with status="draft"
- Daily limit: generate max 20 drafts

### Stage 4: Outreach Execution (10:00 — after manual review)
- **All outreach starts as DRAFT. I review and approve in the dashboard before sending.**
- Approved drafts → send via appropriate channel:
  - LinkedIn DM (if already connected) → free, preferred
  - LinkedIn connection invite + message → counts against ~100/week limit
  - Email (via Gmail API) → for contacts with email, no LinkedIn connection
- Rate limits enforced:
  - Max 15-20 messages per day
  - Max ~15 LinkedIn invites per day (to stay under 100/week)
  - Max 1 person per company per day (stagger outreach)
  - Space invites throughout the day (not all at once)
- Update status to "sent", set follow_up_date = sent_at + 4 days
- Log channel used

### Stage 5: Response Handling (17:00)
- Check Gmail for replies to outreach threads
- Check LinkedIn for new messages/connections accepted
- Classify each response:

| Response Type | Action |
|---|---|
| Referral offered | Pause direct application. Apply through referral. Update status. |
| Interest / advice given | Apply immediately with tailored CV. Thank them. |
| Connected (no message reply) | Send a thank-you + soft ask in 2 days |
| No reply after 7 days | Send ONE follow-up (change CTA or add info). Max 1 follow-up. |
| No reply after 14 days | Apply directly. Archive contact. |
| Not a fit / declined | Thank them. Archive. Move on. |

- Store all in `response_tracker`
- Update `people_mapper.next_action` accordingly

### Stage 6: CV Tailoring — Claude API (on-demand, per application)
Before submitting any application:

1. **Parse JD** → Claude API extracts top keywords (skills, tools, qualifications, industry terms)
2. **Match bullets** → Compare JD keywords against master_profile.yaml bullets using semantic matching
3. **Rewrite bullets** → Claude API rewrites selected bullets to mirror JD language:
   - Keep real numbers (e.g. 150% quota, $750K closed)
   - Adapt phrasing to match JD terminology
   - Example: "Managed enterprise software sales" → "Exceeded 130% of quota selling AI-driven SaaS solutions to SMB clients"
4. **Build CV** → python-docx generates .docx:
   - ATS rules: NO images, NO tables, NO graphics, NO icons
   - Standard fonts: Arial or Calibri, ≥10pt
   - Standard headings: Summary, Experience, Education, Skills
   - Keywords from JD appear naturally throughout
5. **Export** → Convert to PDF
6. **Save** → `exports/Ratin_Sharma_{Company}_{Role}_{Date}.pdf`
7. **Log** → Store in `cv_versions` table with keywords used and tailored bullets

### Stage 7: A/B Testing Engine (continuous + weekly report)
- Runs continuously as data comes in
- Weekly: generate performance report
- Dashboard shows:
  - Variant performance table (sends, replies, reply rate, referrals, referral rate)
  - Bar chart comparing variants
  - Active/retired variant status
  - Recommendation: which variants to keep/kill

### Stage 8: Daily Digest Email (20:00)
Send to ratinsharma99@gmail.com:

```
📊 Daily Summary — {date}
━━━━━━━━━━━━━━━━━━━━━━━━
Jobs sourced today:        X
Contacts enriched:         X
Messages drafted:          X
Messages sent:             X / Target: 15-20
LinkedIn invites used:     X / Weekly limit: ~100
Replies received:          X
Referrals secured:         X
Applications submitted:    X
Follow-ups due tomorrow:   X

📈 Variant Performance (top 3):
  V{X} ({style}): XX% reply rate (n=XX sends)
  V{Y} ({style}): XX% reply rate (n=XX sends)
  V{Z} ({style}): XX% reply rate (n=XX sends)

⚠️ Flagged Tier 1 roles (manual apply):
  - {Company} — {Role} — {Link}
  - {Company} — {Role} — {Link}

📅 Tomorrow's plan:
  - X new contacts to message
  - X follow-ups due
  - X applications to submit
```

---

## LinkedIn Limits — CRITICAL

These limits MUST be enforced in code. Violations can get the account restricted.

| Limit | Free Account | Sales Navigator |
|---|---|---|
| Connection invites/week | ~100 | ~200-250 |
| InMails/month | 0 | 50 |
| Profile views/day | ~80-100 | 150+ |
| Messages to connections | Unlimited | Unlimited |

**Implementation rules:**
- Track daily and weekly LinkedIn invite counts in a `linkedin_quota` table or config
- Hard-stop at 15 invites/day (to stay safely under 100/week)
- Space invites: minimum 5-minute gap between sends
- Prefer free messages (to existing connections) over invites
- Never send invites in bulk bursts — stagger throughout the day
- Log every LinkedIn API call with timestamp

---

## Outreach Staggering Rules

For each company:
- Day 1: Message Person A (highest priority — hiring manager)
- Day 4: Follow-up to Person A if no reply
- Day 6: Message Person B (team lead / peer)
- Day 8: Final follow-up to Person A if still no reply
- Day 9: Message Person C (if exists)
- Day 11: If no referral from anyone → apply directly

Max 1 contact per company per day. Max 3 contacts per company total.

---

## Dashboard Views (FastAPI + Jinja2)

`http://localhost:8000`

| View | What It Shows |
|---|---|
| **Home** | Today's KPIs: jobs sourced, messages sent/target, replies, referrals, LinkedIn quota used. Cumulative weekly/monthly totals. |
| **Jobs** | Job shortlist table with filters: status, tier, location, industry. Kanban option: Shortlisted → Contacted → Follow-up → Applied → Interviewing. Tier 1 flags highlighted. |
| **Contacts** | People mapper table per job. Shows assigned variant, last contact, next action, priority. |
| **Outreach** | Outreach log with draft approval workflow. Select drafts → review message → approve/edit → send. Shows follow-up schedule. |
| **Analytics** | A/B test results: variant performance bar chart, reply rate table, active/retired variants. Weekly trend line. Conversion funnel: contacted → replied → referral → applied → interview. |
| **CVs** | CV versions table. Download links. Keywords used per version. |
| **Settings** | Edit config values from UI (daily limits, variant weights, search criteria). |

Style: Dark theme, Tailwind CDN, vanilla JS. Clean and functional.

---

## CLI Commands

```bash
# Full daily pipeline
python main.py run

# Individual stages
python main.py source              # Stage 1: Job sourcing
python main.py enrich              # Stage 2: Contact enrichment
python main.py generate            # Stage 3: Generate message drafts
python main.py send                # Stage 4: Send approved messages
python main.py check-replies       # Stage 5: Process responses
python main.py tailor --job-id 42  # Stage 6: Tailor CV for specific job
python main.py ab-report           # Stage 7: Print A/B test report
python main.py digest              # Stage 8: Send daily digest

# Dashboard
python main.py dashboard           # Start web UI at localhost:8000

# Utilities
python main.py import-csv --file jobs.csv --source linkedin
python main.py seed                # Seed with test data
python main.py quota               # Show LinkedIn invite quota status
python main.py stats               # Print quick stats to terminal
```

---

## Config Files

### .env.example
```
ANTHROPIC_API_KEY=sk-ant-...
APOLLO_API_KEY=...
GMAIL_CLIENT_ID=...
GMAIL_CLIENT_SECRET=...
GMAIL_REFRESH_TOKEN=...
LINKEDIN_CLIENT_ID=...
LINKEDIN_CLIENT_SECRET=...
LINKEDIN_ACCESS_TOKEN=...
```

### config.yaml
```yaml
agent:
  name: "Ratin Sharma"
  email: "ratinsharma99@gmail.com"
  daily_message_limit: 20
  daily_linkedin_invite_limit: 15
  weekly_linkedin_invite_limit: 100
  follow_up_days: 4
  max_follow_ups: 1
  max_contacts_per_company: 3
  max_contacts_per_company_per_day: 1
  linkedin_invite_gap_minutes: 5

search:
  roles:
    - "Account Executive"
    - "Sales Manager"
    - "Business Development Manager"
    - "Founding AE"
    - "Senior Account Executive"
  locations:
    - "Ireland"
    - "Remote - Europe"
    - "Dublin"
    - "London"
  industries:
    - "AI"
    - "SaaS"
    - "Fintech"
    - "Cybersecurity"
  exclude_keywords:
    - "intern"
    - "junior"
    - "entry level"
    - "graduate"

ab_testing:
  min_sends_per_variant: 10
  min_total_replies_to_evaluate: 30
  kill_threshold_pct: 30
  winner_boost_threshold_pct: 30
  min_active_variants: 4

variants:
  V1:  { style: "referral",       weight: 0.12, active: true }
  V2:  { style: "referral",       weight: 0.10, active: true }
  V3:  { style: "referral",       weight: 0.10, active: true }
  V4:  { style: "value_first",    weight: 0.10, active: true }
  V5:  { style: "value_first",    weight: 0.10, active: true }
  V6:  { style: "value_first",    weight: 0.08, active: true }
  V7:  { style: "conversational", weight: 0.10, active: true }
  V8:  { style: "conversational", weight: 0.10, active: true }
  V9:  { style: "conversational", weight: 0.10, active: true }
  V10: { style: "conversational", weight: 0.10, active: true }

schedule:
  source_jobs: "08:00"
  enrich_contacts: "08:30"
  generate_messages: "09:00"
  send_outreach: "10:00"
  check_replies: "17:00"
  daily_digest: "20:00"
```

### tier1_exclusions.yaml
```yaml
tier1_companies:
  - Salesforce
  - Google
  - Microsoft
  - HubSpot
  - TikTok
  - Rippling
  - Personio
  - AWS
  - Meta
  - Apple
  - Oracle
  - SAP
  - Adobe
  - Zoom
  - Slack
  - Atlassian
  - Snowflake
  - Databricks
  - Stripe
  - Twilio
  - Cloudflare
  - CrowdStrike
  - Palo Alto Networks
  - ServiceNow
  - Workday
  - Okta
  - Datadog
  - MongoDB
  - Elastic
  - Confluent
  - HashiCorp
  - GitLab
  - GitHub
  - Notion
  - Figma
  - Canva
  - Intercom
  - Zendesk
  - Freshworks
  - Monday.com
  - Asana
  - Airtable
  - Miro
  - Linear
  - Vercel
  - Supabase
  - PlanetScale
```

### master_profile.yaml
```yaml
name: "Ratin Sharma"
headline: "Senior Account Executive | SMB & Startup SaaS | AI-Powered Sales"
location: "Dublin, Ireland"
email: "ratinsharma99@gmail.com"
linkedin: "https://www.linkedin.com/in/ratin-sharma-accountexecutive6a359b138/"

summary: >
  Sales professional with 7+ years of experience and 4+ years in SaaS,
  specialising in consultative and value-based selling. Track record of
  closing $750K+ in deals and $480K in international contracts. Deep
  expertise in MEDDIC/MEDDPICC, founder-led sales, and high-velocity
  SMB/mid-market cycles. EU work authorised.

experience:
  - company: "With Taste"
    title: "Account Executive"
    location: "Dublin, Ireland"
    bullets:
      - "Consultative selling of premium food & beverage solutions to restaurants and hotels across Ireland"
      - "Full-cycle sales: prospecting, demos, negotiation, close"
      - "Built pipeline from scratch using cold outreach and referral strategies"

  - company: "Fund Administration Company"
    title: "Payments Project Lead"
    location: "Dublin, Ireland"
    bullets:
      - "Leading ISO 20022 migration across 5 payment applications"
      - "Built payment lifecycle dashboard for real-time transaction monitoring"
      - "Cross-functional coordination between compliance, tech, and operations"

  - company: "Brand Bing"
    title: "International Sales Manager"
    bullets:
      - "Closed $480K in international contracts across APAC and Middle East"
      - "Managed end-to-end sales cycle for enterprise and SMB clients"
      - "Built $540K ARR book of business from zero base"

  - company: "Simplilearn"
    title: "Inside Sales Specialist"
    bullets:
      - "Consistently exceeded 150%+ of monthly quota"
      - "Sold B2C and B2B edtech solutions via consultative phone sales"
      - "Managed 200+ monthly leads with systematic follow-up cadence"

education:
  - degree: "MBA in International Business"
    school: "Griffith College Dublin"
    thesis: "AI-driven predictive analytics for B2B lead scoring in Irish SaaS"

skills:
  - "MEDDIC/MEDDPICC"
  - "Salesforce"
  - "HubSpot"
  - "LinkedIn Sales Navigator"
  - "Outreach"
  - "Apollo"
  - "Gong"
  - "Cold calling"
  - "Discovery & demos"
  - "Contract negotiation"
  - "Founder-led sales"
  - "High-velocity sales"
  - "SMB/Mid-market"
  - "Startup sales"
  - "PLG sales motions"
  - "Freemium conversion"
  - "AI/SaaS selling"
  - "Consultative selling"
```

---

## Build Order (for Claude Code — sequential)

Build and test each step before moving to the next:

1. **DB + Models** — SQLite, all 5 SQLAlchemy models, session management, Alembic-lite migration
2. **Config loading** — Parse .env, config.yaml, tier1_exclusions.yaml, master_profile.yaml
3. **CLI framework** — main.py with Typer, wire up all commands as stubs
4. **Job sourcing** — Indeed API integration + CSV import + deduplication + Tier 1 flagging
5. **Contact enrichment** — Apollo.io API integration, max 3 contacts/company, priority assignment
6. **Message generation** — Claude API integration, 10 variant templates, personalisation engine
7. **A/B test engine** — Variant assignment, tracking, statistical stopping rules, reporting
8. **LinkedIn outreach** — LinkedIn API integration, invite sending, quota tracking, staggering
9. **Gmail outreach** — Gmail API send, thread tracking, reply detection
10. **Response handling** — Reply classification, next-action routing, status updates
11. **CV tailoring** — Claude API keyword extraction + bullet rewriting + python-docx builder
12. **Daily digest** — Compile stats, generate email, send via Gmail
13. **Dashboard** — FastAPI + Jinja2 UI, all views, draft approval workflow
14. **Scheduler** — APScheduler cron jobs for automated daily runs

---

## Critical Rules

1. **All outreach starts as DRAFT.** I review and approve before sending. No auto-send until I explicitly enable it.
2. **46 Tier 1 companies are ALWAYS excluded from automation.** Flag for manual application only.
3. **LinkedIn limits are hard-enforced in code.** Never exceed 15 invites/day or 100/week. Add safety margins.
4. **Every message must sound human-written.** Claude API must personalise based on JD, contact role, and company context — not just fill in blanks.
5. **Max 1 contact per company per day.** Stagger outreach over 1-2 weeks per company.
6. **Max 1 follow-up per contact.** If no reply after follow-up, move on or apply directly.
7. **Rate limit all API calls.** Apollo: 1 req/sec. LinkedIn: 5-min gaps between invites. Claude: respect token limits.
8. **Store everything locally.** SQLite, no external database, no cloud.
9. **GDPR compliance.** Don't store unnecessary personal data. Delete contact data when no longer needed.
10. **Log everything.** Every API call, every message, every error — for debugging and audit.
