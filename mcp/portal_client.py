# -*- coding: utf-8 -*-
"""
Write operations for the MCP servers. All mutations go through this module
so the portal's audit_log and validate_application() are always exercised.
"""
import os
import re
import hashlib
import random
import requests as req
from datetime import datetime

PORTAL_URL = os.environ.get("PORTAL_URL", "http://app:8000")

BLOCKS = ["Sonari", "Rajapara", "Dhemaji Pathar", "Borgaon", "Namti", "Khelua"]

# ── Blocks available to AI assistants (subset as the Director requested) ────
MCP_ALLOWED_BLOCKS = os.environ.get(
    "MCP_ALLOWED_BLOCKS",
    "Sonari,Rajapara,Dhemaji Pathar,Borgaon,Namti,Khelua"
).split(",")


def read_sms_inbox(mobile: str) -> list:
    """Read the simulated SMS gateway inbox for this mobile number."""
    try:
        r = req.get(
            f"{PORTAL_URL}/__gateway/api/messages",
            params={"to": mobile}, timeout=10
        )
        return r.json().get("messages", [])
    except Exception:
        return []


# ── Shared DB helpers (imported here to keep writes in one place) ────────────

def _db_write(sql, params, returning=False):
    import db
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(sql, params)
    row = cur.fetchone() if returning else None
    conn.commit()
    cur.close(); conn.close()
    return dict(row) if row else None


# ── Citizen: submit application ──────────────────────────────────────────────

def citizen_submit(mobile: str, data: dict, doc_placeholder: str = "PENDING_UPLOAD") -> dict:
    """
    Validate and submit an application, mirroring validate_application() and
    create_application() from app.py exactly.

    doc_placeholder is used when the AI assistant has collected all data
    but the physical document upload happens separately on the portal.
    Returns {success, app_no, app_id, errors}.
    """
    import db

    # ── Block restriction ──────────────────────────────────────────────────
    block = (data.get("block") or "").strip()
    if block not in MCP_ALLOWED_BLOCKS:
        return {
            "success": False,
            "errors": [f"Block '{block}' is not currently served by the AI assistant. "
                       f"Available blocks: {', '.join(MCP_ALLOWED_BLOCKS)}. "
                       "Please visit the counter or portal directly."]
        }

    # ── Replicate portal validation ────────────────────────────────────────
    errors = []
    cleaned = {
        "applicant_name": (data.get("applicant_name") or "").strip()[:100],
        "village":        (data.get("village") or "").strip(),
        "block":          block,
        "gender":         data.get("gender") or "",
        "marital_status": data.get("marital_status") or "",
        "husband_name":   (data.get("husband_name") or "").strip(),
        "husband_employer": "",
        "bank_account":   re.sub(r"[\s-]", "", data.get("bank_account") or ""),
        "ifsc":           re.sub(r"[\s-]", "", (data.get("ifsc") or "")).upper(),
        "doc_path":       doc_placeholder,
        "dob":            None,
    }
    for label, key in (("full name", "applicant_name"), ("village", "village"),
                       ("block", "block"), ("bank account", "bank_account")):
        if not cleaned[key]:
            errors.append(f"{label} is required")
    if cleaned["block"] and cleaned["block"] not in BLOCKS:
        errors.append("block must be one of: " + ", ".join(BLOCKS))
    if cleaned["bank_account"] and not re.fullmatch(r"\d{9,18}", cleaned["bank_account"]):
        errors.append("bank account number must be 9 to 18 digits")
    if cleaned["ifsc"] and not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", cleaned["ifsc"]):
        errors.append("IFSC must be 11 characters, e.g. SBIN0003077")

    dob_raw = data.get("dob", "")
    dob = None
    try:
        dob = datetime.strptime((dob_raw or "").strip(), "%d/%m/%Y").date()
    except ValueError:
        errors.append("date of birth must be in DD/MM/YYYY format, e.g. 15/08/1954")
    if dob:
        today = datetime.now().date()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if age < 60:
            errors.append(f"Applicant must be 60 years or above (calculated age: {age} years).")
        cleaned["dob"] = dob

    # Scheme deadline
    from datetime import datetime as dt
    import configparser, os as _os
    _cfg = configparser.ConfigParser()
    for _p in ("/app/config/app.ini", _os.path.join(_os.path.dirname(__file__), "..", "app", "config", "app.ini"), "app/config/app.ini"):
        if _os.path.exists(_p):
            _cfg.read(_p)
            break
    try:
        deadline = dt.strptime(_cfg.get("pension", "scheme_deadline"), "%Y-%m-%d %H:%M")
        if dt.now() > deadline:
            errors.append("The application window for this scheme has closed.")
    except Exception:
        pass

    if errors:
        return {"success": False, "errors": errors}

    # ── Check for existing active application ──────────────────────────────
    existing = db.get_active_application(mobile)
    if existing:
        return {
            "success": False,
            "errors": [f"An active application {existing['application_no']} ({existing['status']}) "
                       f"already exists for this mobile number. A pending application can be "
                       f"withdrawn if you need to apply afresh."]
        }

    # ── Insert ─────────────────────────────────────────────────────────────
    app_no = "SSP" + datetime.now().strftime("%y") + str(random.randint(100000, 999999))
    portal_pass = cleaned["dob"].strftime("%d%m%Y")
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO applications "
        "(application_no, applicant_name, mobile, dob, gender, marital_status, "
        " husband_name, husband_employer, village, block, bank_account, ifsc, "
        " doc_path, status, submitted_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PENDING',%s) RETURNING id",
        (app_no, cleaned["applicant_name"], mobile, cleaned["dob"],
         cleaned["gender"], cleaned["marital_status"], cleaned["husband_name"],
         cleaned["husband_employer"], cleaned["village"], cleaned["block"],
         cleaned["bank_account"], cleaned["ifsc"], cleaned["doc_path"], datetime.now())
    )
    new_id = cur.fetchone()["id"]
    cur.execute("SELECT count(*) AS n FROM portal_users WHERE mobile = %s", (mobile,))
    if cur.fetchone()["n"] == 0:
        cur.execute(
            "INSERT INTO portal_users (mobile, password_hash) VALUES (%s, %s)",
            (mobile, hashlib.sha256(portal_pass.encode()).hexdigest())
        )
    cur.execute(
        "INSERT INTO audit_log (application_id, action, actor, note, at) "
        "VALUES (%s, 'SUBMIT', %s, 'Submitted via AI assistant', %s)",
        (new_id, f"applicant:{mobile}", datetime.now())
    )
    conn.commit()
    cur.close(); conn.close()

    # Notify citizen
    try:
        req.post(
            f"{PORTAL_URL.rstrip('/')}/__gateway/../api/send".replace("/__gateway/../", "/"),
            json={"to": mobile,
                  "text": f"Sewa Setu: application {app_no} received. Track at status portal "
                          f"with your mobile and password (DOB as DDMMYYYY)."}, timeout=5
        )
    except Exception:
        pass

    return {"success": True, "app_no": app_no, "app_id": new_id}


