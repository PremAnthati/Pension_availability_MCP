# Sewa Setu — Old Age Pension Portal

Department of Social Welfare, Government of Purvanchal. Maintained in-house.

## Running

```
ADMIN_PASSWORD=pick-something docker compose up --build
```

- Portal: http://localhost:8000
- Status portal: http://localhost:8000/status (mobile number + password; the
  password is the applicant's date of birth as DDMMYYYY)
- Departmental login: http://localhost:8000/admin (user `admin`, password from
  `ADMIN_PASSWORD`)
- SMS gateway console (simulated telecom): http://localhost:8000/__gateway/ —
  OTPs and notifications appear here once "delivered" (1–4 s carrier latency).
  The gateway's inbox is also readable as JSON at
  `/__gateway/api/messages?to=<mobile>`.
- Database: Postgres, loaded from `seed/seed.sql` on first boot (~100k applications).

## Deploying on a server

Set `PUBLIC_BASE_URL` to the address people will use (for example
`https://sewasetu.example.in`). It is stamped into sign-in tokens and the discovery documents
described below, so a wrong value means other applications cannot find the sign-in page. Put
the portal behind HTTPS; some applications refuse to sign in over plain HTTP.

```
PUBLIC_BASE_URL=https://sewasetu.example.in ADMIN_PASSWORD=pick-something docker compose up --build -d
```

## Deploying on Render (Free Tier / Production)

This repository includes a production-ready Render blueprint (`render.yaml`) and unified container (`Dockerfile.render`).

### Option 1: Blueprint Deployment (Web Service + Render PostgreSQL)
1. Go to **[Render Dashboard](https://dashboard.render.com/)**.
2. Click **New +** → **Blueprint**.
3. Connect repository: `https://github.com/PremAnthati/Pension_availability_MCP.git`.
4. Render automatically configures:
   - **Web Service** (`sewasetu-pension`) running the Docker container.
   - **PostgreSQL Database** (`sewasetu-db`) with automatic connection string mapping.
5. Click **Apply**.
   The container automatically seeds the database, verifies migrations, runs initial evaluations, and routes all endpoints.

### Option 2: Single Web Service Deployment (Embedded PostgreSQL)
1. Click **New +** → **Web Service** → Connect this repository.
2. Select **Docker** environment (specify Dockerfile path: `Dockerfile.render`).
3. Under Environment Variables:
   - `PORT`: `10000` (or Render's default `$PORT`)
   - `ADMIN_PASSWORD`: Your chosen admin password
4. Click **Deploy**. The container automatically starts an embedded PostgreSQL instance and bootstraps the schema.

### Render Endpoints Once Deployed:
- **Main Portal**: `https://<your-service>.onrender.com/`
- **Citizen MCP Endpoint**: `https://<your-service>.onrender.com/mcp/citizen`
- **Officer MCP Endpoint**: `https://<your-service>.onrender.com/mcp/officer`
- **Eval Dashboard**: `https://<your-service>.onrender.com/eval-dashboard`
- **Department Admin**: `https://<your-service>.onrender.com/admin`
- **SMS Gateway Console**: `https://<your-service>.onrender.com/__gateway/`

## What the portal does

Citizen flow: mobile → OTP → personal details → address → bank details →
age-proof upload → preview and declaration → application number. A nightly
job (`scripts/deemed_approval.py`, via cron in the `scheduler` container)
deems approved any application still pending after the 15-day statutory SLA.

Rules enforced at submission, in `validate_application()` in `app/app.py`:
applicant is 60 years of age or above; required fields and an age-proof
document are present; the scheme window is open; and the mobile number holds
no other active (pending / approved / deemed-approved) application. A pending
application can be withdrawn from the status portal, after which the same
mobile may apply again.

Departmental users see a dashboard, list and filter applications, approve or
reject pending ones, and see the audit trail per application.

## Layout

```
app/          Flask application, templates, config, nightly job
seed/         seed.sql — production data snapshot
smsgw/        simulated SMS gateway
```

## Letting other applications act for a citizen or an officer

Sewa Setu is also an **OAuth 2.1 authorization server**. A third-party application can act
for a citizen (scope `citizen`) or for a block officer (scope `officer`) once that person
signs in on the portal and approves it. Citizens sign in by mobile and OTP, officers with the
departmental login. The application never handles the OTP or the password.

- Discovery: `/.well-known/oauth-authorization-server` (RFC 8414)
- Registration: `/oauth/register` (RFC 7591), or a client ID metadata document URL as `client_id`
- Authorization: `/oauth/authorize` (authorization code with PKCE S256; the `resource` the
  application asks for becomes the token's audience, RFC 8707)
- Tokens: `/oauth/token`. Access tokens are RS256 JWTs. A sign-in is a **session with an
  absolute end**: 2 hours for a citizen, 8 hours for an officer, counted from the consent.
  Access tokens are short (20 / 30 minutes) and refresh tokens rotate within the session but
  never extend it; after it ends the person signs in again. Portals are used on shared phones
  and kiosks.
- Sign-out: `/oauth/revoke` (RFC 7009). People can also end any sign-in from the status
  portal (**Connected applications**) or, for officers, the admin dashboard.
- Keys: `/.well-known/jwks.json`

A service that receives one of these tokens verifies it with the JWKS, checks `iss` is this
portal, checks `aud` is its own canonical URL, and reads `scope`, `role` and `sub`
(`citizen:<mobile>` or `officer:<username>`).

Long-lived **program tokens** for unattended use (role officer) are issued by an
administrator at `/admin/tokens`.

## AI Assistant Layer (MCP Servers & Eval Dashboard)

As designed for the Department of Social Welfare, Sewa Setu includes two Model Context Protocol (MCP) servers and an automated eval dashboard:

### Architecture
- **Citizen MCP (`/mcp/citizen`)**: Streamable HTTP endpoint for citizens / family members / CSC kiosk operators.
  - Auth: OAuth 2.1 token with `scope=citizen`, `sub=citizen:<mobile>`.
  - Enforces data isolation: mobile identity is extracted directly from the authenticated JWT `sub` claim.
  - Validates eligibility (age >= 60, block in allowed blocks, application window open).
  - Tools: `explain_scheme`, `check_eligibility`, `get_application_status`, `submit_application`, `withdraw_application`, `list_required_documents`, `get_acknowledgment_url`, `explain_status`.
- **Officer MCP (`/mcp/officer`)**: Streamable HTTP endpoint for block development officers.
  - Auth: OAuth 2.1 token with `scope=officer`, `sub=officer:<username>` (or admin-issued program token).
  - Tools: `get_dashboard_summary`, `list_pending_applications`, `get_application_detail`, `search_by_mobile`, `list_overdue_applications`, `approve_application`, `reject_application`.
  - Every decision requires confirmation, a recorded reason, and writes directly into the portal's `audit_log`.
- **Eval Dashboard (`/eval-dashboard`)**:
  - Live inspection dashboard showing 6 invented citizen personas across varied edge cases (happy path, underage, duplicate application, multi-turn fragmentary communication, scheme deadline queries, and withdraw + re-apply).
  - Verifies exact PostgreSQL database state post-conversation via automated SQL assertions.

### Running with Docker Compose
```bash
ADMIN_PASSWORD=pick-something docker compose up --build
```
- Citizen MCP: `http://localhost:8000/mcp/citizen`
- Officer MCP: `http://localhost:8000/mcp/officer`
- Eval Dashboard: `http://localhost:8000/eval-dashboard`
- Portal & Status: `http://localhost:8000`
