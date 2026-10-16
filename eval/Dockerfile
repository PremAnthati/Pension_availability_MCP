FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Also install mcp deps so we can import db.py
COPY ../mcp/requirements.txt /tmp/mcp-reqs.txt
RUN pip install --no-cache-dir psycopg2-binary==2.9.9

COPY . /app/eval/
COPY ../mcp /app/mcp/
COPY ../app/config /app/config/

WORKDIR /app/eval
RUN mkdir -p results

EXPOSE 8003
CMD ["python", "dashboard_app.py"]
