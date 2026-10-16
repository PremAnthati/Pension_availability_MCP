# -*- coding: utf-8 -*-
"""
Eval Dashboard — served at /eval-dashboard.

Publicly accessible page showing:
  - All eval personas with backstory and scenario
  - Conversation transcripts (from results/ JSON files)
  - Per-assertion pass/fail status
  - Overall pass rate and last-run timestamp
"""
import os
import sys
import json
import glob
from datetime import datetime
from flask import Flask, render_template_string

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)) + "/mcp")

app = Flask(__name__)

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

# ---------------------------------------------------------------------------
# Load personas (without DB dep for dashboard)
# ---------------------------------------------------------------------------
PERSONAS_META = [
    {
        "id": "P1", "name": "Champa Devi", "age": 67, "village": "Narayantola", "block": "Sonari",
        "scenario": "Happy path: eligible widow, first application",
        "backstory": (
            "67-year-old widow from Narayantola, Sonari block. Her grandson Raju is helping her "
            "at a CSC kiosk. Speaks short Hindi sentences. Has SBI account. Wants to apply for "
            "the first time. Should result in a PENDING application in the database."
        ),
        "should_create_app": True,
    },
    {
        "id": "P2", "name": "Ramnath Prasad", "age": 55, "village": "Khelua Bazaar", "block": "Khelua",
        "scenario": "Age ineligibility (55 years old)",
        "backstory": (
            "55-year-old retired teacher from Khelua Bazaar. Heard about the pension and came to apply. "
            "Born in 1969, he does not meet the 60-year age minimum. "
            "The assistant must refuse politely and explain. No application should be created."
        ),
        "should_create_app": False,
    },
    {
        "id": "P3", "name": "Sunita Bai", "age": 70, "village": "Dhemaji", "block": "Dhemaji Pathar",
        "scenario": "Duplicate application — already has APPROVED record",
        "backstory": (
            "70-year-old widow from Dhemaji village. Already has an APPROVED application "
            "(pre-seeded in the database). She comes to apply again, possibly forgetting she "
            "already applied. The assistant must surface her existing application and NOT create a duplicate."
        ),
        "should_create_app": False,
    },
    {
        "id": "P4", "name": "Abdul Karim", "age": 72, "village": "Borgaon Tanda", "block": "Borgaon",
        "scenario": "Multi-turn low-literacy: gives information piece by piece",
        "backstory": (
            "72-year-old farmer from Borgaon Tanda. Speaks Bhojpuri-Hindi mix, gives very short answers, "
            "sometimes needs prompting. His daughter is helping. Tests the assistant's ability to "
            "gather all required fields patiently across multiple turns."
        ),
        "should_create_app": True,
    },
    {
        "id": "P5", "name": "Meena Kumari", "age": 63, "village": "Rajapara Khas", "block": "Rajapara",
        "scenario": "Scheme deadline check — tests accurate information",
        "backstory": (
            "63-year-old woman from Rajapara Khas. Her first question is whether the scheme is still "
            "open. Tests that the assistant reads the correct deadline from the portal config and "
            "does not hallucinate dates. She is eligible if the window is open."
        ),
        "should_create_app": False,
    },
    {
        "id": "P6", "name": "Gopal Singh", "age": 68, "village": "Namti Bazar", "block": "Namti",
        "scenario": "Withdraw existing PENDING, then re-apply with correct bank",
        "backstory": (
            "68-year-old farmer from Namti Bazar. Has an existing PENDING application with a wrong "
            "bank account number (pre-seeded). Wants to withdraw it and apply fresh with the correct "
            "Canara Bank details. Tests the withdraw-and-reapply flow."
        ),
        "should_create_app": True,
    },
]


def load_latest_results() -> dict:
    """Load the most recent eval run results from results/ directory."""
    pattern = os.path.join(RESULTS_DIR, "run_*.json")
    files = sorted(glob.glob(pattern), reverse=True)
    if not files:
        return {}
    with open(files[0]) as f:
        return json.load(f)


DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sewa Setu — AI Eval Dashboard</title>
<style>
  body { font-family: Arial, sans-serif; background: #f0f4f8; margin: 0; padding: 0; color: #1a1a2e; }
  header { background: #1a3c6e; color: white; padding: 20px 40px; }
  header h1 { margin: 0; font-size: 1.6em; }
  header p { margin: 4px 0 0; opacity: 0.8; font-size: 0.95em; }
  .container { max-width: 1100px; margin: 30px auto; padding: 0 20px; }
  .summary { background: white; border-radius: 8px; padding: 20px 30px; margin-bottom: 30px;
             box-shadow: 0 2px 6px rgba(0,0,0,0.08); display: flex; gap: 30px; flex-wrap: wrap; }
  .stat { text-align: center; }
  .stat .n { font-size: 2.4em; font-weight: bold; color: #1a3c6e; }
  .stat .label { font-size: 0.85em; color: #666; margin-top: 4px; }
  .pass-rate .n { color: #1b7e3c; }
  .fail-rate .n { color: #c0392b; }
  .persona-card { background: white; border-radius: 8px; margin-bottom: 24px;
                  box-shadow: 0 2px 6px rgba(0,0,0,0.08); overflow: hidden; }
  .persona-header { padding: 16px 24px; background: #1a3c6e; color: white;
                    display: flex; align-items: center; gap: 16px; }
  .persona-header .pid { background: rgba(255,255,255,0.2); border-radius: 4px;
                         padding: 2px 10px; font-size: 0.85em; font-weight: bold; }
  .persona-header h2 { margin: 0; font-size: 1.15em; }
  .persona-header .age { opacity: 0.8; font-size: 0.9em; }
  .persona-body { padding: 20px 24px; }
  .scenario-badge { display: inline-block; background: #e8f0fe; color: #1a3c6e;
                    border-radius: 20px; padding: 3px 14px; font-size: 0.82em;
                    margin-bottom: 12px; font-weight: 600; }
  .backstory { color: #444; font-size: 0.92em; line-height: 1.6; margin-bottom: 16px; }
  .assertions { border-top: 1px solid #eee; padding-top: 16px; }
  .assertions h4 { margin: 0 0 10px; font-size: 0.9em; color: #555; text-transform: uppercase;
                   letter-spacing: 0.05em; }
  .assertion { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 8px;
               font-size: 0.88em; padding: 8px 12px; border-radius: 6px; }
  .assertion.pass { background: #e8f8ee; }
  .assertion.fail { background: #fdecea; }
  .assertion.pending { background: #f5f5f5; }
  .assertion .icon { font-size: 1.1em; flex-shrink: 0; margin-top: 1px; }
  .assertion .label { flex: 1; color: #333; }
  .assertion .sql { font-family: monospace; color: #666; font-size: 0.88em;
                    background: rgba(0,0,0,0.04); padding: 2px 6px; border-radius: 3px;
                    margin-top: 3px; display: block; }
  .assertion .result { font-size: 0.85em; color: #888; margin-top: 2px; }
  .convo-toggle { background: none; border: 1px solid #ccc; border-radius: 4px;
                  padding: 4px 12px; font-size: 0.82em; cursor: pointer; color: #555;
                  margin-top: 12px; }
  .convo-toggle:hover { background: #f0f0f0; }
  .convo { display: none; margin-top: 12px; background: #fafafa; border-radius: 6px;
           padding: 16px; font-size: 0.86em; }
  .convo.open { display: block; }
  .msg { margin-bottom: 10px; }
  .msg .role { font-weight: bold; font-size: 0.82em; text-transform: uppercase;
               letter-spacing: 0.05em; margin-bottom: 2px; }
  .msg.user .role { color: #1a3c6e; }
  .msg.assistant .role { color: #1b7e3c; }
  .msg .text { color: #333; line-height: 1.5; white-space: pre-wrap; }
  .no-results { text-align: center; color: #888; padding: 30px;
                background: white; border-radius: 8px; }
  .last-run { color: #888; font-size: 0.85em; margin-top: 6px; }
  footer { text-align: center; color: #aaa; font-size: 0.82em; padding: 30px 0; }
</style>
</head>
<body>
<header>
  <h1>Sewa Setu — AI Assistant Eval Dashboard</h1>
  <p>Department of Social Welfare, Government of Purvanchal &bull; Old Age Pension Portal</p>
</header>
<div class="container">

  <!-- Summary -->
  <div class="summary">
    <div class="stat">
      <div class="n">{{ personas|length }}</div>
      <div class="label">Personas Tested</div>
    </div>
    <div class="stat">
      <div class="n">{{ total_assertions }}</div>
      <div class="label">Assertions</div>
    </div>
    <div class="stat pass-rate">
      <div class="n">{{ pass_count }}</div>
      <div class="label">Passed</div>
    </div>
    <div class="stat fail-rate">
      <div class="n">{{ fail_count }}</div>
      <div class="label">Failed</div>
    </div>
    <div class="stat pass-rate">
      <div class="n">{{ pass_rate }}%</div>
      <div class="label">Pass Rate</div>
    </div>
    {% if last_run %}
    <div class="stat">
      <div class="last-run">Last run: {{ last_run }}</div>
    </div>
    {% endif %}
  </div>

  {% if not results %}
  <div class="no-results">
    <p>No eval results yet. Run <code>python eval/run_evals.py</code> to generate results.</p>
  </div>
  {% endif %}

  <!-- Persona Cards -->
  {% for persona in personas %}
  {% set pid = persona.id %}
  {% set res = results.get(pid, {}) %}
  <div class="persona-card">
    <div class="persona-header">
      <span class="pid">{{ pid }}</span>
      <div>
        <h2>{{ persona.name }}</h2>
        <div class="age">Age {{ persona.age }} &bull; {{ persona.village }}, {{ persona.block }}</div>
      </div>
    </div>
    <div class="persona-body">
      <div class="scenario-badge">{{ persona.scenario }}</div>
      <p class="backstory">{{ persona.backstory }}</p>

      <div class="assertions">
        <h4>DB Assertions after conversation</h4>
        {% set assertion_results = res.get("assertions", []) %}
        {% if not assertion_results %}
          <div class="assertion pending">
            <span class="icon">⏳</span>
            <span class="label">No results yet — run evals to populate</span>
          </div>
        {% else %}
          {% for ar in assertion_results %}
          <div class="assertion {{ 'pass' if ar.passed else 'fail' }}">
            <span class="icon">{{ '\u2705' if ar.passed else '\u274c' }}</span>
            <div>
              <span class="label">{{ ar.label }}</span>
              <code class="sql">{{ ar.sql }}</code>
              {% if ar.actual is not none %}
              <span class="result">Result: {{ ar.actual }} {% if ar.passed %}(passed){% else %}(expected {{ ar.expected }}){% endif %}</span>
              {% endif %}
            </div>
          </div>
          {% endfor %}
        {% endif %}
      </div>

      {% if res.get("turns") %}
      <button class="convo-toggle" onclick="toggleConvo('{{ pid }}')">Show conversation</button>
      <div class="convo" id="convo-{{ pid }}">
        {% for turn in res.turns %}
        <div class="msg {{ turn.role }}">
          <div class="role">{{ turn.role }}</div>
          <div class="text">{{ turn.content }}</div>
        </div>
        {% endfor %}
      </div>
      {% endif %}

    </div>
  </div>
  {% endfor %}

</div>
<footer>Sewa Setu MCP Eval Dashboard &bull; Generated by the AI assistant layer</footer>
<script>
function toggleConvo(pid) {
  var el = document.getElementById("convo-" + pid);
  el.classList.toggle("open");
  var btn = el.previousElementSibling;
  btn.textContent = el.classList.contains("open") ? "Hide conversation" : "Show conversation";
}
</script>
</body>
</html>
'''


@app.route("/eval-dashboard")
def dashboard():
    results = load_latest_results()
    personas = PERSONAS_META

    # Compute summary stats
    total_assertions = 0
    pass_count = 0
    fail_count = 0
    for p in personas:
        ars = results.get(p["id"], {}).get("assertions", [])
        total_assertions += len(ars)
        pass_count += sum(1 for a in ars if a.get("passed"))
        fail_count += sum(1 for a in ars if not a.get("passed"))

    pass_rate = round(100 * pass_count / total_assertions) if total_assertions else 0
    last_run = results.get("_meta", {}).get("run_at", "")

    return render_template_string(
        DASHBOARD_HTML,
        personas=personas,
        results=results,
        total_assertions=total_assertions,
        pass_count=pass_count,
        fail_count=fail_count,
        pass_rate=pass_rate,
        last_run=last_run,
    )


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.environ.get("EVAL_PORT", "8003"))
    app.run(host="0.0.0.0", port=port, debug=False)
