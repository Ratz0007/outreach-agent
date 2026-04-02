"""SQLAlchemy models for the Job Search Execution Agent — 6 tables."""

from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, Text, Boolean, DateTime, Date, Float,
    ForeignKey, create_engine, event
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class JobShortlist(Base):
    """Tracks every target role. Inspired by BeamJobs tracker fields."""
    __tablename__ = "job_shortlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    company = Column(Text, nullable=False)
    role = Column(Text, nullable=False)
    location = Column(Text)
    industry = Column(Text)
    company_stage = Column(Text)  # Seed, Series A/B, Growth, Public
    tier = Column(Integer)  # 1 = high priority, 2 = medium, 3 = low
    desired_segment = Column(Text)  # SMB / Mid-Market / Enterprise
    fit_score = Column(Integer)  # 1-10
    status = Column(Text, default="shortlisted")  # shortlisted/contacted/follow_up/applied/interviewing/rejected/offer
    application_link = Column(Text)
    description = Column(Text)  # Full JD text
    keywords = Column(Text)  # JSON array of extracted JD keywords
    is_tier1 = Column(Boolean, default=False)  # True = excluded from automation
    sourcer_note = Column(Text)
    source = Column(Text)  # indeed/linkedin/irishjobs/adzuna/manual
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    contacts = relationship("PeopleMapper", back_populates="job", cascade="all, delete-orphan")
    outreach_logs = relationship("OutreachLog", back_populates="job", cascade="all, delete-orphan")
    responses = relationship("ResponseTracker", back_populates="job", cascade="all, delete-orphan")
    cv_versions = relationship("CVVersion", back_populates="job", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Job {self.id}: {self.company} — {self.role}>"


class PeopleMapper(Base):
    """Contacts at each target company. Up to 3 contacts per company."""
    __tablename__ = "people_mapper"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    job_id = Column(Integer, ForeignKey("job_shortlist.id"), nullable=False)
    name = Column(Text, nullable=False)
    title = Column(Text)
    company = Column(Text)
    linkedin_url = Column(Text)
    email = Column(Text)
    relationship_type = Column(Text)  # hiring_manager/recruiter/peer/team_lead
    priority = Column(Integer)  # 1 = contact first, 2 = second, 3 = last resort
    assigned_variant = Column(Text)  # V1–V10
    next_action = Column(Text, default="to_contact")  # to_contact/contacted/follow_up/replied/archived
    last_contact_date = Column(Date)
    next_follow_up = Column(Date)
    source = Column(Text)  # apollo/manual
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    job = relationship("JobShortlist", back_populates="contacts")
    outreach_logs = relationship("OutreachLog", back_populates="person", cascade="all, delete-orphan")
    responses = relationship("ResponseTracker", back_populates="person", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Contact {self.id}: {self.name} @ {self.company}>"


class OutreachLog(Base):
    """Every message sent, with variant tracking for A/B testing."""
    __tablename__ = "outreach_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    person_id = Column(Integer, ForeignKey("people_mapper.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("job_shortlist.id"), nullable=False)
    variant = Column(Text, nullable=False)  # V1–V10
    style = Column(Text)  # referral/value_first/conversational
    channel = Column(Text)  # linkedin_dm/linkedin_inmail/email
    message_body = Column(Text)
    status = Column(Text, default="draft")  # draft/approved/sent/replied/no_reply
    sent_at = Column(DateTime)
    follow_up_date = Column(Date)  # sent_at + 4 days
    follow_up_count = Column(Integer, default=0)  # Max 1 follow-up
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    person = relationship("PeopleMapper", back_populates="outreach_logs")
    job = relationship("JobShortlist", back_populates="outreach_logs")
    responses = relationship("ResponseTracker", back_populates="outreach", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Outreach {self.id}: {self.variant} → {self.status}>"


class ResponseTracker(Base):
    """Outcomes from outreach. Connects contacts to referrals/interviews."""
    __tablename__ = "response_tracker"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    outreach_id = Column(Integer, ForeignKey("outreach_log.id"), nullable=False)
    person_id = Column(Integer, ForeignKey("people_mapper.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("job_shortlist.id"), nullable=False)
    response_type = Column(Text)  # referral/interest/no_reply/not_fit/connected
    response_date = Column(DateTime)
    action_taken = Column(Text)  # referral_to_apply/interview_scheduled/applied_direct/archived
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    outreach = relationship("OutreachLog", back_populates="responses")
    person = relationship("PeopleMapper", back_populates="responses")
    job = relationship("JobShortlist", back_populates="responses")

    def __repr__(self):
        return f"<Response {self.id}: {self.response_type}>"


class CVVersion(Base):
    """Tailored CV files per role."""
    __tablename__ = "cv_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    job_id = Column(Integer, ForeignKey("job_shortlist.id"), nullable=False)
    filename = Column(Text)  # Ratin_Sharma_{Company}_{Role}_{Date}.pdf
    file_path = Column(Text)
    tailored_bullets = Column(Text)  # JSON of modified bullets
    keywords_used = Column(Text)  # JSON of JD keywords incorporated
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    job = relationship("JobShortlist", back_populates="cv_versions")

    def __repr__(self):
        return f"<CV {self.id}: {self.filename}>"


class ApplicationMemory(Base):
    """Deep memory of every job application step, form field, and action taken."""
    __tablename__ = "application_memory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    job_id = Column(Integer, ForeignKey("job_shortlist.id"), nullable=False)
    portal = Column(Text)  # indeed/linkedin/greenhouse/lever/workday/manual
    portal_status = Column(Text, default="pending")  # pending/in_progress/completed/blocked/manual_needed
    application_url = Column(Text)
    form_data = Column(Text)  # JSON: all form fields filled
    documents_uploaded = Column(Text)  # JSON: list of uploaded files
    steps_completed = Column(Text)  # JSON: list of completed steps
    steps_remaining = Column(Text)  # JSON: list of remaining steps
    blocked_reason = Column(Text)  # Why automation stopped (captcha, login, unsupported field)
    blocked_step = Column(Text)  # Which specific step is blocked
    ai_summary = Column(Text)  # Claude-generated summary of application state
    extra_data = Column(Text)  # JSON: salary, benefits, extracted JD data
    last_action = Column(Text)  # Last action taken
    last_action_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    job = relationship("JobShortlist", backref="applications")

    def __repr__(self):
        return f"<ApplicationMemory {self.id}: job={self.job_id} portal={self.portal} status={self.portal_status}>"


class PortalConnector(Base):
    """Registry of supported job portals and their automation status."""
    __tablename__ = "portal_connectors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    portal_name = Column(Text, nullable=False, unique=True)  # linkedin/indeed/greenhouse/lever/workday
    display_name = Column(Text)
    support_level = Column(Text, default="manual")  # full/partial/manual
    can_detect_listings = Column(Boolean, default=False)
    can_extract_details = Column(Boolean, default=False)
    can_auto_apply = Column(Boolean, default=False)
    can_track_status = Column(Boolean, default=False)
    requires_login = Column(Boolean, default=True)
    login_method = Column(Text)  # oauth/credentials/manual
    base_url = Column(Text)
    api_endpoint = Column(Text)
    notes = Column(Text)
    is_active = Column(Boolean, default=True)
    last_tested = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<PortalConnector {self.id}: {self.portal_name} ({self.support_level})>"


class User(Base):
    """User accounts for dashboard authentication."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(Text, nullable=False, unique=True, index=True)
    email = Column(Text, nullable=False, unique=True, index=True)
    password_hash = Column(Text)  # Nullable for Google Auth users
    google_id = Column(Text, unique=True, index=True)
    full_name = Column(Text)
    picture_url = Column(Text)
    linkedin_url = Column(Text)
    is_active = Column(Boolean, default=True)
    settings = Column(Text)  # JSON blob for user-specific settings
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)

    def __repr__(self):
        return f"<User {self.id}: {self.username}>"
