# -*- coding: utf-8 -*-
"""
End-to-End AI Agent Simulator for Sewa Setu MCP Servers.

Simulates two AI assistants:
1. Citizen AI Assistant (helping a senior citizen apply for pension)
2. Officer AI Assistant (helping an administrative officer review and approve)
"""
import json
import httpx

PUBLIC_BASE = "https://proceedings-managing-skirt-jurisdiction.trycloudflare.com"
CITIZEN_URL = f"{PUBLIC_BASE}/mcp/citizen"
OFFICER_URL = f"{PUBLIC_BASE}/mcp/officer"

def call_mcp(url, session_id, req_id, method, params=None):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }
    if session_id:
        headers["mcp-session-id"] = session_id

    body = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
        "params": params or {}
    }
    r = httpx.post(url, headers=headers, json=body, timeout=15)
    sid = r.headers.get("mcp-session-id", session_id)
    
    # Parse SSE response text
    for line in r.text.splitlines():
        if line.startswith("data: "):
            try:
                data = json.loads(line[6:])
                return sid, data
            except Exception:
                pass
    return sid, {"raw": r.text, "status": r.status_code}

def run_agent_simulation():
    print("=" * 70)
    print("🤖 SIMULATING AI AGENT CONNECTING TO SEWA SETU MCP SERVERS")
    print(f"Citizen MCP: {CITIZEN_URL}")
    print(f"Officer MCP: {OFFICER_URL}")
    print("=" * 70)

    # ---------------------------------------------------------
    # PART 1: CITIZEN AI ASSISTANT
    # ---------------------------------------------------------
    print("\n[AGENT: CITIZEN ASSISTANT] Connecting to Citizen MCP...")
    sid, res = call_mcp(CITIZEN_URL, None, 1, "initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "Citizen-AI-Agent", "version": "1.0"}
    })
    server_name = res.get("result", {}).get("serverInfo", {}).get("name", "Unknown")
    print(f"✅ Connected to: {server_name} (Session ID: {sid})")

    # Discover tools
    _, res = call_mcp(CITIZEN_URL, sid, 2, "tools/list")
    tools = [t["name"] for t in res.get("result", {}).get("tools", [])]
    print(f"🛠️  Discovered {len(tools)} tools: {', '.join(tools)}")

    # Agent Step 1: Explain Scheme
    print("\n👉 Agent Step 1: Querying official scheme parameters (get_scheme_info)...")
    _, res = call_mcp(CITIZEN_URL, sid, 3, "tools/call", {"name": "get_scheme_info", "arguments": {}})
    scheme_text = res.get("result", {}).get("content", [{}])[0].get("text", "{}")
    scheme = json.loads(scheme_text)
    print(f"   Monthly Pension: {scheme.get('monthly_pension')}")
    print(f"   Minimum Age: {scheme.get('minimum_age')} years")
    print(f"   Application Window Open: {scheme.get('application_window_open')} (Closes: {scheme.get('application_deadline')})")

    # Agent Step 2: Check Eligibility
    print("\n👉 Agent Step 2: Checking applicant eligibility for 'Phulwa Devi', age 64, block 'Borgaon'...")
    _, res = call_mcp(CITIZEN_URL, sid, 4, "tools/call", {
        "name": "check_eligibility",
        "arguments": {"date_of_birth": "12/04/1962", "block": "Borgaon"}
    })
    elig = json.loads(res.get("result", {}).get("content", [{}])[0].get("text", "{}"))
    print(f"   Eligible: {elig.get('eligible')}, Calculated Age: {elig.get('calculated_age')}")
    print(f"   Pilot Supported: {elig.get('pilot_supported')}")

    # Agent Step 3: Validate Application (Dry Run)
    print("\n👉 Agent Step 3: Performing server-side dry-run validation (validate_application)...")
    test_mobile = "9800000099"
    app_data = {
        "applicant_name": "Phulwa Devi",
        "date_of_birth": "12/04/1962",
        "gender": "Female",
        "marital_status": "Widowed",
        "village": "Borgaon Gaon",
        "block": "Borgaon",
        "bank_account": "123456789012",
        "ifsc": "SBIN0003077",
        "husband_name": "Late Rameshwar Devi",
        "helper_name": "Anita (Daughter)",
        "helper_relationship": "Daughter"
    }
    _, res = call_mcp(CITIZEN_URL, sid, 5, "tools/call", {
        "name": "validate_application",
        "arguments": app_data
    })
    val = json.loads(res.get("result", {}).get("content", [{}])[0].get("text", "{}"))
    print(f"   Dry-run Validation Passed: {val.get('is_valid')}")
    print(f"   Masked Account: {val.get('preview_record', {}).get('bank_account_masked')}")

    # Agent Step 4: Submit Application with Explicit Confirmation
    print("\n👉 Agent Step 4: Filing verified application (submit_application)...")
    sub_args = dict(app_data)
    sub_args["user_confirmed"] = True
    sub_args["mobile"] = test_mobile
    _, res = call_mcp(CITIZEN_URL, sid, 6, "tools/call", {
        "name": "submit_application",
        "arguments": sub_args
    })
    sub = json.loads(res.get("result", {}).get("content", [{}])[0].get("text", "{}"))
    new_app_no = sub.get("application_no")
    new_app_id = sub.get("application_id")
    print(f"   Application Status: {sub.get('status')}")
    print(f"   Application Number: {new_app_no} (ID: {new_app_id})")
    print(f"   Tracking Portal: {sub.get('tracking_url')}")

    # Agent Step 5: Check Application Status
    print(f"\n👉 Agent Step 5: Tracking status for mobile {test_mobile} (get_application_status)...")
    _, res = call_mcp(CITIZEN_URL, sid, 7, "tools/call", {
        "name": "get_application_status",
        "arguments": {"mobile": test_mobile}
    })
    stat = json.loads(res.get("result", {}).get("content", [{}])[0].get("text", "{}"))
    latest = stat.get("latest_application", {})
    print(f"   Record Found: {stat.get('found')}")
    print(f"   Application No: {latest.get('application_no')}")
    print(f"   Status: {latest.get('status')}")
    print(f"   Days Remaining in SLA: {latest.get('days_remaining')}")

    # ---------------------------------------------------------
    # PART 2: OFFICER AI ASSISTANT
    # ---------------------------------------------------------
    print("\n" + "-" * 70)
    print("[AGENT: OFFICER ASSISTANT] Connecting to Officer MCP...")
    sid_off, res = call_mcp(OFFICER_URL, None, 10, "initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "Officer-AI-Agent", "version": "1.0"}
    })
    server_name = res.get("result", {}).get("serverInfo", {}).get("name", "Unknown")
    print(f"✅ Connected to: {server_name} (Session ID: {sid_off})")

    # Discover tools
    _, res = call_mcp(OFFICER_URL, sid_off, 11, "tools/list")
    tools = [t["name"] for t in res.get("result", {}).get("tools", [])]
    print(f"🛠️  Discovered {len(tools)} officer tools: {', '.join(tools)}")

    # Officer Step 1: Queue Summary
    print("\n👉 Officer Step 1: Retrieving review queue summary (get_queue_summary)...")
    _, res = call_mcp(OFFICER_URL, sid_off, 12, "tools/call", {
        "name": "get_queue_summary",
        "arguments": {}
    })
    q = json.loads(res.get("result", {}).get("content", [{}])[0].get("text", "{}"))
    print(f"   Officer: {q.get('officer')}, Assigned Block: {q.get('assigned_block')}")
    print(f"   Total Pending: {q.get('total_pending')}, Overdue SLA: {q.get('overdue_past_15_days_sla')}")

    # Officer Step 2: List Pending Cases
    print("\n👉 Officer Step 2: Listing pending cases (list_pending_applications)...")
    _, res = call_mcp(OFFICER_URL, sid_off, 13, "tools/call", {
        "name": "list_pending_applications",
        "arguments": {"page": 1, "page_size": 5}
    })
    pending_res = json.loads(res.get("result", {}).get("content", [{}])[0].get("text", "{}"))
    cases = pending_res.get("applications", [])
    print(f"   Pending Cases in Queue: {len(cases)}")
    for c in cases[:2]:
        print(f"     • ID {c.get('id')}: {c.get('application_no')} ({c.get('applicant_name')}) - {c.get('days_remaining')} days left")

    # Officer Step 3: Inspect Newly Created Case
    if new_app_id:
        print(f"\n👉 Officer Step 3: Inspecting case #{new_app_id} (get_case_details)...")
        _, res = call_mcp(OFFICER_URL, sid_off, 14, "tools/call", {
            "name": "get_case_details",
            "arguments": {"application_id": new_app_id}
        })
        case = json.loads(res.get("result", {}).get("content", [{}])[0].get("text", "{}"))
        print(f"   Applicant: {case.get('applicant_name')}, DOB: {case.get('dob')}")
        print(f"   Masked Bank: {case.get('bank_account_masked')}")
        print(f"   Audit Trail Entries: {len(case.get('audit_trail', []))}")

        # Officer Step 4: Approve Case with Reason
        print(f"\n👉 Officer Step 4: Approving case #{new_app_id} with justification (approve_application)...")
        _, res = call_mcp(OFFICER_URL, sid_off, 15, "tools/call", {
            "name": "approve_application",
            "arguments": {
                "application_id": new_app_id,
                "reason": "Verified age proof and active SBI savings account.",
                "confirm": True
            }
        })
        appr = json.loads(res.get("result", {}).get("content", [{}])[0].get("text", "{}"))
        print(f"   Approval Success: {appr.get('success')}")
        print(f"   New Status: {appr.get('new_status')}")

    print("\n" + "=" * 70)
    print("🎉 FULL AI AGENT WORKFLOW COMPLETED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    run_agent_simulation()
