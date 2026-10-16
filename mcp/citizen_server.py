# -*- coding: utf-8 -*-
"""
Sewa Setu — Citizen AI Assistant MCP Server.
Compliant with Model Context Protocol (MCP) streamable HTTP transport.

Endpoints:
- GET /mcp/citizen or POST /mcp/citizen
- Tools provided:
  1. get_scheme_info
  2. check_eligibility (non-binding pre-screen)
  3. validate_application (dry-run with remediation hints)
  4. submit_application (requires explicit confirmation flag)
  5. get_application_status (authenticated via sub claim)
  6. withdraw_application (requires explicit confirmation)
  7. list_required_documents
  8. get_acknowledgment_url
"""
import os
import sys
from typing import Annotated

# Ensure paths
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
import core_rules
import db
import portal_client as pc

MCP_URL = os.environ.get(
    "CITIZEN_MCP_URL",
    os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/") + "/mcp/citizen"
)

mcp = FastMCP(
    "Sewa Setu Citizen Assistant",
    instructions=(
        "You are the official AI assistant for the Sewa Setu Old Age Pension portal (Government of Purvanchal). "
        "Your purpose is to help seniors, family members, and kiosk operators learn about the pension, "
        "check eligibility, validate details, submit applications, and track decisions. "
        "CRITICAL RULES: "
        "1. Never guess or hallucinate scheme rules; always invoke get_scheme_info or check_eligibility. "
        "2. Applicants are elderly. Speak gently, in plain language, one step at a time. "
        "3. Never ask the citizen for their mobile number; it is already verified from their authenticated session. "
        "4. Always perform a validate_application check and show the masked summary before asking for final submission confirmation. "
        "5. If a block is not in the pilot, explain politely and direct them to the local block office counter."
    ),
)


def _get_citizen_mobile(ctx) -> str:
    """Extract mobile from verified JWT claims in request state or fallback env for testing."""
    claims = getattr(ctx, "_auth_claims", None)
    if claims and claims.get("sub", "").startswith("citizen:"):
        return claims["sub"].split(":", 1)[1]
    return os.environ.get("TEST_CITIZEN_MOBILE", "9800000001")