def citizen_withdraw(app_id: int, mobile: str) -> dict:
    import db
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE applications SET status = 'WITHDRAWN', decided_at = %s, decided_by = 'APPLICANT' "
        "WHERE id = %s AND mobile = %s AND status = 'PENDING' RETURNING application_no",
        (datetime.now(), app_id, mobile)
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            "INSERT INTO audit_log (application_id, action, actor, note, at) "
            "VALUES (%s, 'WITHDRAW', %s, 'Withdrawn via AI assistant', %s)",
            (app_id, f"applicant:{mobile}", datetime.now())
        )
        conn.commit()
        cur.close(); conn.close()
        return {"success": True, "application_no": row["application_no"]}
    cur.close(); conn.close()
    return {"success": False,
            "reason": "Only a pending application can be withdrawn, and it must belong to your mobile number."}


def officer_approve(app_id: int, note: str, actor: str = "mcp-officer") -> dict:
    import db
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE applications SET status = 'APPROVED', decided_at = %s, decided_by = %s "
        "WHERE id = %s AND status = 'PENDING' RETURNING application_no",
        (datetime.now(), actor, app_id)
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            "INSERT INTO audit_log (application_id, action, actor, note, at) "
            "VALUES (%s, 'APPROVED', %s, %s, %s)",
            (app_id, f"officer:{actor}", note, datetime.now())
        )
        conn.commit()
        cur.close(); conn.close()
        return {"success": True, "application_no": row["application_no"], "new_status": "APPROVED"}
    cur.close(); conn.close()
    return {"success": False, "reason": "Application not found or not in PENDING status."}


def officer_reject(app_id: int, note: str, actor: str = "mcp-officer") -> dict:
    import db
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE applications SET status = 'REJECTED', decided_at = %s, decided_by = %s "
        "WHERE id = %s AND status = 'PENDING' RETURNING application_no",
        (datetime.now(), actor, app_id)
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            "INSERT INTO audit_log (application_id, action, actor, note, at) "
            "VALUES (%s, 'REJECTED', %s, %s, %s)",
            (app_id, f"officer:{actor}", note, datetime.now())
        )
        conn.commit()
        cur.close(); conn.close()
        return {"success": True, "application_no": row["application_no"], "new_status": "REJECTED"}
    cur.close(); conn.close()
    return {"success": False, "reason": "Application not found or not in PENDING status."}
