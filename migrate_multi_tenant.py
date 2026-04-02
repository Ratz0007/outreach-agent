import sqlite3
import os
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "outreach.db"

def migrate():
    if not DB_PATH.exists():
        print(f"DB not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Find the primary user (or fallback to ID 1)
    cursor.execute("SELECT id FROM users ORDER BY created_at ASC LIMIT 1")
    row = cursor.fetchone()
    primary_user_id = row[0] if row else 1
    
    if not row:
        print("No users found. Creating a default primary user.")
        cursor.execute("INSERT INTO users (username, email, password_hash) VALUES ('legacy_owner', 'legacy@local.host', 'none')")
        primary_user_id = cursor.lastrowid
        conn.commit()

    print(f"Assigning legacy data to User ID {primary_user_id}")

    tables_to_migrate = [
        "job_shortlist",
        "people_mapper",
        "outreach_log",
        "response_tracker",
        "cv_versions",
        "application_memory"
    ]

    for table in tables_to_migrate:
        try:
            # Check if column exists
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [c[1] for c in cursor.fetchall()]
            
            if "user_id" not in columns:
                print(f"Adding user_id to {table}...")
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER REFERENCES users(id)")
                
                # Assign to primary user
                cursor.execute(f"UPDATE {table} SET user_id = ?", (primary_user_id,))
                print(f"Updated existing records in {table}.")
            else:
                print(f"Table {table} already has user_id.")
        except Exception as e:
            print(f"Error migrating {table}: {e}")

    conn.commit()
    conn.close()
    print("Migration complete!")

if __name__ == "__main__":
    migrate()
