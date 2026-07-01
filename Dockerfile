FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts/start-api.sh ./scripts/start-api.sh

RUN pip install --upgrade pip && \
    pip install ".[dev]" && \
    chmod +x ./scripts/start-api.sh

EXPOSE 8000

CMD ["./scripts/start-api.sh"]
