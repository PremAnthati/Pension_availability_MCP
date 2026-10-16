FROM python:3.11-slim AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 VIRTUAL_ENV=/opt/venv PATH="/opt/venv/bin:$PATH"
RUN python -m venv "$VIRTUAL_ENV" \
    && pip install --no-cache-dir Flask==2.2.5

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 VIRTUAL_ENV=/opt/venv PATH="/opt/venv/bin:$PATH"
RUN groupadd --system --gid 10001 smsgw && useradd --system --uid 10001 --gid smsgw smsgw
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=smsgw:smsgw app.py .
USER smsgw
EXPOSE 8025
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8025/', timeout=2)"
CMD ["python", "app.py"]