# ---------------------------------------------------------------------------
# Citizen Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_scheme_info() -> dict:
    """
    Get the official, live scheme parameters directly from the portal rules.
    Returns monthly pension amount, age requirements, valid blocks, active pilot blocks, and deadlines.
    Always call this before explaining rules to citizens to avoid outdated information.
    """
    now = core_rules.now_ist()
    deadline = core_rules.SCHEME_DEADLINE
    window_open = now <= deadline
    hours_remaining = int((deadline - now).total_seconds() // 3600) if window_open else 0

    return {
        "scheme_name": "Purvanchal Old Age Pension Scheme",
        "monthly_pension": "Rs 250 per month",
        "minimum_age": core_rules.MIN_AGE,
        "sla_processing_days": core_rules.SLA_DAYS,
        "application_window_open": window_open,
        "application_deadline": deadline.strftime("%d %B %Y, %H:%M IST"),
        "hours_remaining": hours_remaining,
        "statutory_blocks": core_rules.STATUTORY_BLOCKS,
        "pilot_blocks_supported_by_ai": core_rules.PILOT_BLOCKS,
        "deemed_approval_policy": "Under the Right to Public Services Act, any application not decided within 15 days is automatically approved by the system."
    }


@mcp.tool()
def check_eligibility(
    date_of_birth: Annotated[str, "Date of birth in DD/MM/YYYY format, e.g. 15/08/1954"],
    block: Annotated[str, "Block name where applicant resides"],
) -> dict:
    """
    Non-binding eligibility pre-screening.
    Evaluates applicant's age and block coverage without asking for sensitive personal or banking details.
    """
    dob = core_rules.parse_dob(date_of_birth)
    if not dob:
        return {
            "eligible": False,
            "error_code": "INVALID_DOB",
            "message": "Date of birth must be in DD/MM/YYYY format (e.g. 15/08/1954)."
        }

    age = core_rules.calculate_age(dob)
    reasons = []
    is_eligible = True

    if age < core_rules.MIN_AGE:
        is_eligible = False
        reasons.append(f"Applicant is {age} years old. The minimum age required by law is {core_rules.MIN_AGE} years.")

    block_clean = (block or "").strip()
    pilot_supported = block_clean in core_rules.PILOT_BLOCKS
    statutory_supported = block_clean in core_rules.STATUTORY_BLOCKS

    if not statutory_supported:
        is_eligible = False
        reasons.append(f"'{block_clean}' is not recognized as a statutory block in Purvanchal. Valid blocks: {', '.join(core_rules.STATUTORY_BLOCKS)}.")
    elif not pilot_supported:
        reasons.append(f"Block '{block_clean}' is not currently in the AI assistant pilot. The applicant must visit the block counter or apply on the web portal.")

    return {
        "eligible": is_eligible,
        "calculated_age": age,
        "pilot_supported": pilot_supported,
        "statutory_supported": statutory_supported,
        "reasons": reasons,
        "guidance": "If eligible, proceed to collect personal, address, and bank details." if is_eligible and pilot_supported else "Cannot proceed via this AI assistant."
    }


@mcp.tool()
def validate_application(
    applicant_name: Annotated[str, "Full legal name of the applicant"],
    date_of_birth: Annotated[str, "Date of birth in DD/MM/YYYY format"],
    gender: Annotated[str, "Gender (Female, Male, Other)"],
    marital_status: Annotated[str, "Marital status (Single, Married, Widowed, Divorced)"],
    village: Annotated[str, "Village or locality name"],
    block: Annotated[str, "Block name (must be in pilot list)"],
    bank_account: Annotated[str, "Savings bank account number (9 to 18 digits)"],
    ifsc: Annotated[str, "Bank branch IFSC code (11 characters)"],
    husband_name: Annotated[str, "Husband's name if applicable"] = "",
    helper_name: Annotated[str, "Name of family member or kiosk operator assisting, if applicable"] = "",
    helper_relationship: Annotated[str, "Relationship of helper to applicant (e.g. Grandson, Daughter, CSC Operator)"] = "",
) -> dict:
    """
    Perform a dry-run validation of the entire application.
    Does NOT save anything to the database.
    Returns validation errors with specific remediation guidance, or a masked confirmation preview.
    Call this before asking the citizen for final confirmation!
    """
    helper_info = None
    if helper_name:
        helper_info = {"helper_name": helper_name, "relationship": helper_relationship}

    payload = {
        "applicant_name": applicant_name,
        "dob": date_of_birth,
        "gender": gender,
        "marital_status": marital_status,
        "village": village,
        "block": block,
        "bank_account": bank_account,
        "ifsc": ifsc,
        "husband_name": husband_name,
        "helper_info": helper_info,
        "doc_path": "PENDING_ATTACHMENT",
    }
    return pc.dry_run_validate(payload)


@mcp.tool()
def submit_application(
    ctx,
    applicant_name: Annotated[str, "Full legal name"],
    date_of_birth: Annotated[str, "DD/MM/YYYY"],
    gender: Annotated[str, "Gender"],
    marital_status: Annotated[str, "Marital status"],
    village: Annotated[str, "Village"],
    block: Annotated[str, "Block"],
    bank_account: Annotated[str, "Bank account number"],
    ifsc: Annotated[str, "Bank IFSC code"],
    user_confirmed: Annotated[bool, "Must be True. Confirm explicitly with the applicant before setting this!"],
    husband_name: Annotated[str, "Husband name if applicable"] = "",
    helper_name: Annotated[str, "Name of family member or kiosk operator assisting, if applicable"] = "",
    helper_relationship: Annotated[str, "Relationship of helper to applicant"] = "",
    doc_attachment_token: Annotated[str, "Age proof document reference or upload token"] = "ATTACHED_AGE_PROOF",
) -> dict:
    """
    Commit the verified application into the Sewa Setu portal.
    Requires user_confirmed=True.
    The mobile number is securely taken from the authenticated session (not from the model).
    Returns the official Application Number and status tracking instructions.
    """
    if not user_confirmed:
        return {
            "success": False,
            "error_code": "UNCONFIRMED_SUBMISSION",
            "message": "Submission canceled: Explicit citizen confirmation is required before filing an application."
        }

    mobile = _get_citizen_mobile(ctx)
    helper_info = None
    if helper_name:
        helper_info = {"helper_name": helper_name, "relationship": helper_relationship}

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

    res = pc.citizen_submit_application(mobile, data, doc_placeholder=doc_attachment_token, helper_info=helper_info)
    if res["success"]:
        portal_base = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
        res["tracking_url"] = f"{portal_base}/status"
        res["acknowledgment_pdf_url"] = f"{portal_base}/ack/{res['application_id']}.pdf"
    return res


@mcp.tool()
def get_application_status(ctx) -> dict:
    """
    Check the current status of all applications submitted from the signed-in mobile number.
    Returns application number, current status, review dates, and days remaining before statutory auto-approval.
    """
    mobile = _get_citizen_mobile(ctx)
    apps = db.get_applications_for_mobile(mobile)
    if not apps:
        return {
            "found": False,
            "message": "No application on record for your mobile number. Would you like assistance applying?"
        }

    for a in apps:
        a["bank_account_masked"] = core_rules.mask_sensitive_string(a.get("bank_account", ""))
        a.pop("bank_account", None)
        for k in ("submitted_at", "decided_at"):
            if a.get(k):
                a[k] = str(a[k])

    return {
        "found": True,
        "mobile_masked": core_rules.mask_sensitive_string(mobile, 3),
        "total_applications": len(apps),
        "latest_application": apps[0],
        "applications": apps
    }


@mcp.tool()
def withdraw_application(
    ctx,
    application_id: Annotated[int, "Numeric application ID to withdraw"],
    confirm: Annotated[bool, "Must be True. Confirm explicitly with the applicant."],
    reason: Annotated[str, "Reason for withdrawal (e.g. wrong bank account, name error)"],
) -> dict:
    """
    Withdraw an active PENDING application.
    Only applications in PENDING status belonging to the signed-in citizen can be withdrawn.
    Once withdrawn, the citizen is immediately free to submit a fresh application with correct details.
    """
    if not confirm:
        return {
            "success": False,
            "error_code": "UNCONFIRMED_WITHDRAWAL",
            "message": "Withdrawal requires explicit confirmation from the applicant."
        }
    mobile = _get_citizen_mobile(ctx)
    return pc.citizen_withdraw_application(application_id, mobile, reason=reason)


@mcp.tool()
def list_required_documents() -> dict:
    """
    List acceptable age-proof documents and format requirements under the Purvanchal scheme.
    """
    return {
        "valid_age_proofs": [
            "Aadhaar Card (with complete DD/MM/YYYY of birth)",
            "Electoral Photo Identity Card (Voter ID)",
            "Birth Certificate issued by Registrar of Births & Deaths",
            "Matriculation or School Leaving Certificate"
        ],
        "document_specifications": {
            "formats": ["PDF", "JPG", "PNG"],
            "max_file_size": "5 MB",
            "clarity_requirement": "Name and date of birth must match the application exactly."
        }
    }


@mcp.tool()
def get_acknowledgment_url(ctx) -> dict:
    """
    Retrieve the official computer-generated PDF acknowledgment download link for the latest application.
    """
    mobile = _get_citizen_mobile(ctx)
    apps = db.get_applications_for_mobile(mobile)
    if not apps:
        return {"found": False, "message": "No application found for this mobile number."}
    latest = apps[0]
    portal_base = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    return {
        "found": True,
        "application_no": latest["application_no"],
        "status": latest["status"],
        "download_url": f"{portal_base}/ack/{latest['id']}.pdf"
    }


# ---------------------------------------------------------------------------
# Auth Middleware
# ---------------------------------------------------------------------------

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse
import auth as auth_mod


class CitizenAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        if request.method == "OPTIONS" or request.url.path in ("/health", "/"):
            return await call_next(request)
        authz = request.headers.get("Authorization", "")
        if not authz.startswith("Bearer "):
            # For standalone testing environments without live OAuth gateway
            if os.environ.get("ALLOW_TEST_AUTH", "false").lower() == "true":
                request.state.auth_claims = {"sub": f"citizen:{os.environ.get('TEST_CITIZEN_MOBILE', '9800000001')}", "scope": "citizen"}
                return await call_next(request)
            return JSONResponse({"error": "Bearer token required in Authorization header."}, status_code=401)

        token = authz[7:]
        try:
            claims = auth_mod._decode(token, MCP_URL)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=401)

        if claims.get("scope") != "citizen":
            return JSONResponse({"error": "Token scope must be 'citizen'."}, status_code=403)

        request.state.auth_claims = claims
        return await call_next(request)


if __name__ == "__main__":
    import uvicorn
    starlette_app = mcp.streamable_http_app()
    starlette_app.add_middleware(CitizenAuthMiddleware)
    port = int(os.environ.get("CITIZEN_MCP_PORT", "8001"))
    print(f"Sewa Setu Citizen MCP Server running on port {port} (Audience: {MCP_URL})")
    uvicorn.run(starlette_app, host="0.0.0.0", port=port)
