# 🎮 Palworld Dedicated Server For ARM64

**🚀 Production-ready ARM64 optimized Palworld server with FEX + SteamCMD integration**

## 🌟 What Makes This Special?

### 🔧 **ARM64-Optimized Palworld Server**

- **Revolutionary FEX Integration**: 3-5x faster than QEMU on ARM64
- **Apple Silicon Ready**: M1/M2/M3 Macs with native performance
- **Raspberry Pi Support**: Perfect for home servers and edge computing
- **AWS Graviton Optimized**: Cloud-native ARM64 deployment

### 🤖 **Intelligent Auto-Management**

- **🔄 Smart Idle Restart**: Automatically restart when no players for configurable time
- **📊 Advanced Health Monitoring**: CPU, memory, disk, and API health checks with auto-recovery
- **💾 Enterprise Backup System**: Daily/weekly/monthly rotation with intelligent cleanup
- **🎯 Zero-Downtime Updates**: SteamCMD integration with graceful server management

### 🌍 **Multi-Language Discord Integration**

- **Real-time Notifications**: Player join/leave, server events, backup completion
- **3 Languages Supported**: Korean, English, Japanese
- **Smart Event Filtering**: Configurable notification preferences
- **Rich Embeds**: Beautiful Discord messages with server status

## 🚀 Quick Start

### **🐳 One-Command Deploy**

```bash
docker run -d \
  --name palworld-server \
  -p 8211:8211/udp \
  -p 127.0.0.1:8212:8212/tcp \
  -p 127.0.0.1:25575:25575/tcp \
  -e ADMIN_PASSWORD=your-secure-password \
  -v palworld-data:/home/steam/palworld_server \
  -v palworld-backups:/home/steam/backups \
  supersunho/palworld-server:latest
```

> ⚠️ **Security**: REST API (8212) and RCON (25575) bind to `127.0.0.1` by default.
> To expose them externally, configure a VPN, firewall allowlist, or ingress authentication.

### **📋 Docker Compose (Recommended)**

Create the service-specific environment files before starting the stack:

```bash
cp .env.palworld.example .env.palworld
cp .env.grafana.example .env.grafana

# Set ADMIN_PASSWORD in .env.palworld.
# Set GF_SECURITY_ADMIN_PASSWORD in .env.grafana.
bash scripts/validate_env_files.sh .env.palworld .env.grafana
docker compose --env-file .env.palworld up -d
```

`.env.palworld` contains the Palworld configuration; `.env.grafana` contains
only Grafana's native `GF_*` variables.

```yaml
version: "3.8"
services:
    palworld-server:
        image: supersunho/palworld-server:latest
        container_name: palworld-server
        restart: unless-stopped
        ports:
            - "8211:8211/udp" # Game Server
            - "127.0.0.1:8212:8212/tcp" # REST API (localhost only)
            - "127.0.0.1:25575:25575/tcp" # RCON (localhost only)
        env_file:
            - .env.palworld
        volumes:
            - palworld-data:/home/steam/palworld_server
            - palworld-backups:/home/steam/backups
            - palworld-logs:/home/steam/logs

volumes:
    palworld-data:
    palworld-backups:
    palworld-logs:
```

## ⚙️ Configuration

### **🔧 Essential Environment Variables**

| Variable              | Default             | Description                          |
| :-------------------- | :------------------ | :----------------------------------- |
| `SERVER_NAME`         | `"Palworld Server"` | 🏷️ Server display name               |
| `SERVER_PASSWORD`     | `""`                | 🔒 Server join password              |
| `ADMIN_PASSWORD`      | _(required)_        | 👑 Admin/RCON password (no default)  |
| `MAX_PLAYERS`         | `32`                | 👥 Maximum player count (1-32)       |
| `BACKUP_ENABLED`      | `true`              | 💾 Enable automatic backups          |
| `DISCORD_WEBHOOK_URL` | `""`                | 💬 Discord webhook for notifications |
| `LANGUAGE`            | `ko`                | 🌍 Language (`ko`/`en`/`ja`)         |

### **⏰ NEW: Idle Restart Feature**

| Variable                     | Default | Description                               |
| :--------------------------- | :------ | :---------------------------------------- |
| `IDLE_RESTART_ENABLED`       | `true`  | 🔄 Enable auto-restart when no players    |
| `IDLE_RESTART_MINUTES`       | `30`    | ⏱️ Minutes to wait before restart         |
| `DISCORD_EVENT_IDLE_RESTART` | `true`  | 📣 Discord notification for idle restarts |

### **🎮 Game Settings (150+ configurable options)**

| Variable              | Default | Description                  |
| :-------------------- | :------ | :--------------------------- |
| `DIFFICULTY`          | `None`  | 🎯 Game difficulty           |
| `IS_PVP`              | `false` | ⚔️ Enable PvP mode           |
| `DAY_TIME_SPEED_RATE` | `1.0`   | ☀️ Day time speed multiplier |
| `EXP_RATE`            | `1.0`   | 📈 Experience gain rate      |
| `PAL_CAPTURE_RATE`    | `1.0`   | 🎯 Pal capture difficulty    |

