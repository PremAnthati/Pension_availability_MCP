# -*- coding: utf-8 -*-
"""
Seed the database with pre-conditions needed for eval personas P3 and P6.

P3 (Sunita Bai, mobile 9800000003): needs an existing APPROVED application.
P6 (Gopal Singh, mobile 9800000006): needs an existing PENDING application with wrong bank account.

Run this once before running evals:
  python seed_eval_data.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)) + "/mcp")

from datetime import datetime, timedelta
import hashlib
import db


def seed():
    conn = db.get_db()
    cur = conn.cursor()

    # Clean up any previous eval runs
    eval_mobiles = (
        "9800000001", "9800000002", "9800000003",
        "9800000004", "9800000005", "9800000006",
    )
    print("Cleaning up previous eval data...")
    for mobile in eval_mobiles:
        cur.execute(
            "DELETE FROM audit_log WHERE application_id IN "
            "(SELECT id FROM applications WHERE mobile = %s)", (mobile,)
        )
        cur.execute("DELETE FROM applications WHERE mobile = %s", (mobile,))
        cur.execute("DELETE FROM portal_users WHERE mobile = %s", (mobile,))

    # P3: Sunita Bai — pre-existing APPROVED application
    print("Seeding P3 (Sunita Bai) — existing APPROVED application...")
    cur.execute(
        "INSERT INTO applications "
        "(application_no, applicant_name, mobile, dob, gender, marital_status, "
        " husband_name, husband_employer, village, block, bank_account, ifsc, "
        " doc_path, status, submitted_at, decided_at, decided_by) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'APPROVED',%s,%s,%s) RETURNING id",
        ("SSP24-EVAL-P3", "Sunita Bai", "9800000003",
         "1954-06-03", "Female", "Widowed", "Mohan Lal", "",
         "Dhemaji", "Dhemaji Pathar", "111222333444", "UBIN0567890",
         "eval/placeholder.pdf",
         datetime.now() - timedelta(days=20),
         datetime.now() - timedelta(days=10),
         "admin")
    )
    p3_id = cur.fetchone()["id"]
    cur.execute(
        "INSERT INTO portal_users (mobile, password_hash) VALUES (%s, %s)",
        ("9800000003", hashlib.sha256("03061954".encode()).hexdigest())
    )
    cur.execute(
        "INSERT INTO audit_log (application_id, action, actor, note, at) VALUES (%s, 'SUBMIT', 'applicant:9800000003', 'eval seed', %s)",
        (p3_id, datetime.now() - timedelta(days=20))
    )
    cur.execute(
        "INSERT INTO audit_log (application_id, action, actor, note, at) VALUES (%s, 'APPROVED', 'admin', 'Verified by officer', %s)",
        (p3_id, datetime.now() - timedelta(days=10))
    )

    # P6: Gopal Singh — pre-existing PENDING application with wrong bank account
    print("Seeding P6 (Gopal Singh) — existing PENDING application with wrong bank...")
    cur.execute(
        "INSERT INTO applications "
        "(application_no, applicant_name, mobile, dob, gender, marital_status, "
        " husband_name, husband_employer, village, block, bank_account, ifsc, "
        " doc_path, status, submitted_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PENDING',%s) RETURNING id",
        ("SSP24-EVAL-P6", "Gopal Singh", "9800000006",
         "1956-09-30", "Male", "Married", "", "",
         "Namti Bazar", "Namti", "999888777666", "HDFC0009999",  # wrong bank
         "eval/placeholder.pdf",
         datetime.now() - timedelta(days=5))
    )
    p6_id = cur.fetchone()["id"]
    cur.execute(
        "INSERT INTO portal_users (mobile, password_hash) VALUES (%s, %s)",
        ("9800000006", hashlib.sha256("30091956".encode()).hexdigest())
    )
    cur.execute(
        "INSERT INTO audit_log (application_id, action, actor, note, at) VALUES (%s, 'SUBMIT', 'applicant:9800000006', 'eval seed — wrong bank', %s)",
        (p6_id, datetime.now() - timedelta(days=5))
    )

    conn.commit()
    cur.close(); conn.close()
    print("Eval data seeded successfully.")
    print(f"  P3 app_id: {p3_id}")
    print(f"  P6 app_id: {p6_id}")
    return {"p3_app_id": p3_id, "p6_app_id": p6_id}


if __name__ == "__main__":
    seed()
