"""Database connection and session management for SQLite."""

import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from src.db.models import Base


# Database configuration
# 1. Check for DATABASE_URL (PostgreSQL - Production/Neon)
# 2. Check for VERCEL (SQLite - /tmp)
# 3. Fallback to local SQLite
DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    # Handle the 'postgres://' vs 'postgresql://' issue if from older Heroku/Render configs
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    # Fast-fail pooling logic for Postgres
    engine = create_engine(
        DATABASE_URL, 
        pool_size=10, 
        max_overflow=20, 
        pool_pre_ping=True
    )
else:
    # SQLite logic
    DB_DIR = Path(__file__).resolve().parent.parent.parent
    _local_db = DB_DIR / "outreach.db"

    if os.environ.get("VERCEL"):
        # Vercel serverless: use writable /tmp directory
        DB_PATH = Path("/tmp/outreach.db")
    else:
        DB_PATH = _local_db

    DATABASE_URL = f"sqlite:///{DB_PATH}"
    engine = create_engine(DATABASE_URL, echo=False)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable WAL mode and foreign keys for SQLite."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db():
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)
    _seed_demo_user()


def _seed_demo_user():
    """Create a demo user if none exists (useful for Vercel's ephemeral /tmp DB)."""
    from src.db.models import User
    session = SessionLocal()
    try:
        if session.query(User).filter(User.username == "demo").first():
            return
        from src.auth import hash_password
        demo = User(
            username="demo",
            email="demo@outreach-agent.app",
            password_hash=hash_password("demo1234"),
            full_name="Demo User",
            settings="{}",
        )
        session.add(demo)
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def get_session() -> Session:
    """Get a new database session. Caller must close it."""
    return SessionLocal()
