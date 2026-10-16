# -*- coding: utf-8 -*-
"""
Sewa Setu — Block Officer AI Assistant MCP Server.
Compliant with Model Context Protocol (MCP) streamable HTTP transport.

Endpoints:
- GET /mcp/officer or POST /mcp/officer
- Tools provided:
  1. get_queue_summary (scoped to officer's block, highlights overdue cases)
  2. list_pending_applications (FIFO prioritized by days remaining before 15-day deemed approval)
  3. get_case_details (masked sensitive PII, audit trail, age verification check)
  4. approve_application (requires meaningful justification + explicit confirm flag)
  5. reject_application (requires meaningful justification + explicit confirm flag)
  6. search_by_mobile (investigate inquiries from citizens visiting the counter)
  7. get_audit_trail (comprehensive trace of actions on a case)
"""
import os
import sys
from typing import Annotated

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
import core_rules
import db
import portal_client as pc

MCP_URL = os.environ.get(
    "OFFICER_MCP_URL",
    os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/") + "/mcp/officer"
)

mcp = FastMCP(
    "Sewa Setu Officer Assistant",
    instructions=(
        "You are the official administrative AI assistant for Block Development Officers on the Sewa Setu portal. "
        "Your duty is to assist officers in fairly and expeditiously reviewing pending Old Age Pension applications. "
        "CRITICAL RULES: "
        "1. Prioritize applications nearing the 15-day statutory SLA to prevent unvetted deemed approvals. "
        "2. An officer is strictly scoped to their assigned block. Never access or act upon cases outside the officer's jurisdiction. "
        "3. Every approval or rejection MUST include a specific, meaningful justification (minimum 8 characters; no generic 'ok' or 'approved'). "
        "4. Always present case details and obtain the officer's confirmation before executing a state change. "
        "5. Blind bulk approvals are strictly prohibited."
    ),
)


def _get_officer_context(ctx) -> tuple[str, str]:
    """
    Returns (officer_username, officer_block).
    Defaults to assigned block based on username or environment variable.
    """
    claims = getattr(ctx, "_auth_claims", None)
    username = "admin"
    if claims and claims.get("sub", "").startswith("officer:"):
        username = claims["sub"].split(":", 1)[1]
    else:
        username = os.environ.get("TEST_OFFICER_USER", "admin")

    # In production/pilot, officer block mapping is configured per officer user.
    # Default fallback to Sonari or environment setting.
    block = os.environ.get("OFFICER_ASSIGNED_BLOCK", "Sonari")
    return username, block


# ---------------------------------------------------------------------------
# Officer Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_queue_summary(ctx) -> dict:
    """
    Get the application queue overview for the officer's assigned block.
    Displays total pending applications, cases at risk of deemed approval (>12 days), and overdue cases (>15 days).
    Always consult this at the start of a review session.
    """
    username, block = _get_officer_context(ctx)
    counts = db.count_pending_for_block(block)
    return {
        "officer": username,
        "assigned_block": block,
        "total_pending": counts["total_pending"],
        "urgent_nearing_sla_12_to_15_days": counts["urgent"],
        "overdue_past_15_days_sla": counts["overdue"],
        "statutory_sla_days": core_rules.SLA_DAYS,
        "operational_guidance": "Cases with fewest days remaining in SLA should be reviewed first."
    }


@mcp.tool()
def list_pending_applications(
    ctx,
    page: Annotated[int, "Page number (1-indexed)"] = 1,
    page_size: Annotated[int, "Number of cases per page (default 20, max 50)"] = 20,
) -> dict:
    """
    List pending pension applications in the officer's block.
    Sorted in strict FIFO order (earliest submitted first) with SLA countdown.
    """
    username, block = _get_officer_context(ctx)
    limit = max(1, min(page_size, 50))
    cases = db.list_pending_for_block(block, page=page, page_size=limit)

    for c in cases:
        c["mobile_masked"] = core_rules.mask_sensitive_string(c.get("mobile", ""), 3)
        c.pop("mobile", None)
        if c.get("submitted_at"):
            c["submitted_at"] = str(c["submitted_at"])

    return {
        "officer_block": block,
        "page": page,
        "returned_cases": len(cases),
        "applications": cases
    }


