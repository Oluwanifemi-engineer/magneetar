# ═══════════════════════════════════════════════════════════════════════════════
# MAGNEETAR SERVER — Dockerfile
# Multi-stage build for production
# ═══════════════════════════════════════════════════════════════════════════════

# ── Builder Stage ────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (including optional pg support)
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt \
    && pip install --no-cache-dir --user asyncpg 2>/dev/null || true

# ── Production Stage ─────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Accept version from build arg (fallback to 1.0.0)
ARG APP_VERSION=1.0.0

# Write VERSION file so main.py can read it at runtime
RUN echo "$APP_VERSION" > /VERSION

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY . .

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run with uvicorn in production mode
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--log-level", "info"]
