# 3-Minute Loom Presentation Script: Sewa Setu Agent Access

**Presenter:** Bharat Digital Fellow  
**Target Audience:** Department Director & Technical Review Panel  
**Time Limit:** 3 minutes (180 seconds)  
**Format:** Face & Screen Recording  

---

### [00:00 - 00:25] The Problem & Field Reality (25 seconds)
*(Face on camera + quick transition to Sewa Setu portal home screen)*

"Good afternoon, Director. Last month in Sonari block, an elderly grandmother and her grandson tried to apply for her ₹250 monthly pension using an AI assistant on the bus. It failed completely—giving outdated rules and lacking any way to talk to our portal. 

For elderly citizens, shared phones, and busy CSC kiosks, standard web forms can be intimidating, but AI assistants had no official, trusted channel. 

As a Bharat Digital Fellow, I built **Sewa Setu Agent Access**: two Model Context Protocol (MCP) servers over streamable HTTP that turn AI assistants into an official, validated channel where our portal remains the single system of record."

---

### [00:25 - 01:10] Citizen Demo & The Core Architecture Decisions (45 seconds)
*(Screen: Claude Code / MCP client interacting with `/mcp/citizen`)*

"Let’s look at the citizen side. 

Here, Raju is applying for his grandmother, Champa Devi, from Sonari. 
Notice three deliberate design decisions:
1. **Zero-Trust Identity:** The assistant never asks for her phone number. It is securely extracted from the authenticated OAuth 2.1 token (`sub: citizen:mobile`). Even on a shared phone or kiosk, one user cannot query or touch another’s application.
2. **Server-Side Validation Parity:** The AI assistant uses `validate_application` to dry-run the data against our portal's exact statutory rules—age 60+, valid block, IFSC, and bank format. No hallucinated rules.
3. **Explicit Confirmation:** The assistant presents a masked summary and will not submit without explicit applicant confirmation. 

Once submitted, application `SSP26...` is immediately created in PostgreSQL in `PENDING` status, with Raju's helper details logged in the audit trail."

---

### [01:10 - 01:50] Officer Demo & Block Governance (40 seconds)
*(Screen: Switching to `/mcp/officer` and showing the portal admin view)*

"Now, the block officer's assistant. This is an entirely different design.

The officer's assistant connects to `/mcp/officer`. A citizen’s assistant cannot even see these tools.
1. **Block Scoping:** Officer Sonari only sees applications within Sonari block. Attempting to touch a case in Rajapara throws a hard `FORBIDDEN_BLOCK_SCOPE` error.
2. **SLA Urgency FIFO:** The queue is sorted by days remaining before the 15-day statutory deemed-approval deadline, flagging urgent cases first.
3. **No Blind Approvals:** The officer must review details and provide a meaningful, non-boilerplate reason. 

I’ll approve Champa Devi’s case with: *'Aadhaar age verified, SBI account active.'* 
Instantly, we see the portal's audit log update with the officer’s name, timestamp, and reason."

---

### [01:50 - 02:35] Personas, Evals & What We Learned (45 seconds)
*(Screen: `/eval-dashboard` showing the 8 personas and test telemetry)*

"To make sure this works in the field—not just in a tech demo—we created 8 realistic citizen personas and 2 officer profiles on our live `/eval-dashboard`:
- Champa Devi (widow with grandson)
- An illiterate senior applying through her remote daughter
- A CSC operator processing multiple applicants on a shared terminal
- A boundary case aged 59 years and 11 months
- A duplicate applicant, an out-of-scope block resident, and an adversary attempting prompt injection.

**What the evals caught:**  
During initial testing, our duplicate check allowed a second submission if a user had an existing approved pension from a previous year. The evaluation assertions caught this immediately. We tightened the query to block any mobile with status in `PENDING`, `APPROVED`, or `DEEMED_APPROVED`, exactly matching the physical counter rules.

Our automated suite runs 22 assertions across parity, boundary, security, cross-visibility, and deemed approval—with a **100% pass rate**."

---

### [02:35 - 03:00] Conclusion & What I Would Do Differently (25 seconds)
*(Face on camera + screen showing repository)*

"With more time, I would refactor the Flask portal to expose a first-class headless JSON REST API, decoupling the MCP server completely from direct database queries.

The code, Docker deployment, and full evaluation suite are live in our private repository `sewasetu-assistant`. 

Thank you, Director. The counter is now open to every citizen’s assistant."

