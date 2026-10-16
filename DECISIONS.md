# DECISIONS: Sewa Setu Agent Access Architecture

**Fellowship Cohort:** Bharat Digital Fellowship  
**Project:** Model Context Protocol (MCP) Agent Access for the Old Age Pension Portal  
**Jurisdiction:** Department of Social Welfare, Government of Purvanchal  

---

### Decision 1: Sub-Claim Inversion for Zero-Trust Identity Isolation

- **Options Considered:**
  1. *Parameter-based identity:* Let tools accept a `mobile` argument (e.g. `get_application_status(mobile="...")`).
  2. *Custom secondary database:* Build a separate API key or user table for the AI layer.
  3. *Sub-claim inversion (Chosen):* Piggyback directly on Sewa Setu's OAuth 2.1 authorization server (RFC 8414 / RFC 8707). Extract the authenticated citizen mobile strictly from the verified JWT `sub` claim (`citizen:<mobile>`).
- **Rationale for Choice:**
  Applicants in rural Purvanchal predominantly use shared family smartphones or sit at village CSC kiosks. If an AI tool took a mobile number as an LLM argument, any user prompt could snoop on or withdraw another senior citizen's pension application. By tying the identity strictly to the RS256 token claims validated against `/.well-known/jwks.json`, identity spoofing is mathematically impossible regardless of model hallucination or adversarial prompt injection.
- **Trade-off:**
  Requires the MCP client to initiate standard OAuth 2.1 PKCE authorization with the portal before invoking the citizen server.

---

### Decision 2: Shared Core Business Rules (Zero-Drift Enforcement)

- **Options Considered:**
  1. *Prompt-based validation:* Instruct the AI assistant in system prompts to reject applicants under 60 or outside allowed blocks.
  2. *Duplicate validation routines:* Re-implement regex and age checks inside the MCP tool functions.
  3. *Imported Shared Core (`core_rules.py`, Chosen):* Extract the single source of truth for validation rules (`validate_application_data`) and dynamic settings from `config/app.ini`, directly imported by both the Flask web routes and the FastMCP tools.
- **Rationale for Choice:**
  The Director's mandate was uncompromising: *"The assistant must never get anyone a pension the counter or paper form would not."* Server-side Python logic enforces statutory age limits ($\ge 60$), RBI-compliant bank account lengths (9–18 digits), IFSC formatting (`[A-Z]{4}0[A-Z0-9]{6}`), and application deadlines. If policy rules change in `app.ini`, all channels immediately inherit the update without code drift.
- **Trade-off:**
  Requires tool developers to structure input data into normalized dictionaries before executing validation.

---

### Decision 3: Physical Capability & Endpoint Bifurcation (`/mcp/citizen` vs `/mcp/officer`)

- **Options Considered:**
  1. *Single monolithic MCP server:* One endpoint serving both citizens and officers, with internal role checks inside tools.
  2. *Separate decoupled FastMCP processes (Chosen):* Host `/mcp/citizen` and `/mcp/officer` as independent services on distinct ports behind Nginx.
- **Rationale for Choice:**
  An assistant interacting with a citizen or family helper should have zero awareness of administrative tools like `approve_application` or `list_pending_applications`. Eliminating administrative tools from the citizen server's capability declaration (`tools/list`) removes the possibility of privilege escalation attacks or model confusion. Furthermore, the officer server strictly scopes each officer to their assigned block and mandates recorded non-boilerplate justifications for all decisions.
- **Trade-off:**
  Slightly higher operational overhead in container orchestration (running two FastMCP server instances).

---

### Decision 4: Dry-Run Validation & Explicit Confirmation Gate

- **Options Considered:**
  1. *Immediate single-turn submission:* Commit the record to the database as soon as the assistant gathers the parameters.
  2. *Two-stage validation & confirmation gate (Chosen):* Provide `validate_application` (dry-run returning structured errors or a masked preview) and require `user_confirmed=True` in `submit_application`.
- **Rationale for Choice:**
  Elderly citizens and intermediaries need an opportunity to review their details before commitment, especially since the portal enforces that only one active application can exist per mobile number. The two-stage gate prevents accidental duplicate attempts and gives immediate remediation guidance on formatting mistakes.

---

### The Decision We Would Make Differently With More Time

#### Full Native REST/JSON API in Flask Core
Currently, because legacy portal endpoints were written for HTML form submissions, the MCP server invokes Python database routines directly (`db.py` / `portal_client.py`). With additional development time, we would refactor the Flask core to expose first-class JSON endpoints authenticated via Bearer tokens for all actions, completely abstracting the database layer behind clean HTTP microservices.
