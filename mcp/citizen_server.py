# -*- coding: utf-8 -*-
"""
Sewa Setu — Citizen AI Assistant MCP Server

Streamable-HTTP MCP server for citizens applying for the Old Age Pension.
Bound at /mcp/citizen. Auth: citizen-scope OAuth 2.1 JWT from the portal.

Design rules (from the Director's brief):
  - Same validations as the portal counter — no shortcuts.
  - Mobile number comes from the JWT sub claim, never from tool arguments.
  - A citizen can only see and act on their own application.
  - The portal is the system of record; writes go through portal_client.py.
"""
import os
import sys
import json
from typing import Annotated
from datetime import datetime

# Ensure mcp/ directory is on the path
sys.path.insert(0, os.path.dirname(__file__))

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
import db
import portal_client as pc

MCP_URL = os.environ.get("CITIZEN_MCP_URL",
           os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
           + "/mcp/citizen")

BLOCKS = ["Sonari", "Rajapara", "Dhemaji Pathar", "Borgaon", "Namti", "Khelua"]
SCHEME_INFO = {
    "scheme_name": "Old Age Pension Scheme",
    "department": "Department of Social Welfare, Government of Purvanchal",
    "benefit": "Rs 250 per month",
    "eligibility": "Resident of Purvanchal aged 60 years or above",
    "blocks_covered": BLOCKS,
    "required_documents": [
        "Age proof: Aadhaar card, voter ID, birth certificate, or school leaving certificate",
        "A photo ID that shows date of birth",
    ],
    "bank_account_required": True,
    "sla_days": 15,
    "note": "If no officer decision is made within 15 days, the law automatically approves the application (deemed approval).",
}

mcp = FastMCP(
    "Sewa Setu Citizen Assistant",
    instructions=(
        "You are the official AI assistant for the Sewa Setu Old Age Pension portal, "
        "Government of Purvanchal. Help citizens check eligibility, apply for the pension, "
        "and track their application status. "
        "Always be polite and patient — applicants may be elderly or first-time users. "
        "Speak simply. Collect one piece of information at a time if the citizen seems confused. "
        "Never fabricate application numbers or status. "
        "The mobile number is already known from the citizen's login — do not ask for it."
    ),
)


