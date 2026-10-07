# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# Kayan ERP API image: slim runtime, non-root user, healthcheck on /health.
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt

# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    ENVIRONMENT=production \
    STORAGE_DIR=/app/storage \
    BACKUP_DIR=/app/backups

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system kayan \
    && useradd --system --gid kayan --home /app kayan

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=kayan:kayan alembic.ini ./
COPY --chown=kayan:kayan alembic ./alembic
COPY --chown=kayan:kayan app ./app

RUN mkdir -p /app/storage /app/backups && chown -R kayan:kayan /app

USER kayan
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
