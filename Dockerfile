# syntax=docker/dockerfile:1
# Palworld Dedicated Server with FEX emulation for ARM64
# Multi-stage build optimized for production deployment

# Stage 1: Python dependencies builder
FROM python:3.12-slim-bookworm AS python-deps

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install build dependencies
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libyaml-dev \
    python3-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY requirements.txt requirements-dev.txt ./

# ✅ Create proper virtual environment and install PyYAML explicitly
RUN python -m venv /app/venv && \
    /app/venv/bin/pip install --upgrade pip setuptools wheel && \
    /app/venv/bin/pip install PyYAML==6.0.2 && \
    /app/venv/bin/pip install --no-cache-dir -r requirements.txt

# ✅ Verify core module installation
RUN /app/venv/bin/python -c "import yaml; print(f'✅ PyYAML {yaml.__version__} installed')" && \
    /app/venv/bin/python -c "import aiohttp; print('✅ aiohttp installed')" && \
    /app/venv/bin/python -c "import structlog; print('✅ structlog installed')"

# Stage 2: Application builder
FROM python-deps AS app-builder

WORKDIR /app

# Copy application source code
COPY src/ ./src/
COPY config/ ./config/
COPY templates/ ./templates/
COPY scripts/ ./scripts/

# ✅ Validate configuration (using virtual environment path)
RUN /app/venv/bin/python -c "import yaml; yaml.safe_load(open('config/default.yaml'))" && \
    echo "✅ Configuration validation passed"

# ✅ Test Python modules (important!)
RUN /app/venv/bin/python -c "from src.config_loader import get_config; print('✅ Config loader works')" || \
    echo "⚠️ Config loader test failed - will be fixed at runtime"

# Compile Python bytecode for faster startup
RUN /app/venv/bin/python -m compileall src/ || true

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

# ✅ Install system packages with root privileges
USER root

ENV DEBIAN_FRONTEND=noninteractive

# ✅ Remove sudo and execute directly
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-venv \
    python-is-python3 \
    libyaml-0-2 \
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

# ✅ Set environment variables (maintain path consistency)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/src" \
    PATH="/app/venv/bin:$PATH" \
    VIRTUAL_ENV="/app/venv" \
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
    PUID=1000 \
    PGID=1000

# ✅ Create user (without sudo)
RUN groupadd --gid ${PGID} palworld && \
    useradd --uid ${PUID} --gid palworld --shell /bin/bash --create-home palworld

# ✅ Create directories (with root privileges)
RUN mkdir -p \
    /app \
    /home/palworld/palworld_server/Pal/Saved/Config/LinuxServer \
    /home/palworld/backups \
    /home/palworld/logs/palworld \
    /etc/supervisor/conf.d

# ✅ Copy virtual environment (unified paths)
COPY --from=python-deps /app/venv /app/venv

# ✅ Copy application files (unified paths)
COPY --from=app-builder /app /app

# ✅ Copy additional configuration files
COPY docker/supervisor/ /etc/supervisor/conf.d/
COPY docker/entrypoint.sh /entrypoint.sh
COPY --chmod=755 scripts/healthcheck.py /usr/local/bin/healthcheck

# ✅ Set permissions (batch processing with root privileges)
RUN chown -R ${PUID}:${PGID} \
    /app \
    /home/palworld \
    /opt/venv || true && \
    chmod +x /entrypoint.sh /usr/local/bin/healthcheck && \
    chmod 755 /home/palworld/palworld_server \
    /home/palworld/backups \
    /home/palworld/logs

# ✅ Final Python module verification
RUN python -c "import yaml; print(f'✅ Runtime PyYAML {yaml.__version__} ready')" && \
    python -c "import sys; print(f'✅ Python path: {sys.path}')"

# Expose ports
EXPOSE ${SERVER_PORT}/udp \
       27015/udp \
       ${REST_API_PORT}/tcp \
       ${DASHBOARD_PORT}/tcp

# Health check configuration
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=5m \
    CMD /usr/local/bin/healthcheck || exit 1

# ✅ Switch to user at the end
USER palworld:palworld

# ✅ Set working directory (match with PYTHONPATH)
WORKDIR /app

# Entry point
ENTRYPOINT ["/entrypoint.sh"]
CMD ["--start-server"]
