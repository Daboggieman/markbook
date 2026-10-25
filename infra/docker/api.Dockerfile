# Markbook API image — one image, entrypoints api and worker (spec §15).
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build deps for psycopg/argon2 if wheels are unavailable for the platform.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/pyproject.toml /app/pyproject.toml
COPY apps/api/src /app/src

RUN pip install --no-cache-dir .

WORKDIR /app/src

EXPOSE 8000

# Migrations run as a release step (compose / CI), never at container start.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "/app/src"]