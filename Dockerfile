# ShuyuanCore - Production Dockerfile
# Multi-stage build for minimal image size

# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml .

# Install Python dependencies
RUN pip install --no-cache-dir --user -e .

# Stage 2: Runtime
FROM python:3.11-slim as runtime

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY src/ ./src/
COPY config/ ./config/
COPY migrations/ ./migrations/
COPY alembic.ini ./
COPY pyproject.toml ./

# Create non-root user
RUN useradd -m -u 1000 -s /bin/bash shuyuancore \
    && chown -R shuyuancore:shuyuancore /app

# Switch to non-root user
USER shuyuancore

# Expose port
EXPOSE 8005

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8005/health || exit 1

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV SHUYUANCORE_CONFIG=/app/config/default.yaml

# Entry point
CMD ["uvicorn", "src.gateway.api_server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8005"]
