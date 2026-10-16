FROM python:3.12-slim AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 VIRTUAL_ENV=/opt/venv PATH="/opt/venv/bin:$PATH"
RUN python -m venv "$VIRTUAL_ENV"
WORKDIR /build
COPY mcp/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 VIRTUAL_ENV=/opt/venv PATH="/opt/venv/bin:$PATH"
RUN groupadd --system --gid 10001 mcp && useradd --system --uid 10001 --gid mcp mcp
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=mcp:mcp mcp/ /app/
COPY --chown=mcp:mcp app/config /app/config
COPY --chown=mcp:mcp app/core_rules.py /app/../app/core_rules.py
USER mcp
EXPOSE 8001 8002
CMD ["python", "citizen_server.py"]
