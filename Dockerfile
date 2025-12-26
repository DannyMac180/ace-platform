# Production Dockerfile for ACE Platform
# Multi-stage build for optimized image size

# ============================================================================
# Stage 1: Base image with Python and system dependencies
# ============================================================================
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Required for psycopg2
    libpq-dev \
    # Required for building Python packages
    gcc \
    # Useful for debugging
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd --gid 1000 ace && \
    useradd --uid 1000 --gid ace --shell /bin/bash --create-home ace

WORKDIR /app

# ============================================================================
# Stage 2: Builder - Install dependencies
# ============================================================================
FROM base as builder

# Copy only dependency files first for better caching
COPY pyproject.toml ./

# Install dependencies
RUN pip install --no-cache-dir .

# ============================================================================
# Stage 3: Production image
# ============================================================================
FROM base as production

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=ace:ace ace_platform ./ace_platform
COPY --chown=ace:ace ace_core ./ace_core
COPY --chown=ace:ace pyproject.toml ./

# Install the package in development mode for imports to work
RUN pip install --no-cache-dir -e .

# Create directories for logs and data
RUN mkdir -p /app/logs /app/data && chown -R ace:ace /app

# Switch to non-root user
USER ace

# Default environment variables
ENV ENVIRONMENT=production \
    DEBUG=false \
    API_HOST=0.0.0.0 \
    API_PORT=8000 \
    MCP_SERVER_HOST=0.0.0.0 \
    MCP_SERVER_PORT=8001

# Health check for API server
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${API_PORT}/health || exit 1

# Expose ports
EXPOSE 8000 8001

# Default command runs the API server
CMD ["uvicorn", "ace_platform.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ============================================================================
# Stage 4: API server target
# ============================================================================
FROM production as api

CMD ["uvicorn", "ace_platform.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

# ============================================================================
# Stage 5: MCP server target
# ============================================================================
FROM production as mcp

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${MCP_SERVER_PORT}/health || exit 1

CMD ["python", "-m", "ace_platform.mcp.server"]

# ============================================================================
# Stage 6: Celery worker target
# ============================================================================
FROM production as worker

# Workers don't need health check endpoint
HEALTHCHECK NONE

CMD ["celery", "-A", "ace_platform.workers.celery_app", "worker", "--loglevel=info", "--concurrency=4"]

# ============================================================================
# Stage 7: Celery beat (scheduler) target
# ============================================================================
FROM production as beat

HEALTHCHECK NONE

CMD ["celery", "-A", "ace_platform.workers.celery_app", "beat", "--loglevel=info"]

# ============================================================================
# Stage 8: Migration runner target
# ============================================================================
FROM production as migrate

HEALTHCHECK NONE

CMD ["alembic", "upgrade", "head"]
