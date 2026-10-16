# -*- coding: utf-8 -*-
"""
Eval runner for Sewa Setu citizen MCP.

For each persona:
  1. Ensures DB pre-conditions via seed_eval_data.py.
  2. Simulates the conversation by calling portal_client / db directly
     (without needing a live MCP session — tests the underlying logic).
  3. Runs SQL assertions against the DB.
  4. Saves results to eval/results/run_<timestamp>.json.

Full MCP-session replay (pointing a real Claude client at the MCP) is done
manually by the evaluator per the BRIEF.
"""
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mcp"))
sys.path.insert(0, os.path.dirname(__file__))

import db
from personas import PERSONAS, Persona
from seed_eval_data import seed

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
os.makedirs(RESULTS_DIR, exist_ok=True)


def run_assertion(assertion: dict) -> dict:
    """Run a single SQL assertion against the DB."""
    sql = assertion["sql"]
    result = {"label": assertion["label"], "sql": sql, "passed": False, "actual": None, "expected": None}
    try:
        conn = db.get_db()
        cur = conn.cursor()
        cur.execute(sql)
        row = cur.fetchone()
        cur.close(); conn.close()

        if row is None:
            result["actual"] = None
        else:
            vals = list(row.values())
            result["actual"] = vals[0] if len(vals) == 1 else vals

        actual = result["actual"]

        if "expected_equals_int" in assertion:
            expected = assertion["expected_equals_int"]
            result["expected"] = f"== {expected}"
            result["passed"] = int(actual) == expected
        elif "expected_min" in assertion:
            expected = assertion["expected_min"]
            result["expected"] = f">= {expected}"
            result["passed"] = int(actual) >= expected
        elif "expected_equals" in assertion:
            expected = assertion["expected_equals"]
            result["expected"] = f"== '{expected}'"
            result["passed"] = str(actual).strip() == expected
        elif "expected_contains" in assertion:
            expected = assertion["expected_contains"]
            result["expected"] = f"contains '{expected}'"
            result["passed"] = expected.lower() in str(actual).lower()
        else:
            result["passed"] = actual is not None
            result["expected"] = "not null"

        if isinstance(result["actual"], (int,)):
            result["actual"] = int(result["actual"])

    except Exception as e:
        result["error"] = str(e)
        result["passed"] = False
    return result


def run_persona_assertions(persona: Persona) -> list:
    results = []
    for assertion in persona.assertions:
        r = run_assertion(assertion)
        status = "\u2705 PASS" if r["passed"] else "\u274c FAIL"
        print(f"    {status}: {r['label']}")
        if not r["passed"]:
            print(f"           actual={r['actual']!r}, expected={r['expected']!r}")
        results.append(r)
    return results


def run_all() -> dict:
    print("=" * 60)
    print("Sewa Setu — Eval Run")
    print(f"Started at: {datetime.now().isoformat()}")
    print("=" * 60)

    # Seed pre-conditions
    print("\nSeeding eval pre-conditions...")
    try:
        seed()
    except Exception as e:
        print(f"WARNING: seed failed: {e}")

    all_results = {
        "_meta": {
            "run_at": datetime.now().isoformat(),
            "total_personas": len(PERSONAS),
        }
    }

    total_pass = 0
    total_fail = 0

    import portal_client as pc

    for persona in PERSONAS:
        print(f"\n[{persona.id}] {persona.name} — {persona.scenario}")
        
        # Simulate the actions for personas where the conversation resulted in submission / withdrawal
        if persona.id == "P1":
            pc.citizen_submit(persona.mobile, {
                "applicant_name": persona.name,
                "dob": persona.dob,
                "gender": persona.gender,
                "marital_status": persona.marital_status,
                "husband_name": persona.husband_name,
                "village": persona.village,
                "block": persona.block,
                "bank_account": persona.bank_account,
                "ifsc": persona.ifsc,
            })
        elif persona.id == "P4":
            pc.citizen_submit(persona.mobile, {
                "applicant_name": persona.name,
                "dob": persona.dob,
                "gender": persona.gender,
                "marital_status": persona.marital_status,
                "husband_name": "",
                "village": persona.village,
                "block": persona.block,
                "bank_account": persona.bank_account,
                "ifsc": persona.ifsc,
            })
        elif persona.id == "P6":
            # First find and withdraw the pre-seeded PENDING application
            existing = db.get_active_application(persona.mobile)
            if existing:
                pc.citizen_withdraw(existing["id"], persona.mobile)
            # Then submit afresh with the correct details
            pc.citizen_submit(persona.mobile, {
                "applicant_name": persona.name,
                "dob": persona.dob,
                "gender": persona.gender,
                "marital_status": persona.marital_status,
                "husband_name": "",
                "village": persona.village,
                "block": persona.block,
                "bank_account": persona.bank_account,
                "ifsc": persona.ifsc,
            })

        assertion_results = run_persona_assertions(persona)
        passed = sum(1 for r in assertion_results if r["passed"])
        failed = len(assertion_results) - passed
        total_pass += passed
        total_fail += failed
        print(f"  Result: {passed}/{len(assertion_results)} assertions passed")

        all_results[persona.id] = {
            "name": persona.name,
            "scenario": persona.scenario,
            "assertions": assertion_results,
            "turns": persona.turns,  # seed conversation for dashboard display
            "passed": passed,
            "failed": failed,
        }

    all_results["_meta"]["total_pass"] = total_pass
    all_results["_meta"]["total_fail"] = total_fail
    all_results["_meta"]["pass_rate"] = round(100 * total_pass / (total_pass + total_fail)) if (total_pass + total_fail) else 0

    # Save
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(RESULTS_DIR, f"run_{ts}.json")
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f"\n{'='*60}")
    print(f"Total: {total_pass} passed, {total_fail} failed")
    print(f"Pass rate: {all_results['_meta']['pass_rate']}%")
    print(f"Results saved to: {out_path}")
    return all_results


if __name__ == "__main__":
    run_all()
