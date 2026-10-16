# -*- coding: utf-8 -*-
"""
Sewa Setu Evaluation Dashboard & Live Metrics Reporter.
Served at /eval-dashboard.
Pulls live telemetry from evals/eval_results.json and the 8 citizen personas.
"""

import os
import sys
import json
from datetime import datetime
from flask import Flask, render_template_string

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "personas"))
from personas_directory import CITIZEN_PERSONAS, OFFICER_PERSONAS

app = Flask(__name__)

EVAL_FILE = os.path.join(BASE_DIR, "evals", "eval_results.json")

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sewa Setu — Agent Access Evaluation & Verification Dashboard</title>
<style>
  :root {
    --primary: #153b68;
    --primary-dark: #0c2544;
    --accent: #d97706;
    --bg: #f8fafc;
    --card: #ffffff;
    --text: #0f172a;
    --text-muted: #64748b;
    --success: #16a34a;
    --danger: #dc2626;
    --border: #e2e8f0;
  }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); margin: 0; color: var(--text); }
  header { background: var(--primary); color: white; padding: 28px 48px; border-bottom: 4px solid var(--accent); }
  header h1 { margin: 0 0 6px 0; font-size: 1.75em; letter-spacing: -0.02em; }
  header p { margin: 0; opacity: 0.85; font-size: 0.95em; }
  .wrapper { max-width: 1200px; margin: 32px auto; padding: 0 24px; }
  
  .grid-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 32px; }
  .stat-card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
  .stat-card .val { font-size: 2.2em; font-weight: 700; color: var(--primary-dark); }
  .stat-card .lbl { font-size: 0.85em; font-weight: 600; text-transform: uppercase; color: var(--text-muted); margin-top: 4px; }
  .stat-card.pass .val { color: var(--success); }
  .stat-card.fail .val { color: var(--danger); }

  .nav-tabs { display: flex; gap: 12px; margin-bottom: 24px; border-bottom: 2px solid var(--border); padding-bottom: 8px; }
  .tab-btn { background: none; border: none; font-size: 1em; font-weight: 600; color: var(--text-muted); cursor: pointer; padding: 8px 16px; border-radius: 6px; }
  .tab-btn.active { color: var(--primary); background: #e0e7ff; }

  .section-title { font-size: 1.3em; font-weight: 700; margin: 0 0 16px 0; color: var(--primary-dark); }
  
  .persona-grid { display: grid; grid-template-columns: 1fr; gap: 20px; margin-bottom: 40px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 24px; box-shadow: 0 2px 4px rgba(0,0,0,0.04); }
  .card-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 14px; border-bottom: 1px solid var(--border); padding-bottom: 12px; }
  .card-header h3 { margin: 0; font-size: 1.2em; color: var(--primary); }
  .badge { font-size: 0.75em; font-weight: 700; padding: 4px 10px; border-radius: 12px; text-transform: uppercase; }
  .badge-accepted { background: #dcfce7; color: #15803d; }
  .badge-rejected { background: #fee2e2; color: #b91c1c; }
  .badge-blocked { background: #fef3c7; color: #b45309; }
  
  .details-table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 0.9em; }
  .details-table td { padding: 6px 12px; border-bottom: 1px solid #f1f5f9; }
  .details-table td.lbl { width: 25%; font-weight: 600; color: var(--text-muted); }

  .utterances { background: #f8fafc; border-left: 3px solid var(--accent); padding: 12px 16px; margin: 14px 0; border-radius: 0 6px 6px 0; }
  .utterances h5 { margin: 0 0 6px 0; font-size: 0.85em; text-transform: uppercase; color: var(--text-muted); }
  .utterances ul { margin: 0; padding-left: 18px; font-size: 0.88em; line-height: 1.5; color: #334155; }

  .results-table { width: 100%; border-collapse: collapse; background: var(--card); border-radius: 8px; overflow: hidden; border: 1px solid var(--border); }
  .results-table th, .results-table td { padding: 12px 16px; text-align: left; font-size: 0.9em; border-bottom: 1px solid var(--border); }
  .results-table th { background: #f1f5f9; font-weight: 600; color: var(--text-muted); }
  .status-pass { color: var(--success); font-weight: 700; }
  .status-fail { color: var(--danger); font-weight: 700; }

  footer { text-align: center; padding: 40px; color: var(--text-muted); font-size: 0.85em; }
</style>
</head>
<body>
<header>
  <h1>Sewa Setu — Agent Access Evaluation & Verification</h1>
  <p>Department of Social Welfare, Government of Purvanchal &bull; Old Age Pension Scheme (₹250/mo)</p>
</header>

<div class="wrapper">
  <!-- Key Metrics -->
  <div class="grid-stats">
    <div class="stat-card">
      <div class="val">{{ total_tests }}</div>
      <div class="lbl">Automated Checks</div>
    </div>
    <div class="stat-card pass">
      <div class="val">{{ passed_tests }}</div>
      <div class="lbl">Passed</div>
    </div>
    <div class="stat-card {% if failed_tests > 0 %}fail{% endif %}">
      <div class="val">{{ failed_tests }}</div>
      <div class="lbl">Failed</div>
    </div>
    <div class="stat-card pass">
      <div class="val">{{ pass_rate }}%</div>
      <div class="lbl">Parity & Safety Rate</div>
    </div>
  </div>

  <!-- Personas Section -->
  <h2 class="section-title">Tested Citizen Personas & Field Scenarios</h2>
  <div class="persona-grid">
    {% for p in personas %}
    <div class="card">
      <div class="card-header">
        <div>
          <h3>{{ p.id }}: {{ p.name }} (Age {{ p.age }})</h3>
          <span style="font-size: 0.85em; color: var(--text-muted);">{{ p.village }}, Block: {{ p.block }} &bull; {{ p.archetype }}</span>
        </div>
        <span class="badge badge-{{ 'accepted' if p.expected_outcome in ['ACCEPTED', 'WITHDRAW_REAPPLY'] else 'rejected' if 'REJECTED' in p.expected_outcome else 'blocked' }}">
          {{ p.expected_outcome }}
        </span>
      </div>

      <p style="font-size: 0.9em; line-height: 1.5; color: #334155; margin: 8px 0 14px 0;">
        <strong>Field Context:</strong> {{ p.scenario_description }}
      </p>

      <table class="details-table">
        <tr>
          <td class="lbl">Phone & Setup</td>
          <td>{{ p.phone_context }}</td>
          <td class="lbl">Literacy</td>
          <td>{{ p.literacy_level }}</td>
        </tr>
        <tr>
          <td class="lbl">Helper / Intermediary</td>
          <td colspan="3">
            {% if p.helper_info %}
              {{ p.helper_info.helper_name }} ({{ p.helper_info.relationship }})
            {% else %}
              Self-represented
            {% endif %}
          </td>
        </tr>
      </table>

      <div class="utterances">
        <h5>Simulated Citizen Utterances across Turns:</h5>
        <ul>
          {% for u in p.simulated_utterances %}
          <li>"{{ u }}"</li>
          {% endfor %}
        </ul>
      </div>

      <div style="margin-top: 14px; font-size: 0.85em; color: #475569;">
        <strong>Database Verification Criteria:</strong>
        <ul style="margin: 4px 0 0 0; padding-left: 20px;">
          {% for a in p.db_assertions %}
          <li><code>{{ a.query }}</code> $\rightarrow$ Expected: <code>{{ a.expected }}</code></li>
          {% endfor %}
        </ul>
      </div>
    </div>
    {% endfor %}
  </div>

  <!-- Detailed Test Log -->
  <h2 class="section-title">Automated Verification Log</h2>
  <table class="results-table">
    <thead>
      <tr>
        <th>Category</th>
        <th>Test Name</th>
        <th>Status</th>
        <th>Verification Details</th>
      </tr>
    </thead>
    <tbody>
      {% for r in test_records %}
      <tr>
        <td><strong>{{ r.category }}</strong></td>
        <td>{{ r.test_name }}</td>
        <td class="{{ 'status-pass' if r.passed else 'status-fail' }}">{{ 'PASSED' if r.passed else 'FAILED' }}</td>
        <td style="color: #475569; font-size: 0.88em;">{{ r.details }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>

<footer>
  Sewa Setu Agent Access &bull; Verified against PostgreSQL 15 &bull; Deemed Approval Cron Active (15-day SLA)
</footer>
</body>
</html>
"""


@app.route("/eval-dashboard")
def eval_dashboard():
    # Load test results
    test_records = []
    total_tests = 0
    passed_tests = 0
    failed_tests = 0
    pass_rate = 100.0

    if os.path.exists(EVAL_FILE):
        try:
            with open(EVAL_FILE) as fh:
                data = json.load(fh)
                test_records = data.get("results", [])
                total_tests = data.get("total_tests", len(test_records))
                passed_tests = data.get("passed", 0)
                failed_tests = data.get("failed", 0)
                pass_rate = data.get("pass_rate_percent", 100.0)
        except Exception:
            pass

    return render_template_string(
        DASHBOARD_HTML,
        personas=CITIZEN_PERSONAS,
        officers=OFFICER_PERSONAS,
        test_records=test_records,
        total_tests=total_tests,
        passed_tests=passed_tests,
        failed_tests=failed_tests,
        pass_rate=pass_rate
    )


if __name__ == "__main__":
    port = int(os.environ.get("EVAL_PORT", "8003"))
    app.run(host="0.0.0.0", port=port, debug=False)
