FROM python:3.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN python -m venv "$VIRTUAL_ENV"
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends cron \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 sewasetu \
    && useradd --system --uid 10001 --gid sewasetu --create-home --home-dir /home/sewasetu sewasetu \
    && mkdir -p /var/sewasetu/uploads /var/log/sewasetu \
    && chown -R sewasetu:sewasetu /var/sewasetu /var/log/sewasetu

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=sewasetu:sewasetu . .
RUN crontab /app/deploy/crontab

USER sewasetu
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=2)"

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "30", "app:app"]
