# -*- coding: utf-8 -*-
"""
Sewa Setu — Officer AI Assistant MCP Server

Streamable-HTTP MCP server for block officers.
Bound at /mcp/officer. Auth: officer-scope OAuth 2.1 JWT from the portal.

Design rules:
  - Completely separate endpoint from citizen MCP.
  - Officer identity comes from JWT sub claim.
  - Approve/reject go through portal_client.py → audit_log.
  - Read operations use direct DB access for speed.
"""
import os
import sys
from typing import Annotated
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
import db
import portal_client as pc

MCP_URL = os.environ.get(
    "OFFICER_MCP_URL",
    os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/") + "/mcp/officer"
)

BLOCKS = ["Sonari", "Rajapara", "Dhemaji Pathar", "Borgaon", "Namti", "Khelua"]

mcp = FastMCP(
    "Sewa Setu Officer Assistant",
    instructions=(
        "You are the AI assistant for block officers of the Sewa Setu Old Age Pension portal. "
        "Help the officer review applications, check details, and record approve/reject decisions. "
        "Every decision is recorded in the audit log with the officer's identity and reason. "
        "Never approve or reject without a reason. "
        "Always show the officer the application details before asking for a decision."
    ),
)


def _officer_from_ctx(ctx) -> str:
    """Extract officer identity from JWT sub claim."""
    claims = getattr(ctx, "_auth_claims", None)
    if claims:
        sub = claims.get("sub", "")
        if sub.startswith("officer:"):
            return sub.split(":", 1)[1]
    return os.environ.get("TEST_OFFICER_NAME", "officer")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_dashboard_summary() -> dict:
    """
    Get a summary of all applications: counts by status, overdue count,
    and pending applications by block.
    Call this first to give the officer an overview of what needs attention.
    """
    summary = db.dashboard_summary()
    summary["sla_days"] = 15
    summary["note"] = (
        "'overdue_pending' are applications still PENDING after 15 days. "
        "They will be automatically approved (deemed) by the nightly job."
    )
    return summary


@mcp.tool()
def list_pending_applications(
    block: Annotated[str, "Filter by block name, or leave empty for all blocks"] = "",
    page: Annotated[int, "Page number (1-indexed)"] = 1,
) -> dict:
    """
    List applications currently in PENDING status, optionally filtered by block.
    Returns 20 applications per page, oldest first (FIFO — earliest submitted gets priority).
    """
    block_filter = block.strip() if block.strip() in BLOCKS else None
    if block.strip() and not block_filter:
        return {
            "error": f"Block '{block}' not recognised. Valid blocks: {', '.join(BLOCKS)}"
        }
    rows = db.list_pending(block=block_filter, page=page)
    for r in rows:
        for k in ("submitted_at",):
            if r.get(k):
                r[k] = str(r[k])
    return {
        "block_filter": block_filter or "all",
        "page": page,
        "count": len(rows),
        "applications": rows,
        "note": "Call get_application_detail(id) to see full details before deciding.",
    }


@mcp.tool()
def get_application_detail(
    application_id: Annotated[int, "The numeric application ID"],
) -> dict:
    """
    Get full details of a single application, including personal details,
    bank information, and the complete audit trail.
    Always call this before approving or rejecting.
    """
    app = db.get_application_detail(application_id)
    if not app:
        return {"found": False, "error": f"No application found with ID {application_id}."}
    audit = db.get_application_audit(application_id)
    # Format dates
    for k in ("dob", "submitted_at", "decided_at"):
        if app.get(k):
            app[k] = str(app[k])
    for entry in audit:
        if entry.get("at"):
            entry["at"] = str(entry["at"])
    # Mask bank account for privacy (show last 4 digits only)
    if app.get("bank_account") and len(app["bank_account"]) > 4:
        app["bank_account_masked"] = "*" * (len(app["bank_account"]) - 4) + app["bank_account"][-4:]
    app["audit_trail"] = audit
    app["found"] = True
    return app


