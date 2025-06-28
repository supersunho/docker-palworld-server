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
ENV DEBIAN_FRONTEND=noninteractive 

WORKDIR /app

# Install build dependencies
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \ 
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update -qq >/dev/null 2>&1 && apt-get install -y --no-install-recommends \
    build-essential \
    curl -qq >/dev/null 2>&1

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

ENV DEBIAN_FRONTEND=noninteractive 

# Install runtime dependencies
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \ 
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    sudo apt-get update -qq >/dev/null 2>&1 && sudo apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-venv \
    python-is-python3 \
    ca-certificates \
    procps \
    htop \
    curl \
    wget \
    tar \
    gzip \
    cron \
    supervisor -qq >/dev/null 2>&1 

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
    BACKUP_RETENTION_DAYS=7  

RUN sudo useradd -m -s /bin/bash palworld && \
    sudo usermod -aG sudo palworld && \
    echo "palworld ALL=(ALL) NOPASSWD: ALL" >> sudo /etc/sudoers && \
    echo "✅ palworld user created with sudo privileges"

# Create application directory structure
RUN sudo mkdir -p \
    /home/palworld/app \
    /home/palworld/palworld_server \
    /home/palworld/backups \
    /home/palworld/logs/palworld \
    /etc/supervisor/conf.d

# Copy Python virtual environment from builder stage
COPY --from=python-deps /opt/venv /opt/venv

# Copy additional configuration files
COPY --chown=palworld:palworld docker/supervisor/ /etc/supervisor/conf.d/
COPY --chown=palworld:palworld docker/entrypoint.sh /entrypoint.sh
COPY --chmod=755 scripts/healthcheck.py /usr/local/bin/healthcheck

# Copy application files from builder stage
COPY --from=app-builder --chown=palworld:palworld /app /home/palworld/app

# Set proper permissions
RUN sudo chown -R palworld:palworld \
    /home/palworld && \
    sudo chmod +x /entrypoint.sh

# Expose ports
EXPOSE ${SERVER_PORT}/udp \
       27015/udp \
       ${REST_API_PORT}/tcp \
       ${DASHBOARD_PORT}/tcp

# Health check configuration
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=5m \
    CMD /usr/local/bin/healthcheck || exit 1

# Switch to application user
USER palworld

# Set working directory
WORKDIR /home/palworld

# Entry point
ENTRYPOINT ["/entrypoint.sh"]
CMD ["--start-server"]
