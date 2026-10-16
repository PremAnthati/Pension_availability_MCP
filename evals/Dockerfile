FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir flask==2.2.5 psycopg2-binary==2.9.9 requests==2.28.2 gunicorn==20.1.0

# Copy application directories
COPY app/ /app/app/
COPY mcp/ /app/mcp/
COPY personas/ /app/personas/
COPY evals/ /app/evals/

WORKDIR /app/evals

EXPOSE 8003

CMD ["python", "dashboard_app.py"]
