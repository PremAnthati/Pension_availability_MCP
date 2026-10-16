FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: citizen server. Override with CMD in docker-compose.
CMD ["python", "citizen_server.py"]
