# syntax=docker/dockerfile:1
# Palworld Dedicated Server with FEX emulation for ARM64
# Multi-stage build optimized for production deployment

# Stage 1: Python dependencies builder
FROM python:3.12-slim AS python-deps

# Set Python environment variables for optimization
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY requirements.txt requirements-dev.txt ./

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Stage 2: Application builder
FROM python-deps AS app-builder

WORKDIR /app

# Copy application source code
COPY src/ ./src/
COPY config/ ./config/
COPY templates/ ./templates/
COPY scripts/ ./scripts/

# Compile Python bytecode for faster startup
RUN /opt/venv/bin/python -m compileall src/ && \
    find src/ -name "*.py" -exec /opt/venv/bin/python -m py_compile {} \;

# Validate configuration files
RUN /opt/venv/bin/python -c "import yaml; yaml.safe_load(open('config/default.yaml'))"

# Remove unnecessary files for production
RUN find . -name "*.pyc" -delete && \
    find . -name "__pycache__" -type d -exec rm -rf {} + || true && \
    rm -rf .git .pytest_cache tests/ docs/ *.md requirements-dev.txt

# Stage 3: Final runtime image
FROM supersunho/steamcmd-arm64:latest AS runtime

# Metadata labels
LABEL maintainer="supersunho" \
      version="1.0.0" \
      description="Palworld Dedicated Server with FEX emulation for ARM64" \
      architecture="arm64" \
      base-image="supersunho/steamcmd-arm64:latest"

# Install runtime dependencies
RUN sudo apt-get update && sudo apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-venv \
    ca-certificates \
    procps \
    htop \
    curl \
    wget \
    tar \
    gzip \
    cron \
    supervisor \
    && sudo rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/src" \
    PATH="/opt/venv/bin:$PATH" \
    \
    # Default server configuration
    SERVER_NAME="Palworld Server" \
    ADMIN_PASSWORD="admin123" \
    SERVER_PASSWORD="" \
    MAX_PLAYERS=32 \
    SERVER_PORT=8211 \
    REST_API_PORT=8212 \
    DASHBOARD_PORT=8080 \
    \
    # Feature toggles
    BACKUP_ENABLED=true \
    AUTO_UPDATE=true \
    REST_API_ENABLED=true \
    MONITORING_MODE=both \
    DISCORD_ENABLED=false \
    \
    # Operational settings
    LOG_LEVEL=INFO \
    BACKUP_INTERVAL=3600 \
    BACKUP_RETENTION_DAYS=7 \
    \
    # Docker-specific settings
    PUID=1000 \
    PGID=1000

# Create application user and group
RUN sudo groupadd --gid ${PGID} palworld && \
    sudo useradd --uid ${PUID} --gid palworld --shell /bin/bash --create-home palworld

# Create application directory structure
RUN sudo mkdir -p \
    /app \
    /palworld_server \
    /backups \
    /var/log/palworld \
    /etc/supervisor/conf.d

# Copy Python virtual environment from builder stage
COPY --from=python-deps /opt/venv /opt/venv

# Copy application files from builder stage
COPY --from=app-builder --chown=palworld:palworld /app /app

# Copy additional configuration files
COPY --chown=palworld:palworld docker/supervisor/ /etc/supervisor/conf.d/
COPY --chown=palworld:palworld docker/entrypoint.sh /entrypoint.sh
COPY --chmod=755 scripts/healthcheck.py /usr/local/bin/healthcheck

# Set proper permissions
RUN sudo chown -R palworld:palworld \
    /app \
    /palworld_server \
    /backups \
    /var/log/palworld && \
    chmod +x /entrypoint.sh

# Create volume mount points
VOLUME ["/palworld_server/Pal/Saved", "/backups", "/var/log/palworld"]

# Expose ports
EXPOSE ${SERVER_PORT}/udp \
       27015/udp \
       ${REST_API_PORT}/tcp \
       ${DASHBOARD_PORT}/tcp

# Health check configuration
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=5m \
    CMD /usr/local/bin/healthcheck || exit 1

# Switch to application user
USER palworld:palworld

# Set working directory
WORKDIR /app

# Entry point
ENTRYPOINT ["/entrypoint.sh"]
CMD ["--start-server"]