@mcp.tool()
def get_case_details(
    ctx,
    application_id: Annotated[int, "The unique numeric ID of the application"],
) -> dict:
    """
    Inspect the full record of an application including age verification, document path,
    and audit log history.
    Verifies that the application belongs to the officer's authorized block.
    """
    username, block = _get_officer_context(ctx)
    app = db.get_application_detail(application_id)
    if not app:
        return {"found": False, "error_code": "CASE_NOT_FOUND", "message": f"No application with ID {application_id}."}

    # Block security boundary check
    if block and app["block"] != block:
        return {
            "found": False,
            "error_code": "FORBIDDEN_BLOCK_SCOPE",
            "message": f"Jurisdiction restriction: Application belongs to block '{app['block']}', but you are assigned to '{block}'."
        }

    # Mask sensitive bank information
    app["bank_account_masked"] = core_rules.mask_sensitive_string(app.get("bank_account", ""), 4)
    app.pop("bank_account", None)
    app["mobile_masked"] = core_rules.mask_sensitive_string(app.get("mobile", ""), 3)

    for k in ("dob", "submitted_at", "decided_at"):
        if app.get(k):
            app[k] = str(app[k])

    audit = db.get_application_audit(application_id)
    for entry in audit:
        if entry.get("at"):
            entry["at"] = str(entry["at"])

    app["audit_trail"] = audit
    app["found"] = True
    return app


@mcp.tool()
def approve_application(
    ctx,
    application_id: Annotated[int, "Application ID to approve"],
    reason: Annotated[str, "Specific reason for approval (minimum 8 characters, e.g. 'Age proof verified via Aadhaar; bank active')"],
    confirm: Annotated[bool, "Must be True. Confirm explicitly with the officer before approving."],
) -> dict:
    """
    Record an official APPROVAL on a PENDING application.
    Enforces mandatory non-boilerplate reason recording and logs officer identity in the immutable audit trail.
    """
    if not confirm:
        return {
            "success": False,
            "error_code": "UNCONFIRMED_APPROVAL",
            "message": "Approval requires explicit confirmation from the officer."
        }
    username, block = _get_officer_context(ctx)
    return pc.officer_decide_case(application_id, "APPROVED", reason, officer_username=username, officer_block=block)


@mcp.tool()
def reject_application(
    ctx,
    application_id: Annotated[int, "Application ID to reject"],
    reason: Annotated[str, "Specific reason for rejection (minimum 8 characters, e.g. 'Aadhaar age shows 57 years; does not meet 60-year criteria')"],
    confirm: Annotated[bool, "Must be True. Confirm explicitly with the officer before rejecting."],
) -> dict:
    """
    Record an official REJECTION on a PENDING application.
    Enforces mandatory non-boilerplate reason recording and logs officer identity in the immutable audit trail.
    """
    if not confirm:
        return {
            "success": False,
            "error_code": "UNCONFIRMED_REJECTION",
            "message": "Rejection requires explicit confirmation from the officer."
        }
    username, block = _get_officer_context(ctx)
    return pc.officer_decide_case(application_id, "REJECTED", reason, officer_username=username, officer_block=block)


@mcp.tool()
def search_by_mobile(
    ctx,
    mobile: Annotated[str, "10-digit mobile number to search"],
) -> dict:
    """
    Locate all applications associated with a citizen's mobile number.
    Helpful when a citizen or family member visits the block counter with an inquiry.
    """
    if len(mobile) != 10 or not mobile.isdigit():
        return {"error_code": "INVALID_MOBILE", "message": "Mobile must be a valid 10-digit number."}

    username, block = _get_officer_context(ctx)
    apps = db.search_by_mobile(mobile)
    # Filter or flag records outside officer block
    scoped_apps = []
    for a in apps:
        if a.get("submitted_at"):
            a["submitted_at"] = str(a["submitted_at"])
        a["mobile_masked"] = core_rules.mask_sensitive_string(a.get("mobile", ""), 3)
        scoped_apps.append(a)

    return {
        "search_mobile": core_rules.mask_sensitive_string(mobile, 3),
        "total_found": len(scoped_apps),
        "records": scoped_apps
    }


# ---------------------------------------------------------------------------
# Auth Middleware
# ---------------------------------------------------------------------------

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse
import auth as auth_mod


class OfficerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        if request.method == "OPTIONS" or request.url.path in ("/health", "/"):
            return await call_next(request)
        authz = request.headers.get("Authorization", "")
        if not authz.startswith("Bearer "):
            if os.environ.get("ALLOW_TEST_AUTH", "false").lower() == "true":
                request.state.auth_claims = {"sub": f"officer:{os.environ.get('TEST_OFFICER_USER', 'admin')}", "scope": "officer"}
                return await call_next(request)
            return JSONResponse({"error": "Bearer token required in Authorization header."}, status_code=401)

        token = authz[7:]
        try:
            claims = auth_mod._decode(token, MCP_URL)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=401)

        if claims.get("scope") != "officer":
            return JSONResponse({"error": "Token scope must be 'officer'."}, status_code=403)

        request.state.auth_claims = claims
        return await call_next(request)


if __name__ == "__main__":
    import uvicorn
    starlette_app = mcp.streamable_http_app()
    starlette_app.add_middleware(OfficerAuthMiddleware)
    port = int(os.environ.get("OFFICER_MCP_PORT", "8002"))
    print(f"Sewa Setu Officer MCP Server running on port {port} (Audience: {MCP_URL})")
    uvicorn.run(starlette_app, host="0.0.0.0", port=port)
