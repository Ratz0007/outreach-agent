import sqlite3
import os

db_path = "outreach.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("SELECT COUNT(*) FROM users")
    users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM job_shortlist")
    jobs = cursor.fetchone()[0]
    print(f"Users: {users}, Jobs: {jobs}")
except Exception as e:
    print("Error:", e)
conn.close()
