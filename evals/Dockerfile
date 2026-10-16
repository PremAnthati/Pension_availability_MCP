FROM python:3.12-slim AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 VIRTUAL_ENV=/opt/venv PATH="/opt/venv/bin:$PATH"
RUN python -m venv "$VIRTUAL_ENV"
WORKDIR /build
RUN pip install --no-cache-dir flask==2.2.5 psycopg2-binary==2.9.9 requests==2.28.2 gunicorn==20.1.0

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 VIRTUAL_ENV=/opt/venv PATH="/opt/venv/bin:$PATH"
RUN groupadd --system --gid 10001 eval && useradd --system --uid 10001 --gid eval eval
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=eval:eval app/ /app/app/
COPY --chown=eval:eval mcp/ /app/mcp/
COPY --chown=eval:eval personas/ /app/personas/
COPY --chown=eval:eval evals/ /app/evals/
USER eval
WORKDIR /app/evals
EXPOSE 8003
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8003/eval-dashboard', timeout=2)"
CMD ["python", "dashboard_app.py"]
