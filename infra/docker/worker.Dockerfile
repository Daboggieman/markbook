# Worker image — same codebase, different entrypoint (spec §12).
FROM python:3.12-slim AS base

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/pyproject.toml /app/pyproject.toml
COPY apps/api/src /app/src
COPY apps/worker/worker.py /app/worker.py

WORKDIR /app

RUN pip install --no-cache-dir .

WORKDIR /app

CMD ["python", "worker.py"]