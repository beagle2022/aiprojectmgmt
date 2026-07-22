# ── Stage 1: build dependencies ───────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install \
    anthropic \
    python-dotenv \
    requests


# ── Stage 2: production image ──────────────────────────────────────────────────
FROM python:3.12-slim AS production

LABEL maintainer="AI PM Copilot Team"
LABEL description="Agentic AI Project Management Copilot"
LABEL version="1.0.0"

# Non-root user for security
RUN groupadd -r copilot && useradd -r -g copilot -m -d /home/copilot copilot

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy entire project in one instruction — avoids "file not found" errors
# when optional files like pyproject.toml don't exist locally
COPY --chown=copilot:copilot . .

# Create data directory (mounted as volume at runtime)
RUN mkdir -p /app/data && chown -R copilot:copilot /app/data

# Remove any secrets that may have been accidentally copied
# (belt-and-suspenders alongside .dockerignore)
RUN rm -f /app/.env \
          /app/data/users.json \
          /app/data/sessions.json \
          /app/data/otp_store.json \
          /app/data/ltm.json \
          /app/data/.session

USER copilot

VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from copilot.config import Config; print('healthy')" || exit 1

CMD ["python", "login.py"]
