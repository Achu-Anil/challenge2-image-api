# Multi-stage Dockerfile for Challenge 2 - Image Frames API
#
# Stage 1: Builder - Install dependencies
# Stage 2: Runtime - Copy app and run uvicorn
#
# Build: docker build -t aiq-depth-frames-api .
# Run: docker run -p 8000:8000 -v $(pwd)/data:/app/data aiq-depth-frames-api

# ============================================================================
# Stage 1: Builder - Install dependencies
# ============================================================================
FROM python:3.14-slim AS builder

LABEL maintainer="aiq-depth-frames-api"
LABEL description="Multi-stage build for FastAPI Image Frames API"

# Set working directory
WORKDIR /build

# Install system dependencies required for building Python packages
# - gcc, g++: C/C++ compilers for native extensions
# - libpq-dev: PostgreSQL development headers (if needed)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        && \
    rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Install Poetry and dependencies
RUN pip install --no-cache-dir poetry==1.7.1 && \
    poetry config virtualenvs.create false && \
    poetry install --only main --no-interaction --no-ansi

# ============================================================================
# Stage 2: Runtime - Lean production image
# ============================================================================
FROM python:3.14-slim AS runtime

LABEL maintainer="aiq-depth-frames-api"
LABEL description="Production image for FastAPI Image Frames API"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    # FastAPI/Uvicorn settings
    HOST=0.0.0.0 \
    PORT=8000 \
    WORKERS=1 \
    # Application settings
    LOG_LEVEL=info \
    DATABASE_URL=sqlite+aiosqlite:////app/data/frames.db \
    ADMIN_TOKEN=changeme-in-production

# Create non-root user for security
RUN groupadd -r appuser && \
    useradd -r -g appuser -u 1000 appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app

# Set working directory
WORKDIR /app

# Copy Python packages from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=appuser:appuser app/ ./app/
COPY --chown=appuser:appuser scripts/ ./scripts/

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()" || exit 1

# Default command: run uvicorn server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]

# Alternative commands (document in README):
# 
# Run ingestion CLI:
# docker run --rm -v $(pwd)/data:/app/data -v $(pwd)/sample.csv:/app/sample.csv \
#   aiq-depth-frames-api python -m app.cli.ingest /app/sample.csv
#
# Interactive shell:
# docker run --rm -it -v $(pwd)/data:/app/data aiq-depth-frames-api /bin/bash
#
# Run tests:
# docker run --rm aiq-depth-frames-api pytest tests/