def _mobile_from_ctx(ctx) -> str:
    """Extract mobile number from the MCP request context (JWT sub claim)."""
    # In FastMCP the auth claims are injected via lifespan or middleware.
    # We read them from the request state set by our auth middleware.
    claims = getattr(ctx, "_auth_claims", None)
    if claims:
        sub = claims.get("sub", "")
        if sub.startswith("citizen:"):
            return sub.split(":", 1)[1]
    # Fallback: read from env (for testing without full OAuth)
    return os.environ.get("TEST_CITIZEN_MOBILE", "")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def explain_scheme() -> dict:
    """
    Explain the Old Age Pension scheme: who is eligible, what they receive,
    which blocks are covered, and what documents are needed.
    Call this first when a citizen asks 'what is this scheme' or 'am I eligible'.
    """
    import configparser
    cfg = configparser.ConfigParser()
    for _p in ("/app/config/app.ini", os.path.join(os.path.dirname(__file__), "..", "app", "config", "app.ini"), "app/config/app.ini"):
        if os.path.exists(_p):
            cfg.read(_p)
            break
    try:
        deadline = cfg.get("pension", "scheme_deadline")
        now = datetime.now()
        deadline_dt = datetime.strptime(deadline, "%Y-%m-%d %H:%M")
        hours_left = int((deadline_dt - now).total_seconds() // 3600) if deadline_dt > now else 0
        window_open = deadline_dt > now
    except Exception:
        deadline = "Unknown"
        hours_left = None
        window_open = True
    info = dict(SCHEME_INFO)
    info["application_window_open"] = window_open
    info["scheme_deadline"] = deadline
    if hours_left is not None and window_open:
        info["hours_remaining"] = hours_left
    elif not window_open:
        info["window_closed_message"] = "The application window has closed. No new applications can be submitted."
    return info


@mcp.tool()
def check_eligibility(
    date_of_birth: Annotated[str, "Date of birth in DD/MM/YYYY format, e.g. 15/08/1954"],
    block: Annotated[str, "The block the applicant lives in"],
) -> dict:
    """
    Check if a person is eligible for the Old Age Pension.
    Use this before collecting all application details, to avoid wasting the citizen's time.
    Returns eligibility verdict, reason, and the list of valid blocks.
    """
    import configparser
    from datetime import datetime as dt

    result = {"eligible": False, "reasons": [], "valid_blocks": BLOCKS}

    # Age check
    try:
        dob = dt.strptime(date_of_birth.strip(), "%d/%m/%Y").date()
        today = dt.now().date()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        result["calculated_age"] = age
        if age < 60:
            result["reasons"].append(
                f"Applicant is {age} years old. The minimum age is 60 years."
            )
        else:
            result["age_ok"] = True
    except ValueError:
        result["reasons"].append("Date of birth format not recognised. Please use DD/MM/YYYY, e.g. 15/08/1954.")
        return result

    # Block check
    if block not in BLOCKS:
        result["reasons"].append(
            f"Block '{block}' is not in our list. Valid blocks are: {', '.join(BLOCKS)}."
        )
    else:
        result["block_ok"] = True

    cfg = configparser.ConfigParser()
    for _p in ("/app/config/app.ini", os.path.join(os.path.dirname(__file__), "..", "app", "config", "app.ini"), "app/config/app.ini"):
        if os.path.exists(_p):
            cfg.read(_p)
            break
    try:
        deadline = dt.strptime(cfg.get("pension", "scheme_deadline"), "%Y-%m-%d %H:%M")
        if dt.now() > deadline:
            result["reasons"].append("The application window for this scheme has closed.")
        else:
            result["window_open"] = True
    except Exception:
        result["window_open"] = True

    result["eligible"] = len(result["reasons"]) == 0
    if result["eligible"]:
        result["message"] = "This person appears eligible. You may proceed to collect application details."
    return result


@mcp.tool()
def get_application_status(ctx) -> dict:
    """
    Get the current application status for the signed-in citizen.
    Shows application number, status, submission date, and any decision.
    The citizen's identity comes from their login — do not ask for any ID.
    """
    mobile = _mobile_from_ctx(ctx)
    if not mobile:
        raise ToolError("Could not identify the citizen from the session. Please sign in again.")
    apps = db.get_applications_for_mobile(mobile)
    if not apps:
        return {
            "found": False,
            "message": "No application found for this mobile number. Would you like to apply?",
        }
    # Return most recent + summary of others
    latest = apps[0]
    # Format dates for readability
    for a in apps:
        for k in ("submitted_at", "decided_at"):
            if a.get(k):
                a[k] = str(a[k])
    return {
        "found": True,
        "latest_application": latest,
        "all_applications": apps,
        "total": len(apps),
    }


@mcp.tool()
def submit_application(
    ctx,
    applicant_name: Annotated[str, "Full name of the applicant as it should appear on records"],
    date_of_birth: Annotated[str, "Date of birth in DD/MM/YYYY format"],
    gender: Annotated[str, "Gender: Male, Female, or Other"],
    marital_status: Annotated[str, "Marital status: Single, Married, Widowed, or Divorced"],
    village: Annotated[str, "Village or locality name"],
    block: Annotated[str, "Block name — must be one of the valid blocks"],
    bank_account: Annotated[str, "Bank account number (9 to 18 digits)"],
    ifsc: Annotated[str, "IFSC code of the bank branch, e.g. SBIN0003077"],
    husband_name: Annotated[str, "Husband's name (required if married or widowed; leave blank otherwise)"] = "",
) -> dict:
    """
    Submit an Old Age Pension application for the signed-in citizen.

    IMPORTANT: Before calling this tool:
    1. Call check_eligibility first to confirm the person qualifies.
    2. Collect and confirm ALL required fields with the citizen.
    3. Confirm with the citizen that the details are correct before submitting.

    The mobile number comes from the citizen's login — do not ask for it.
    The age proof document must be uploaded separately at the portal URL returned.
    """
    mobile = _mobile_from_ctx(ctx)
    if not mobile:
        raise ToolError("Could not identify the citizen from the session. Please sign in again.")

    data = {
        "applicant_name": applicant_name,
        "dob": date_of_birth,
        "gender": gender,
        "marital_status": marital_status,
        "village": village,
        "block": block,
        "bank_account": bank_account,
        "ifsc": ifsc,
        "husband_name": husband_name,
    }
    result = pc.citizen_submit(mobile, data)
    if result["success"]:
        portal_url = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
        result["next_step"] = (
            f"Application {result['app_no']} submitted successfully! "
            f"An SMS has been sent to your mobile. "
            f"To complete the application, please upload your age proof document at: "
            f"{portal_url}/upload\n"
            f"You can track your application at: {portal_url}/status\n"
            f"Your status portal password is your date of birth as DDMMYYYY."
        )
    return result


@mcp.tool()
def withdraw_application(
    ctx,
    application_id: Annotated[int, "The numeric application ID (not the application number string)"],
    confirm: Annotated[bool, "Must be true to confirm withdrawal. Ask the citizen to confirm before calling."],
) -> dict:
    """
    Withdraw a PENDING application so the citizen can apply afresh.
    Only PENDING applications can be withdrawn.
    The citizen can only withdraw their own application.
    Always confirm with the citizen before calling this tool.
    """
    if not confirm:
        return {"success": False, "reason": "Withdrawal not confirmed. Please confirm with the citizen first."}
    mobile = _mobile_from_ctx(ctx)
    if not mobile:
        raise ToolError("Could not identify the citizen. Please sign in again.")
    return pc.citizen_withdraw(application_id, mobile)


@mcp.tool()
def list_required_documents() -> dict:
    """
    List the documents required to complete an Old Age Pension application.
    Call this when a citizen asks 'what do I need to bring' or 'what documents are required'.
    """
    return {
        "age_proof_options": [
            "Aadhaar card (showing date of birth)",
            "Voter ID card",
            "Birth certificate",
            "School leaving certificate",
            "PAN card",
            "Passport",
        ],
        "bank_details_needed": [
            "Bank account number (the account must be in the applicant's name)",
            "IFSC code of the bank branch",
        ],
        "note": (
            "One of the above age proof documents must be uploaded as a JPG, PNG or PDF file "
            "(maximum 5 MB) to complete the application. "
            "The AI assistant will collect your details and create the application; "
            "the document upload is done on the portal website."
        ),
    }


@mcp.tool()
def get_acknowledgment_url(ctx) -> dict:
    """
    Get the URL to download the PDF acknowledgment for the citizen's latest application.
    """
    mobile = _mobile_from_ctx(ctx)
    if not mobile:
        raise ToolError("Could not identify the citizen. Please sign in again.")
    apps = db.get_applications_for_mobile(mobile)
    if not apps:
        return {"found": False, "message": "No application found."}
    latest = apps[0]
    portal_url = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    return {
        "found": True,
        "application_no": latest["application_no"],
        "status": latest["status"],
        "acknowledgment_url": f"{portal_url}/ack/{latest['id']}.pdf",
        "status_portal_url": f"{portal_url}/status",
    }


@mcp.tool()
def explain_status(status_code: Annotated[str, "Status code from the application (e.g. PENDING, APPROVED, REJECTED, DEEMED_APPROVED, WITHDRAWN)"]) -> dict:
    """
    Explain what a status code means in plain language.
    Call this after showing the citizen their application status.
    """
    explanations = {
        "PENDING": (
            "Your application is under review by the block officer. "
            "A decision will be made within 15 days. If no decision is made, "
            "the law automatically approves your application."
        ),
        "APPROVED": (
            "Congratulations! Your application has been approved by the block officer. "
            "Your pension disbursement will begin shortly. The amount will be credited "
            "to your registered bank account."
        ),
        "DEEMED_APPROVED": (
            "Your application has been automatically approved under the Right to Public Services Act "
            "because no decision was made within 15 days. "
            "Your pension disbursement will begin shortly."
        ),
        "REJECTED": (
            "Your application has been rejected. You may apply again if you believe "
            "there was an error. Please visit the portal or the counter for more details."
        ),
        "WITHDRAWN": (
            "This application was withdrawn. You may submit a fresh application "
            "if you wish to apply again."
        ),
    }
    code = status_code.upper().strip()
    return {
        "status": code,
        "explanation": explanations.get(code, f"Unknown status '{code}'. Please contact the office."),
    }


# ---------------------------------------------------------------------------
# Auth middleware: inject claims into context
# ---------------------------------------------------------------------------

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse
import auth as auth_mod


class CitizenAuthMiddleware(BaseHTTPMiddleware):
    """Verify Bearer token and attach claims to request.state."""

    async def dispatch(self, request: StarletteRequest, call_next):
        # Allow OPTIONS and health checks through
        if request.method == "OPTIONS" or request.url.path in ("/health", "/"):
            return await call_next(request)
        authz = request.headers.get("Authorization", "")
        if not authz.startswith("Bearer "):
            return JSONResponse(
                {"error": "Authorization header with Bearer token required."},
                status_code=401,
            )
        token = authz[7:]
        try:
            claims = auth_mod._decode(token, MCP_URL)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=401)
        if claims.get("scope") != "citizen":
            return JSONResponse(
                {"error": "This endpoint requires a citizen-scope token."},
                status_code=403,
            )
        request.state.auth_claims = claims
        return await call_next(request)


# Patch FastMCP context to carry auth claims
original_get_context = mcp._get_context if hasattr(mcp, '_get_context') else None


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    # Get the underlying Starlette app and add middleware
    starlette_app = mcp.streamable_http_app()
    starlette_app.add_middleware(CitizenAuthMiddleware)

    port = int(os.environ.get("CITIZEN_MCP_PORT", "8001"))
    print(f"Citizen MCP server starting on port {port}")
    print(f"MCP URL: {MCP_URL}")
    uvicorn.run(starlette_app, host="0.0.0.0", port=port)
