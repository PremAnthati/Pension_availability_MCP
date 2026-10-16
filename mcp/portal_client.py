# -*- coding: utf-8 -*-
"""
Write operations and transaction execution for Sewa Setu MCP servers.
Guarantees identical behavior with app/app.py while emitting structured responses.
"""
import os
import sys
import hashlib
import random
import json
import requests as req
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
import core_rules
import db

PORTAL_URL = os.environ.get("PORTAL_URL", "http://app:8000")


def read_sms_inbox(mobile: str) -> list[dict]:
    """Read simulated SMS inbox."""
    try:
        r = req.get(f"{PORTAL_URL}/__gateway/api/messages", params={"to": mobile}, timeout=5)
        return r.json().get("messages", [])
    except Exception:
        return []


def dry_run_validate(data: dict, doc_path: str = "") -> dict:
    """
    Dry run validation of an application without persisting it.
    Returns preview with masked sensitive fields if valid.
    """
    errors, cleaned = core_rules.validate_application_data(data, doc_path)
    if errors:
        return {
            "is_valid": False,
            "errors": errors,
            "message": "Application has validation errors that must be resolved before submission."
        }

    return {
        "is_valid": True,
        "message": "All fields are valid. Please confirm with the citizen before submitting.",
        "confirmation_preview": {
            "applicant_name": cleaned["applicant_name"],
            "age": cleaned["calculated_age"],
            "date_of_birth": cleaned["dob"].strftime("%d/%m/%Y"),
            "gender": cleaned["gender"],
            "village": cleaned["village"],
            "block": cleaned["block"],
            "bank_account_masked": core_rules.mask_sensitive_string(cleaned["bank_account"]),
            "ifsc": cleaned["ifsc"],
            "helper_represented": bool(cleaned["helper_info"]),
        }
    }


