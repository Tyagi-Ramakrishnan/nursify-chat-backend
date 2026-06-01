"""
One-time seed script — run manually:
  python seed_events.py
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL env var not set")

con = psycopg2.connect(DATABASE_URL)
cur = con.cursor()
cur.execute("""
    INSERT INTO events_events
        (name, event_date, registration_deadline, description,
         medical_clearance_note, active)
    VALUES (%s, %s, %s, %s, %s, %s)
    RETURNING id, name
""", (
    "Nursify Tox Party",
    "2026-06-13 17:00:00-06",   # America/Denver (MDT = UTC-6)
    "2026-06-11 23:59:00-06",
    None,
    "Medical clearance required by Medical Director prior to party. "
    "Must register by June 11 to attend.",
    True,
))
row = cur.fetchone()
con.commit()
cur.close()
con.close()

print(f"Seeded event: {row[1]} ({row[0]})")
