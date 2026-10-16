# -*- coding: utf-8 -*-
"""
Database helper utilities for Sewa Setu MCP servers.
Read-mostly layer directly accessing PostgreSQL, ensuring fast responses
while preserving atomic transactions.
"""
import os
import sys
import configparser
import psycopg2
import psycopg2.extras

# Allow importing core_rules
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
import core_rules

_cfg = configparser.ConfigParser()
for p in ("/app/config/app.ini", os.path.join(os.path.dirname(__file__), "..", "app", "config", "app.ini"), "app/config/app.ini"):
    if os.path.exists(p):
        _cfg.read(p)
        break


def _cfg_get(section, key, env_var, default=""):
    val = os.environ.get(env_var)
    if val:
        return val
    try:
        return _cfg.get(section, key)
    except Exception:
        return default


DB_HOST = _cfg_get("database", "host", "DB_HOST", "db")
DB_PORT = _cfg_get("database", "port", "DB_PORT", "5432")
DB_NAME = _cfg_get("database", "name", "DB_NAME", "sewasetu")
DB_USER = _cfg_get("database", "user", "DB_USER", "sewasetu")
DB_PASS = _cfg_get("database", "password", "DB_PASS", "sewasetu123")

ACTIVE_STATUSES = core_rules.ACTIVE_STATUSES


def get_db():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def fetchone(sql, params=()):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, params)
    row = cur.fetchone()
    cur.close(); conn.close()
    return dict(row) if row else None


def fetchall(sql, params=()):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [dict(r) for r in rows]


def get_applications_for_mobile(mobile: str) -> list[dict]:
    return fetchall(
        "SELECT id, application_no, applicant_name, status, submitted_at, decided_at, "
        "       block, village, bank_account, ifsc, "
        "       extract(day from (submitted_at + interval '15 days' - now()))::int AS days_remaining_in_sla "
        "FROM applications WHERE mobile = %s ORDER BY submitted_at DESC",
        (mobile,),
    )


def get_application_detail(app_id: int) -> dict | None:
    return fetchone(
        "SELECT id, application_no, applicant_name, mobile, dob, gender, "
        "       marital_status, village, block, bank_account, ifsc, status, doc_path, "
        "       submitted_at, decided_at, decided_by, "
        "       extract(day from (submitted_at + interval '15 days' - now()))::int AS days_remaining_in_sla "
        "FROM applications WHERE id = %s",
        (app_id,),
    )


def get_application_audit(app_id: int) -> list[dict]:
    return fetchall(
        "SELECT at, action, actor, note FROM audit_log "
        "WHERE application_id = %s ORDER BY at ASC",
        (app_id,),
    )


def get_active_application(mobile: str) -> dict | None:
    return fetchone(
        "SELECT id, application_no, status, submitted_at FROM applications "
        "WHERE mobile = %s AND status IN %s ORDER BY submitted_at DESC LIMIT 1",
        (mobile, ACTIVE_STATUSES),
    )


def search_by_mobile(mobile: str) -> list[dict]:
    return fetchall(
        "SELECT id, application_no, applicant_name, mobile, block, status, submitted_at "
        "FROM applications WHERE mobile = %s ORDER BY submitted_at DESC",
        (mobile,),
    )


def list_pending_for_block(block: str, page: int = 1, page_size: int = 20) -> list[dict]:
    """FIFO queue prioritized by days remaining before 15-day deemed approval."""
    offset = (page - 1) * page_size
    return fetchall(
        "SELECT id, application_no, applicant_name, mobile, village, block, submitted_at, "
        "       extract(day from (now() - submitted_at))::int AS days_elapsed, "
        "       extract(day from (submitted_at + interval '15 days' - now()))::int AS days_remaining_in_sla "
        "FROM applications "
        "WHERE status = 'PENDING' AND block = %s "
        "ORDER BY submitted_at ASC LIMIT %s OFFSET %s",
        (block, page_size, offset),
    )


def count_pending_for_block(block: str) -> dict:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT count(*) AS total_pending, "
        "       count(*) FILTER (WHERE submitted_at < now() - interval '15 days') AS overdue, "
        "       count(*) FILTER (WHERE submitted_at >= now() - interval '15 days' AND submitted_at < now() - interval '12 days') AS urgent "
        "FROM applications WHERE status = 'PENDING' AND block = %s",
        (block,)
    )
    res = dict(cur.fetchone())
    cur.close(); conn.close()
    return res


def dashboard_summary() -> dict:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT status, count(*) FROM applications GROUP BY status")
    by_status = {r["status"]: int(r["count"]) for r in cur.fetchall()}
    cur.execute(
        "SELECT count(*) AS n FROM applications WHERE status = 'PENDING' "
        "AND submitted_at < now() - interval '15 days'"
    )
    overdue = int(cur.fetchone()["n"])
    cur.execute(
        "SELECT block, count(*) AS n FROM applications WHERE status = 'PENDING' "
        "GROUP BY block ORDER BY n DESC"
    )
    by_block = {r["block"]: int(r["n"]) for r in cur.fetchall()}
    cur.close(); conn.close()
    return {"by_status": by_status, "overdue_pending": overdue, "pending_by_block": by_block}
