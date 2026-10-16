# -*- coding: utf-8 -*-
"""
Sewa Setu Core Shared Rules & Validation Engine.

Single source of truth used across:
1. Flask Web Portal (app/app.py)
2. Citizen MCP Server (mcp/citizen_server.py)
3. Officer MCP Server (mcp/officer_server.py)
4. Automated Evaluation Suites (evals/)

Prevents code drift and guarantees 100% parity between web, counter, and agent channels.
"""

import os
import re
import configparser
from datetime import datetime, date
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def now_ist() -> datetime:
    """Official Indian Standard Time anchor."""
    return datetime.now(IST).replace(tzinfo=None)


def find_config_path() -> str:
    candidates = [
        "/app/config/app.ini",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "app.ini"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "config", "app.ini"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]


config = configparser.ConfigParser()
config_file = find_config_path()
if os.path.exists(config_file):
    config.read(config_file)

MIN_AGE = config.getint("pension", "min_age", fallback=60)
SLA_DAYS = config.getint("pension", "sla_days", fallback=15)
SCHEME_DEADLINE_RAW = config.get("pension", "scheme_deadline", fallback="2026-10-31 23:59")
try:
    SCHEME_DEADLINE = datetime.strptime(SCHEME_DEADLINE_RAW, "%Y-%m-%d %H:%M")
except Exception:
    SCHEME_DEADLINE = datetime(2026, 10, 31, 23, 59)

# Standard statutory blocks
STATUTORY_BLOCKS = ["Sonari", "Rajapara", "Dhemaji Pathar", "Borgaon", "Namti", "Khelua"]

# Configurable Pilot Blocks for AI Agent Access
_pilot_env = os.environ.get("MCP_ALLOWED_BLOCKS")
if _pilot_env:
    PILOT_BLOCKS = [b.strip() for b in _pilot_env.split(",") if b.strip()]
else:
    PILOT_BLOCKS = STATUTORY_BLOCKS.copy()

ACTIVE_STATUSES = ("PENDING", "APPROVED", "DEEMED_APPROVED")


def sanitize(value, maxlen=100) -> str:
    """Trim whitespace and cap characters intact (Assamese/Bangla support)."""
    if value is None:
        return ""
    return str(value).strip()[:maxlen]


