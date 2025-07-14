# syntax=docker/dockerfile:1
FROM supersunho/steamcmd-arm64:latest

LABEL maintainer="supersunho" \
      version="1.0.1" \
      description="Palworld Dedicated Server with FEX emulation for ARM64" \
      architecture="arm64" \
      base-image="supersunho/steamcmd-arm64:latest"

USER root
ENV DEBIAN_FRONTEND=noninteractive

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    python-is-python3 \
    pip \
    build-essential \
    libyaml-dev \
    ca-certificates \
    procps \
    htop \
    curl \
    wget \
    tar \
    gzip \
    cron \
    supervisor \
    jq \
    && rm -rf /var/lib/apt/lists/*

RUN DOWNLOAD_URL=$(curl -s https://api.github.com/repos/itzg/rcon-cli/releases/latest | \
                   jq -r '.assets[] | select(.name | contains("linux_arm64.tar.gz")) | .browser_download_url') && \
    \
    if [ -z "$DOWNLOAD_URL" ]; then \
        exit 1; \
    fi && \
    \
    curl -L "$DOWNLOAD_URL" -o /tmp/rcon-cli.tar.gz && \
    cd /tmp && \
    tar -xzf rcon-cli.tar.gz && \
    \
    if [ -f rcon-cli ]; then \
        chmod +x rcon-cli && mv rcon-cli /usr/local/bin/rcon-cli; \
    else \
        find . -name "rcon-cli" -type f -exec chmod +x {} \; && \
        find . -name "rcon-cli" -type f -exec mv {} /usr/local/bin/rcon-cli \; ; \
    fi && \
    \
    rm -rf /tmp/rcon-cli* /tmp/LICENSE /tmp/README.md && \
    rcon-cli --help > /dev/null

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/src" \
    PIP_NO_CACHE_DIR=1 \
    \
    SERVER_NAME="Palworld Server" \
    ADMIN_PASSWORD="admin123" \
    SERVER_PASSWORD="" \
    MAX_PLAYERS=32 \
    SERVER_PORT=8211 \
    REST_API_PORT=8212 \
    RCON_PORT=25575 \
    \
    BACKUP_ENABLED=true \
    AUTO_UPDATE=true \
    REST_API_ENABLED=true \
    MONITORING_MODE=both \
    DISCORD_ENABLED=false \
    \
    LOG_LEVEL=INFO \
    BACKUP_INTERVAL=3600 \
    BACKUP_RETENTION_DAYS=7 \
    PUID=1002 \
    PGID=1002

RUN mkdir -p \
    /app \
    /home/steam/palworld_server/Pal/Saved/Config/LinuxServer \
    /home/steam/backups \
    /home/steam/logs/palworld \
    /etc/supervisor/conf.d

WORKDIR /app
COPY requirements.txt ./

RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

RUN python3 -c "import yaml, aiohttp, structlog"

COPY src/ ./src/
COPY config/ ./config/ 
COPY scripts/ ./scripts/
COPY docker/supervisor/ /etc/supervisor/conf.d/
COPY docker/entrypoint.sh /entrypoint.sh
COPY --chmod=755 scripts/healthcheck.py /usr/local/bin/healthcheck

RUN python -c "from src.config_loader import get_config; get_config()" && \
    python -c "import yaml; yaml.safe_load(open('config/default.yaml'))"

RUN chown -R steam:steam \
    /app \
    /home/steam && \
    chmod +x /entrypoint.sh /usr/local/bin/healthcheck && \
    chmod 755 /home/steam/palworld_server \
    /home/steam/backups \
    /home/steam/logs

EXPOSE ${SERVER_PORT}/udp \
       27015/udp \
       ${REST_API_PORT}/tcp \
       ${RCON_PORT}/tcp

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=5m \
    CMD /usr/local/bin/healthcheck || exit 1

USER steam
WORKDIR /home/steam

ENTRYPOINT ["/entrypoint.sh"]
CMD ["--start-server"]
