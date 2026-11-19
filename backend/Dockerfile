FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for psycopg2 + ortools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .
# Ensure package importable when run from /app/backend
ENV PYTHONPATH=/app/backend

EXPOSE 8000

# Generate dataset + seed on first run, then serve.
CMD ["sh", "-c", "python -m scripts.seed_db && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
