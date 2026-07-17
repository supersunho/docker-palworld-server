# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security
- Removed hardcoded 'admin123' default admin password from PalworldSettings dataclass
- RCON password now passed via stdin instead of command-line argument to prevent process listing exposure

### Fixed
- Supervisor config: replaced bash-style `${VAR:-default}` syntax with supervisor-compatible `%(ENV_VAR)s` interpolation
- Supervisor config: removed event listener referencing uninstalled `supervisor_stdout`
- Supervisor config: replaced inline Python script in metrics-exporter with proper module invocation
- Corrected `Optional` type annotations across backup, settings, notifications, and message loader modules

### Changed
- Updated .gitignore to cover `__pycache__/`, `.mypy_cache/`, and `.python-version`

## [1.1.3] - 2026-07-12

### Added
- Background periodic update check via CHECK_VERSION_UPDATE setting
- Discord notification event for version updates (DISCORD_EVENT_UPDATE)
- Server management settings (ENABLE_BUILDING_PLAYER_UID_DISPLAY, SHOW_JOIN_LEFT_MESSAGE)
- Stat allocation configuration (ALLOW_ENHANCE_STAT_ATTACK/HEALTH/STAMINA/WEIGHT/WORK_SPEED)
- PvP map display settings, voice chat settings, PvP additional drops
- Respawn penalties configuration
- Guild rejoin cooldown setting
- Item corruption multiplier, monster farm action speed rate
- Player data storage update check interval
- Auto-transfer guild master settings
- Max guilds per frame, building name display cache TTL
- Engine performance configuration (LAN/Net tick rate, frame rate bounds, smooth frame rate)

### Changed
- Refactored imports to use direct module references instead of relative imports
- Unwired container instances converted to use dependency injection through ServiceContainer
- LifecycleManager now properly creates ProcessManager when not injected
- HealthManager uses LifecycleManager for process state checks
- Renamed AUTO_UPDATE to CHECK_VERSION_UPDATE (notification-only, no auto-restart)
- Persist entire palworld server directory across container restarts

### Fixed
- DiscordNotifier attribute error on idle restart notification
- Config generation failures handled gracefully with logging
- SteamCMD binary corruption detection during warm-up self-update
- ServerManager SIGHUP forwarding fixed for hot-reload
- API facade startup order and lifecycle references

### Security
- Removed insecure deployment defaults from Helm, Compose, and documentation
- Hardened CI/CD workflow inputs

### Infrastructure
- Multi-stage Docker build for reduced image size
- ARM64 FEX emulation support
- Supervisor-based process management
- Prometheus metrics support with aiohttp exporter integration

## [1.1.2] - 2026-07-08

### Added
- Idle restart feature with Discord notification
- Monitoring system with configurable modes (logs, metrics, both)

### Fixed
- Process lifecycle edge cases
- RCON connection handling

## [1.1.1] - 2026-07-01

### Added
- Discord notification system with multi-language support
- Backup system with retention policies
- Enhanced logging with structlog

### Changed
- Configuration system refactored to use env var substitution in default.yaml
- Entrypoint script rewritten for better error handling

## [1.1.0] - 2026-06-15

### Added
- REST API health check with authentication
- Prometheus metrics exporter
- Hot-reload configuration support

### Fixed
- Process management race conditions
- Port validation logic

## [1.0.0] - 2026-06-01

### Added
- Initial Palworld dedicated server management system
- SteamCMD integration for server installation and updates
- RCON client for server command execution
- Basic configuration management
- Docker containerization with supervisor
- ARM64 support via FEX emulation
