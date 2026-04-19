#!/usr/bin/env python3
"""Run db/migrations/001_initial_schema.sql against the Supabase project.

Usage:
  DB_PASSWORD=<your-supabase-db-password> python3 db/run_migration.py

The DB password is set on the Supabase dashboard under
Project Settings → Database → Database password.
"""

import os, sys
from pathlib import Path

try:
    import psycopg2
except ImportError:
    print("Installing psycopg2-binary…")
    os.system("pip install psycopg2-binary -q")
    import psycopg2

from dotenv import load_dotenv
load_dotenv(".env")

ref = os.getenv("SUPABASE_URL","").replace("https://","").split(".")[0]
pwd = os.getenv("DB_PASSWORD") or os.getenv("SUPABASE_DB_PASSWORD") or ""

if not ref:
    sys.exit("SUPABASE_URL not set in .env")
if not pwd:
    pwd = input("Enter Supabase database password: ").strip()

conn_str = f"postgresql://postgres:{pwd}@db.{ref}.supabase.co:5432/postgres"
sql = Path("db/migrations/001_initial_schema.sql").read_text()

print(f"Connecting to db.{ref}.supabase.co …")
try:
    conn = psycopg2.connect(conn_str)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(sql)
    print("Migration applied successfully.")
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' ORDER BY table_name;
    """)
    tables = [r[0] for r in cur.fetchall()]
    print(f"Tables: {tables}")
    conn.close()
except Exception as e:
    sys.exit(f"Migration failed: {e}")