[📄 **Complete Environment Variables List**](https://github.com/supersunho/docker-palworld-server/blob/main/.env.palworld.example)

## 🎯 ARM64 Performance Revolution

### **Why FEX Matters**

Traditional ARM64 emulation (QEMU) is slow and resource-heavy. Our FEX integration changes everything:

| Platform      | Boot Time  | Memory Usage | CPU Usage |
| :------------ | :--------- | :----------- | :-------- |
| ARM64 + FEX   | ~2 minutes | ~1.2GB       | ~15%      |
| x86_64 Native | ~2 minutes | ~1.0GB       | ~12%      |
| ARM64 + QEMU  | ~8 minutes | ~2.1GB       | ~45%      |

### **Optimized FEX Configuration**

```bash
# Automatically applied in our container
FEX_ENABLE_JIT_CACHE=1
FEX_JIT_CACHE_SIZE=1024
FEX_ENABLE_LAZY_MEMORY_DELETION=1
FEX_ENABLE_STATIC_REGISTER_ALLOCATION=1
```

## 📊 Advanced Features

### **🔄 Smart Idle Management**

```bash
# Automatically restart server when empty
IDLE_RESTART_ENABLED=true
IDLE_RESTART_MINUTES=30

# Discord notification in your language
🇺🇸 "No players for 30 minutes. Restarting server (My Server)."
🇰🇷 "30분 동안 접속자가 없어 서버(My Server)를 재시작합니다."
🇯🇵 "30分間プレイヤーがいなかったため、サーバー(My Server)を再起動します。"
```

### **💾 Enterprise Backup System**

```yaml
backup:
    enabled: true
    interval_seconds: 3600 # Hourly backups
    retention_days: 7 # Keep daily for 7 days
    retention_weeks: 4 # Keep weekly for 4 weeks
    retention_months: 6 # Keep monthly for 6 months
    compress: true # Gzip compression
    max_backups: 100 # Total backup limit
```

### **📡 REST API \& RCON**

```bash
# REST API endpoints
curl http://localhost:8212/v1/api/info
curl http://localhost:8212/v1/api/players
curl http://localhost:8212/v1/api/settings

# RCON commands
rcon-cli --host localhost --port 25575 --password ${ADMIN_PASSWORD} ShowPlayers
rcon-cli --host localhost --port 25575 --password ${ADMIN_PASSWORD} "Broadcast Hello!"
```

### **🩺 Health Monitoring**

```bash
# Built-in health check
docker exec palworld-server python /app/scripts/healthcheck.py

# Automatic recovery on failures
# CPU > 90%, Memory > 95%, API timeouts = auto-restart
```

## 🛠️ Advanced Usage

### **Multi-Arch Build Commands**

```bash
# Clone repository
git clone https://github.com/supersunho/docker-palworld-server.git
cd docker-palworld-server

# Build for your platform
docker build -t palworld-server .

# Build
docker buildx build --platform linux/arm64 -t palworld-server .
```

### **Custom Configuration File**

```bash
# Mount your own configuration
docker run -d \
  -v ./my-config.yaml:/app/config/default.yaml \
  -v palworld-data:/home/steam/palworld_server \
  supersunho/docker-palworld-server:latest
```

### **Development Mode**

```bash
# Run with development tools
docker run -it --rm \
  -v $(pwd):/app \
  -p 8211:8211/udp \
  supersunho/palworld-server:latest bash
```

## 🌍 Multi-Language Discord Notifications

### **Supported Languages**

- 🇰🇷 **Korean** (`ko`) - 한국어 알림
- 🇺🇸 **English** (`en`) - English notifications
- 🇯🇵 **Japanese** (`ja`) - 日本語通知

### **Example Notifications**

```yaml
Player Join:
🇺🇸 "Player joined: Steve (5 players online)"
🇰🇷 "플레이어 참가: Steve (현재 5명)"
🇯🇵 "プレイヤー参加: Steve (現在5人)"

Server Restart:
🇺🇸 "Server restarted due to idle timeout"
🇰🇷 "무접속으로 인한 서버 재시작"
🇯🇵 "アイドルタイムアウトによるサーバー再起動"
```

## 📈 Resource Requirements \& Scaling

### **Recommended Specifications**

| Players | CPU Cores | RAM | Storage | Bandwidth |
| :------ | :-------- | :-- | :------ | :-------- |
| 1-8     | 2 cores   | 2GB | 10GB    | 5 Mbps    |
| 9-16    | 4 cores   | 4GB | 15GB    | 10 Mbps   |
| 17-24   | 6 cores   | 6GB | 20GB    | 15 Mbps   |
| 25-32   | 8 cores   | 8GB | 25GB    | 20 Mbps   |

### **Cloud Provider Recommendations**

#### **ARM64 Cloud Options** 💚

- **AWS**: Graviton3/4 instances (c7g, m7g series)
- **Oracle Cloud**: Ampere A1 (4 cores, 24GB RAM - Always Free!)
- **Hetzner**: CAX series ARM64 VPS
- **Scaleway**: ARM64 instances

## 🤝 Community \& Support

### **🔗 Links**

- 📦 **Docker Hub**: [supersunho/palworld-server](https://hub.docker.com/r/supersunho/palworld-server)
- 📂 **GitHub**: [supersunho/docker-palworld-server](https://github.com/supersunho/docker-palworld-server)
- 🐛 **Issues**: [Report Issues](https://github.com/supersunho/docker-palworld-server/issues)
- 💬 **Discussions**: [Community Discussions](https://github.com/supersunho/docker-palworld-server/discussions)

## 📜 License \& Acknowledgments

**MIT License** - Free for personal and commercial use.

<div align="center">

### **⭐ Love this project? Give it a star! ⭐**

</div>
