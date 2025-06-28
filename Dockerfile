# syntax=docker/dockerfile:1
# Palworld Dedicated Server with FEX emulation for ARM64
# Single-stage build for maximum stability

FROM supersunho/steamcmd-arm64:latest

# Metadata labels
LABEL maintainer="supersunho" \
      version="1.0.0" \
      description="Palworld Dedicated Server with FEX emulation for ARM64" \
      architecture="arm64" \
      base-image="supersunho/steamcmd-arm64:latest"

# Use root for system setup
USER root

ENV DEBIAN_FRONTEND=noninteractive

# Install all dependencies in one go
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    # Python runtime
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    python-is-python3 \
    pip \
    # Build tools (needed for PyYAML compilation)
    build-essential \
    libyaml-dev \
    # System packages
    ca-certificates \
    procps \
    htop \
    curl \
    wget \
    tar \
    gzip \
    cron \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/src" \
    PIP_NO_CACHE_DIR=1 \
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
    PUID=1001 \
    PGID=1001

# Create directories
RUN mkdir -p \
    /app \
    /home/steam/palworld_server/Pal/Saved/Config/LinuxServer \
    /home/steam/backups \
    /home/steam/logs/palworld \
    /etc/supervisor/conf.d

# Copy requirements and install Python packages DIRECTLY
WORKDIR /app
COPY requirements.txt requirements-dev.txt ./

# ✅ Install Python packages directly to system (no virtual environment!)
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

# ✅ Verify installation immediately
RUN python3 -c "import yaml; print(f'✅ PyYAML {yaml.__version__} installed')" && \
    python3 -c "import aiohttp; print('✅ aiohttp installed')" && \
    python3 -c "import structlog; print('✅ structlog installed')" && \
    python -c "import yaml; print('✅ python command works too')"

# Copy application files
COPY src/ ./src/
COPY config/ ./config/
COPY templates/ ./templates/
COPY scripts/ ./scripts/

# Copy configuration files
COPY docker/supervisor/ /etc/supervisor/conf.d/
COPY docker/entrypoint.sh /entrypoint.sh
COPY --chmod=755 scripts/healthcheck.py /usr/local/bin/healthcheck

# ✅ Test application modules
RUN python -c "from src.config_loader import get_config; print('✅ Config loader works')" && \
    python -c "import yaml; yaml.safe_load(open('config/default.yaml')); print('✅ Config validation passed')"

# Set permissions
RUN chown -R steam:steam \
    /app \
    /home/steam && \
    chmod +x /entrypoint.sh /usr/local/bin/healthcheck && \
    chmod 755 /home/steam/palworld_server \
    /home/steam/backups \
    /home/steam/logs

# Final verification
RUN echo "=== Final System Check ===" && \
    python --version && \
    python -c "import yaml, aiohttp, structlog; print('✅ All modules ready')" && \
    python -c "from src.config_loader import get_config; print('✅ Application ready')"

# Expose ports
EXPOSE ${SERVER_PORT}/udp \
       27015/udp \
       ${REST_API_PORT}/tcp \
       ${DASHBOARD_PORT}/tcp

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=5m \
    CMD /usr/local/bin/healthcheck || exit 1

# Switch to user
USER steam
WORKDIR /app

# Entry point
ENTRYPOINT ["/entrypoint.sh"]
CMD ["--start-server"]