@mcp.tool()
def search_by_mobile(
    mobile: Annotated[str, "10-digit mobile number to search"],
) -> dict:
    """
    Find all applications associated with a mobile number.
    Use this when a citizen contacts the office about their application.
    """
    if not mobile.isdigit() or len(mobile) != 10:
        return {"error": "Please provide a valid 10-digit mobile number."}
    rows = db.search_by_mobile(mobile)
    for r in rows:
        for k in ("submitted_at",):
            if r.get(k):
                r[k] = str(r[k])
    return {
        "mobile": mobile,
        "found": len(rows),
        "applications": rows,
    }


@mcp.tool()
def list_overdue_applications(
    page: Annotated[int, "Page number (1-indexed)"] = 1,
) -> dict:
    """
    List PENDING applications that have exceeded the 15-day SLA.
    These are at risk of deemed approval. Review urgently.
    """
    rows = db.list_overdue(page=page)
    for r in rows:
        for k in ("submitted_at",):
            if r.get(k):
                r[k] = str(r[k])
    return {
        "page": page,
        "count": len(rows),
        "applications": rows,
        "warning": (
            "These applications will be automatically approved if not decided. "
            "Please review and act on them."
        ),
    }


@mcp.tool()
def approve_application(
    ctx,
    application_id: Annotated[int, "The numeric application ID to approve"],
    reason: Annotated[str, "Reason for approval — will be recorded in the audit trail"],
    confirm: Annotated[bool, "Must be true. Confirm with the officer before calling."],
) -> dict:
    """
    Approve a PENDING application. Records the officer's identity and reason.

    WORKFLOW:
    1. Call get_application_detail(application_id) to show details.
    2. Ask the officer for a reason.
    3. Ask the officer to confirm.
    4. Only then call this tool.

    Only PENDING applications can be approved.
    """
    if not confirm:
        return {"success": False, "reason": "Approval not confirmed by officer."}
    if not reason or not reason.strip():
        return {"success": False, "reason": "A reason must be provided for the approval."}
    actor = _officer_from_ctx(ctx)
    result = pc.officer_approve(application_id, reason.strip(), actor=actor)
    if result["success"]:
        result["message"] = (
            f"Application {result['application_no']} has been APPROVED. "
            f"Reason recorded: '{reason.strip()}'. Actor: {actor}."
        )
    return result


@mcp.tool()
def reject_application(
    ctx,
    application_id: Annotated[int, "The numeric application ID to reject"],
    reason: Annotated[str, "Reason for rejection — will be recorded and may be communicated to the citizen"],
    confirm: Annotated[bool, "Must be true. Confirm with the officer before calling."],
) -> dict:
    """
    Reject a PENDING application. Records the officer's identity and reason.

    WORKFLOW:
    1. Call get_application_detail(application_id) to show details.
    2. Ask the officer for a specific reason.
    3. Ask the officer to confirm.
    4. Only then call this tool.

    Only PENDING applications can be rejected.
    A rejection reason is mandatory and will be recorded in the audit log.
    """
    if not confirm:
        return {"success": False, "reason": "Rejection not confirmed by officer."}
    if not reason or not reason.strip():
        return {"success": False, "reason": "A reason must be provided for the rejection."}
    actor = _officer_from_ctx(ctx)
    result = pc.officer_reject(application_id, reason.strip(), actor=actor)
    if result["success"]:
        result["message"] = (
            f"Application {result['application_no']} has been REJECTED. "
            f"Reason recorded: '{reason.strip()}'. Actor: {actor}."
        )
    return result


# ---------------------------------------------------------------------------
# Auth middleware
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
            return JSONResponse(
                {"error": "Authorization header with Bearer token required."},
                status_code=401,
            )
        token = authz[7:]
        try:
            claims = auth_mod._decode(token, MCP_URL)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=401)
        if claims.get("scope") != "officer":
            return JSONResponse(
                {"error": "This endpoint requires an officer-scope token."},
                status_code=403,
            )
        request.state.auth_claims = claims
        return await call_next(request)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    starlette_app = mcp.streamable_http_app()
    starlette_app.add_middleware(OfficerAuthMiddleware)
    port = int(os.environ.get("OFFICER_MCP_PORT", "8002"))
    print(f"Officer MCP server starting on port {port}")
    print(f"MCP URL: {MCP_URL}")
    uvicorn.run(starlette_app, host="0.0.0.0", port=port)