def citizen_submit_application(mobile: str, data: dict, doc_placeholder: str = "ATTACHED_AGE_PROOF", helper_info: dict | None = None) -> dict:
    """
    Submit an application following the portal's create_application() transaction.
    """
    # 1. Run core validation
    errors, cleaned = core_rules.validate_application_data(data, doc_placeholder)
    if errors:
        return {
            "success": False,
            "error_code": "VALIDATION_FAILED",
            "errors": errors,
            "message": "Application does not satisfy scheme criteria."
        }

    # 2. Check for duplicate active application
    existing = db.get_active_application(mobile)
    if existing:
        return {
            "success": False,
            "error_code": "DUPLICATE_ACTIVE_APPLICATION",
            "message": f"An active application {existing['application_no']} in status '{existing['status']}' already exists for this mobile number.",
            "existing_application": {
                "application_no": existing["application_no"],
                "status": existing["status"],
                "submitted_at": str(existing["submitted_at"])
            },
            "remediation": "If you wish to apply with different details, withdraw the pending application first."
        }

    # 3. Create record in DB
    app_no = "SSP" + datetime.now().strftime("%y") + str(random.randint(100000, 999999))
    portal_pass = cleaned["dob"].strftime("%d%m%Y")
    actor_str = f"applicant:{mobile}"
    helper_note = ""
    if helper_info and helper_info.get("helper_name"):
        helper_note = f" (Applied by helper: {helper_info.get('helper_name')} - {helper_info.get('relationship', 'Relation')})"

    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO applications
           (application_no, applicant_name, mobile, dob, gender, marital_status,
            husband_name, husband_employer, village, block, bank_account, ifsc,
            doc_path, status, submitted_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PENDING',%s)
           RETURNING id""",
        (app_no, cleaned["applicant_name"], mobile, cleaned["dob"],
         cleaned["gender"], cleaned["marital_status"], cleaned["husband_name"],
         cleaned["husband_employer"], cleaned["village"], cleaned["block"],
         cleaned["bank_account"], cleaned["ifsc"], cleaned["doc_path"], datetime.now())
    )
    new_id = cur.fetchone()["id"]

    # Ensure status portal user
    cur.execute("SELECT count(*) AS n FROM portal_users WHERE mobile = %s", (mobile,))
    if cur.fetchone()["n"] == 0:
        cur.execute(
            "INSERT INTO portal_users (mobile, password_hash) VALUES (%s, %s)",
            (mobile, hashlib.sha256(portal_pass.encode()).hexdigest())
        )

    # Audit log
    cur.execute(
        "INSERT INTO audit_log (application_id, action, actor, note, at) "
        "VALUES (%s, 'SUBMIT', %s, %s, %s)",
        (new_id, actor_str, f"Submitted via AI Assistant{helper_note}", datetime.now())
    )
    conn.commit()
    cur.close(); conn.close()

    # Send notification via SMS gateway
    try:
        req.post(
            f"{PORTAL_URL}/api/send".replace("8000/api", "8025/api"),
            json={"to": mobile,
                  "text": f"Sewa Setu: application {app_no} received. Track at status portal with mobile and password (DOB as DDMMYYYY)."},
            timeout=3
        )
    except Exception:
        pass

    return {
        "success": True,
        "application_no": app_no,
        "application_id": new_id,
        "applicant_name": cleaned["applicant_name"],
        "status": "PENDING",
        "sla_days": core_rules.SLA_DAYS,
        "message": f"Application {app_no} has been successfully recorded in the portal."
    }


def citizen_withdraw_application(app_id: int, mobile: str, reason: str = "") -> dict:
    """Applicant withdraws their own pending application."""
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
            "VALUES (%s, 'WITHDRAW', %s, %s, %s)",
            (app_id, f"applicant:{mobile}", f"Withdrawn via AI Assistant. Reason: {reason or 'Applicant requested'}", datetime.now())
        )
        conn.commit()
        cur.close(); conn.close()
        return {
            "success": True,
            "application_no": row["application_no"],
            "status": "WITHDRAWN",
            "message": f"Application {row['application_no']} was successfully withdrawn. You may now apply afresh."
        }

    cur.close(); conn.close()
    return {
        "success": False,
        "error_code": "CANNOT_WITHDRAW",
        "message": "Only an existing PENDING application registered to your mobile number can be withdrawn."
    }


def officer_decide_case(app_id: int, decision: str, reason: str, officer_username: str, officer_block: str) -> dict:
    """
    Officer records an approve or reject decision.
    Enforces:
    1. Decision must be 'APPROVED' or 'REJECTED'
    2. Meaningful, non-empty reason
    3. Application must be currently PENDING
    4. Application must belong to the officer's authorized block
    """
    decision = decision.upper().strip()
    if decision not in ("APPROVED", "REJECTED"):
        return {"success": False, "error_code": "INVALID_DECISION", "message": "Decision must be APPROVED or REJECTED."}

    reason_clean = (reason or "").strip()
    if len(reason_clean) < 8 or reason_clean.lower() in ("ok", "approved", "done", "yes", "reject"):
        return {
            "success": False,
            "error_code": "INSUFFICIENT_REASON",
            "message": "A detailed, meaningful reason must be recorded (minimum 8 characters; no generic boilerplate)."
        }

    app = db.get_application_detail(app_id)
    if not app:
        return {"success": False, "error_code": "NOT_FOUND", "message": f"Application ID {app_id} does not exist."}

    # Verify block scope
    if officer_block and app["block"] != officer_block:
        return {
            "success": False,
            "error_code": "FORBIDDEN_BLOCK_SCOPE",
            "message": f"Officer authorization violation: Case belongs to '{app['block']}', but you are authorized only for '{officer_block}'."
        }

    if app["status"] != "PENDING":
        return {
            "success": False,
            "error_code": "NOT_PENDING",
            "message": f"Cannot decide case: Application {app['application_no']} is already in status '{app['status']}'."
        }

    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE applications SET status = %s, decided_at = %s, decided_by = %s "
        "WHERE id = %s AND status = 'PENDING' RETURNING application_no",
        (decision, datetime.now(), officer_username, app_id)
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            "INSERT INTO audit_log (application_id, action, actor, note, at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (app_id, decision, f"officer:{officer_username}", reason_clean, datetime.now())
        )
        conn.commit()
        cur.close(); conn.close()
        return {
            "success": True,
            "application_no": row["application_no"],
            "new_status": decision,
            "decided_by": officer_username,
            "reason_recorded": reason_clean,
            "message": f"Application {row['application_no']} has been successfully marked as {decision}."
        }

    cur.close(); conn.close()
    return {"success": False, "error_code": "DECISION_FAILED", "message": "Failed to update application state."}
