#!/usr/bin/env bash
set -e

echo "=== Starting Sewa Setu on Render ==="

# 1. Port configuration
export PORT="${PORT:-10000}"
echo "Configuring Nginx to listen on port: ${PORT}"

# 2. Public Base URL configuration
if [ -z "$PUBLIC_BASE_URL" ]; then
    if [ -n "$RENDER_EXTERNAL_URL" ]; then
        export PUBLIC_BASE_URL="$RENDER_EXTERNAL_URL"
    else
        export PUBLIC_BASE_URL="http://localhost:${PORT}"
    fi
fi
export PUBLIC_BASE_URL="${PUBLIC_BASE_URL%/}"
echo "Public Base URL set to: ${PUBLIC_BASE_URL}"

export CITIZEN_MCP_URL="${PUBLIC_BASE_URL}/mcp/citizen"
export OFFICER_MCP_URL="${PUBLIC_BASE_URL}/mcp/officer"
export PORTAL_ISSUER="${PUBLIC_BASE_URL}"
export PORTAL_URL="http://127.0.0.1:8000"
export SMS_GATEWAY_URL="http://127.0.0.1:8025"
export ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-sewasetu_admin_2026}"
export EVAL_PORT="8003"
export CITIZEN_MCP_PORT="8001"
export OFFICER_MCP_PORT="8002"

# 3. Database setup: External vs Local Embedded PostgreSQL
if [ -n "$DATABASE_URL" ]; then
    echo "External DATABASE_URL detected: connecting to remote PostgreSQL..."
    case "$DATABASE_URL" in
        postgres://*)
            export DATABASE_URL="postgresql://${DATABASE_URL#postgres://}"
            ;;
    esac
else
    echo "No external DATABASE_URL provided. Starting local PostgreSQL service..."
    service postgresql start || /etc/init.d/postgresql start
    
    until su - postgres -c "pg_isready" >/dev/null 2>&1; do
        sleep 1
    done
    
    su - postgres -c "psql -tc \"SELECT 1 FROM pg_roles WHERE rolname='sewasetu'\" | grep -q 1 || psql -c \"CREATE USER sewasetu WITH PASSWORD 'sewasetu123' SUPERUSER;\""
    su - postgres -c "psql -tc \"SELECT 1 FROM pg_database WHERE datname='sewasetu'\" | grep -q 1 || psql -c \"CREATE DATABASE sewasetu OWNER sewasetu;\""

    export DATABASE_URL="postgresql://sewasetu:sewasetu123@127.0.0.1:5432/sewasetu"
    export DB_HOST="127.0.0.1"
    export DB_PORT="5432"
    export DB_NAME="sewasetu"
    export DB_USER="sewasetu"
    export DB_PASS="sewasetu123"
fi

# 4. Initialize Database Schema and Seeds
echo "Checking database schema..."
python /app/init_db.py

# 5. Populate Eval Results if not present
if [ ! -f /app/evals/eval_results.json ]; then
    echo "Running comprehensive evaluations to seed dashboard..."
    python /app/evals/run_comprehensive_evals.py || true
fi

# 6. Run Deemed Approval Check Once on Startup
echo "Running statutory deemed approval check..."
python /app/app/scripts/deemed_approval.py || true

# 7. Substitute PORT in Nginx configuration
echo "Generating Nginx configuration..."
envsubst '${PORT}' < /etc/nginx/nginx.render.conf.template > /etc/nginx/nginx.conf

# 8. Start Supervisord to run all services
echo "Starting services via Supervisor..."
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf

