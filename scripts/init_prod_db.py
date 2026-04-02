import os
from sqlalchemy import create_engine
from src.db.models import Base

# Database URL from subagent
DATABASE_URL = "postgresql://postgres.augfwuxqgrlexeyochom:BtqHArk6e8jNbvopaKUG@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"

def init_db():
    print(f"Connecting to {DATABASE_URL}...")
    engine = create_engine(DATABASE_URL)
    
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    print("Database initialization complete!")

if __name__ == "__main__":
    init_db()