def parse_dob(raw: str) -> date | None:
    """Parse DD/MM/YYYY string to date."""
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw).strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def calculate_age(dob: date, on: date | None = None) -> int:
    if on is None:
        on = now_ist().date()
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def validate_application_data(data: dict, doc_path: str = "") -> tuple[list[dict], dict]:
    """
    Validate application against official rules.
    Returns:
      (errors, cleaned)
      where errors is a list of structured dicts:
      {"field": str, "code": str, "message": str, "remediation": str}
    """
    errors = []
    cleaned = {
        "applicant_name": sanitize(data.get("applicant_name")),
        "village": (data.get("village") or "").strip(),
        "block": (data.get("block") or "").strip(),
        "gender": (data.get("gender") or "").strip(),
        "marital_status": (data.get("marital_status") or "").strip(),
        "husband_name": (data.get("husband_name") or "").strip(),
        "husband_employer": "",
        "bank_account": re.sub(r"[\s-]", "", data.get("bank_account") or ""),
        "ifsc": re.sub(r"[\s-]", "", (data.get("ifsc") or "")).upper(),
        "doc_path": doc_path or (data.get("doc_path") or "").strip(),
        "dob": None,
        "calculated_age": None,
        "helper_info": data.get("helper_info") or None,
    }

    # Required field checks
    if not cleaned["applicant_name"]:
        errors.append({
            "field": "applicant_name",
            "code": "MISSING_REQUIRED_FIELD",
            "message": "Full name of the applicant is required.",
            "remediation": "Please provide the legal name of the applicant as shown on their ID."
        })
    if not cleaned["village"]:
        errors.append({
            "field": "village",
            "code": "MISSING_REQUIRED_FIELD",
            "message": "Village/locality name is required.",
            "remediation": "Please state the village or neighborhood where the applicant resides."
        })
    if not cleaned["block"]:
        errors.append({
            "field": "block",
            "code": "MISSING_REQUIRED_FIELD",
            "message": "Administrative block is required.",
            "remediation": f"Block must be one of: {', '.join(STATUTORY_BLOCKS)}."
        })
    elif cleaned["block"] not in STATUTORY_BLOCKS:
        errors.append({
            "field": "block",
            "code": "INVALID_BLOCK",
            "message": f"Block '{cleaned['block']}' is not a valid administrative block in Purvanchal.",
            "remediation": f"Valid blocks are: {', '.join(STATUTORY_BLOCKS)}."
        })
    elif cleaned["block"] not in PILOT_BLOCKS:
        errors.append({
            "field": "block",
            "code": "OUT_OF_PILOT_SCOPE",
            "message": f"Block '{cleaned['block']}' is currently not served by the AI Agent channel.",
            "remediation": f"The AI Assistant is currently active only for: {', '.join(PILOT_BLOCKS)}. For other blocks, please apply at the physical counter or portal directly."
        })

    # Bank account regex (9 to 18 digits)
    if not cleaned["bank_account"]:
        errors.append({
            "field": "bank_account",
            "code": "MISSING_REQUIRED_FIELD",
            "message": "Bank account number is required.",
            "remediation": "Provide an active savings bank account number in the applicant's name."
        })
    elif not re.fullmatch(r"\d{9,18}", cleaned["bank_account"]):
        errors.append({
            "field": "bank_account",
            "code": "INVALID_BANK_ACCOUNT",
            "message": "Bank account number must be between 9 and 18 digits.",
            "remediation": "Check the passbook and enter only the numbers without hyphens or spaces."
        })

    # IFSC Code (11 characters: 4 letters, 0, 6 alphanumeric)
    if not cleaned["ifsc"]:
        errors.append({
            "field": "ifsc",
            "code": "MISSING_REQUIRED_FIELD",
            "message": "Bank IFSC code is required.",
            "remediation": "Provide the 11-character IFSC code printed on the bank passbook (e.g. SBIN0003077)."
        })
    elif not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", cleaned["ifsc"]):
        errors.append({
            "field": "ifsc",
            "code": "INVALID_IFSC",
            "message": "IFSC must be 11 characters (e.g. SBIN0003077).",
            "remediation": "Ensure the 5th character is zero and the first 4 characters are letters."
        })

    # Date of Birth and Age criteria
    dob = parse_dob(data.get("dob"))
    if dob is None:
        errors.append({
            "field": "dob",
            "code": "INVALID_DOB_FORMAT",
            "message": "Date of birth must be provided in DD/MM/YYYY format.",
            "remediation": "Example: 15/08/1954."
        })
    else:
        cleaned["dob"] = dob
        age = calculate_age(dob)
        cleaned["calculated_age"] = age
        if age < MIN_AGE:
            errors.append({
                "field": "dob",
                "code": "UNDERAGE",
                "message": f"Applicant is {age} years old. The scheme statutory requirement is {MIN_AGE} years or above.",
                "remediation": f"The applicant will become eligible on their 60th birthday ({dob.replace(year=dob.year + 60).strftime('%d/%m/%Y')})."
            })

    # Age proof document
    if not cleaned["doc_path"]:
        errors.append({
            "field": "doc_path",
            "code": "MISSING_AGE_PROOF",
            "message": "Age proof document reference is required.",
            "remediation": "Attach an uploaded age proof document token or file reference."
        })

    # Scheme deadline
    if now_ist() > SCHEME_DEADLINE:
        errors.append({
            "field": "scheme_deadline",
            "code": "WINDOW_CLOSED",
            "message": "The application window for this pension cycle has closed.",
            "remediation": "Please contact the Department of Social Welfare for subsequent scheme cycles."
        })

    return errors, cleaned


def mask_sensitive_string(val: str, visible_end: int = 4) -> str:
    """Mask PII fields such as bank accounts and phone numbers."""
    if not val:
        return ""
    val_str = str(val).strip()
    if len(val_str) <= visible_end:
        return "*" * len(val_str)
    return "*" * (len(val_str) - visible_end) + val_str[-visible_end:]

