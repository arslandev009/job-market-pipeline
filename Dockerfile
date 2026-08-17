# syntax=docker/dockerfile:1

FROM python:3.11-slim-bookworm AS base

# Playwright needs a handful of system libs to run headless Chromium.
# Installed here once so the layer caches across rebuilds of app code.
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=cache,target=/root/.cache/ms-playwright \
    pip install -r requirements.txt \
    && playwright install --with-deps chromium

COPY src/ ./src/
COPY config/ ./config/
COPY scripts/ ./scripts/
COPY migrations/ ./migrations/
COPY alembic.ini .

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# No CMD here on purpose — this image is used by multiple services
# (scraper, extractor, classifier, scorer, sheets-writer, scheduler)
# each with its own command, defined per-service in docker-compose.yml.