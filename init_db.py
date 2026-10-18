# -*- coding: utf-8 -*-
"""
Database initializer for Sewa Setu on Render / container startup.
Checks if schema already exists; if not, loads schema.sql and seed.sql via psql.
"""
import os
import sys
import time
import subprocess
import psycopg2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "app"))
sys.path.insert(0, os.path.join(BASE_DIR, "mcp"))


def wait_for_db(max_retries=30, delay=2):
    db_url = os.environ.get("DATABASE_URL")
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    for i in range(max_retries):
        try:
            if db_url:
                conn = psycopg2.connect(db_url)
            else:
                conn = psycopg2.connect(
                    host=os.environ.get("DB_HOST", "127.0.0.1"),
                    port=os.environ.get("DB_PORT", "5432"),
                    dbname=os.environ.get("DB_NAME", "sewasetu"),
                    user=os.environ.get("DB_USER", "sewasetu"),
                    password=os.environ.get("DB_PASS", "sewasetu123"),
                )
            conn.close()
            print("Database is ready!")
            return True
        except Exception as e:
            print(f"Waiting for database ({i+1}/{max_retries}): {e}")
            time.sleep(delay)
    return False


def init_tables():
    db_url = os.environ.get("DATABASE_URL")
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    if db_url:
        conn = psycopg2.connect(db_url)
    else:
        conn = psycopg2.connect(
            host=os.environ.get("DB_HOST", "127.0.0.1"),
            port=os.environ.get("DB_PORT", "5432"),
            dbname=os.environ.get("DB_NAME", "sewasetu"),
            user=os.environ.get("DB_USER", "sewasetu"),
            password=os.environ.get("DB_PASS", "sewasetu123"),
        )
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("SELECT to_regclass('public.applications');")
    table_exists = cur.fetchone()[0] is not None

    app_count = 0
    if table_exists:
        cur.execute("SELECT count(*) FROM applications;")
        app_count = cur.fetchone()[0]

    cur.close()
    conn.close()

    schema_path = os.path.join(BASE_DIR, "app", "schema.sql")
    seed_path = os.path.join(BASE_DIR, "seed", "seed.sql")

    env = os.environ.copy()
    if not db_url:
        env["PGPASSWORD"] = os.environ.get("DB_PASS", "sewasetu123")

    if not table_exists:
        print("Schema not found. Loading schema.sql via psql...")
        if db_url:
            subprocess.run(["psql", db_url, "-f", schema_path], check=True)
        else:
            subprocess.run(["psql", "-h", "127.0.0.1", "-p", "5432", "-U", "sewasetu", "-d", "sewasetu", "-f", schema_path], env=env, check=True)
        print("Schema loaded.")

    if app_count == 0 and os.path.exists(seed_path):
        print("Applications table is empty. Loading seed.sql via psql...")
        if db_url:
            subprocess.run(["psql", db_url, "-f", seed_path], check=True)
        else:
            subprocess.run(["psql", "-h", "127.0.0.1", "-p", "5432", "-U", "sewasetu", "-d", "sewasetu", "-f", seed_path], env=env, check=True)
        print("Seed data loaded successfully.")
    else:
        print(f"Database already populated ({app_count} applications found).")


if __name__ == "__main__":
    if not wait_for_db():
        print("ERROR: Database connection failed.")
        sys.exit(1)
    init_tables()
    print("Database initialization complete.")
