# Palworld Dedicated Server for ARM64

Production-ready Palworld dedicated server in Docker, with SteamCMD updates,
ARM64 support through FEX, automatic backups, health monitoring, idle restart,
and optional Discord notifications.

## What is included

- ARM64 images for Apple Silicon, Raspberry Pi-class systems, and ARM cloud
  instances.
- SteamCMD installation, validation, and update handling.
- Environment-variable configuration for all settings generated in
  `PalWorldSettings.ini` and the project's generated `Engine.ini` performance
  section.
- Automatic backups with retention by day, week, and month.
- Health checks, metrics, an optional dashboard, and configurable idle restart.
- Optional REST API, RCON, and localized Discord notifications in Korean,
  English, or Japanese.

## Quick start

### Docker Compose (recommended)

Create the environment file first:

```bash
cp .env.palworld.example .env.palworld

# Set ADMIN_PASSWORD in .env.palworld.
docker compose --env-file .env.palworld up -d
```

`.env.palworld` is consumed by the container. Do not commit this copied file;
it contains passwords, webhook URLs, and other private values.

The default Compose port bindings are:

| Service | Host binding | Protocol | Purpose |
|---|---:|---|---|
| Palworld | `8211` | UDP | Game traffic |
| Steam query | `27018` | UDP | Server browser/query traffic |
| REST API | `127.0.0.1:8212` | TCP | Palworld administration API |

RCON uses port `25575` inside the server container. The provided Compose file
does not publish it; publish it only to a trusted local interface or private
network when RCON access is needed. If you change `REST_API_PORT` or
`SERVER_PORT`, Compose uses the new values for its port mappings. The query
port is likewise controlled by `QUERY_PORT`.

The persistent directories created by Compose are:

| Host directory | Container path | Contents |
|---|---|---|
| `./palworld_data` | `/home/steam/palworld_server/Pal/Saved` | World and player data |
| `./palworld_backups` | `/home/steam/backups` | Automatic backups |
| `./palworld_logs` | `/home/steam/logs` | Server and manager logs |

### Docker run

For a server-only container, provide at least `ADMIN_PASSWORD` and a persistent
server volume:

```bash
docker run -d \
  --name palworld-server \
  --restart unless-stopped \
  -p 8211:8211/udp \
  -p 27018:27018/udp \
  -p 127.0.0.1:8212:8212/tcp \
  -e ADMIN_PASSWORD=replace-with-a-strong-password \
  -v palworld-data:/home/steam/palworld_server \
  -v palworld-backups:/home/steam/backups \
  supersunho/palworld-server:latest
```

The REST API and any published RCON port are administrative interfaces. Keep
them on localhost or a private network unless they are protected by a firewall,
VPN, or authenticated reverse proxy.

## Configuration

### The configuration workflow

1. Copy `.env.palworld.example` to `.env.palworld`.
2. Set a strong, non-empty `ADMIN_PASSWORD` and change any desired values.
3. Validate the files and start or recreate the container:

   ```bash
   bash scripts/validate_env_files.sh .env.palworld
   docker compose --env-file .env.palworld up -d --force-recreate
   ```

4. Confirm the generated files and logs after startup.

The manager reads `config/default.yaml`, substitutes environment variables, and
generates the active Palworld files at:

```text
/home/steam/palworld_server/Pal/Saved/Config/LinuxServer/PalWorldSettings.ini
/home/steam/palworld_server/Pal/Saved/Config/LinuxServer/Engine.ini
```

`config/DefaultPalWorldSettings.ini` and `config/DefaultEngine.ini` are source
templates and reference files. Editing those files alone does not change an
already-running server. Restart or recreate the container after changing
`.env.palworld` so the settings generator runs again.

The detailed tables below use the defaults in this project’s
`.env.palworld.example` and `config/default.yaml`. They are not guaranteed to
match the defaults in Palworld’s original sample INI and may change as
Palworld or this project is updated. The complete environment file is available
here: [`.env.palworld.example`](.env.palworld.example).

### Value conventions

- Boolean values are written as `true` or `false`. The loader also accepts
  `yes`/`no`, `on`/`off`, and `1`/`0`, case-insensitively.
- Integer and decimal values are converted to numbers before the INI is
  generated. Use a decimal for rates and multipliers, such as `1.0`.
- For most rate and damage multipliers, `1.0` is the normal game value. A value
  above `1.0` generally increases a rate or amount; a value below `1.0`
  generally decreases it. Depletion rates are the exception: a larger value
  consumes hunger or stamina faster.
- This project does not clamp every Palworld value. “Non-negative multiplier”
  describes the safe practical range where no hard game limit is documented;
  exact limits can vary by Palworld version.
- Values such as `CROSSPLAY_PLATFORMS` and `DENY_TECHNOLOGY_LIST` are passed as
  strings. Preserve the syntax expected by the game.

## Palworld game settings

Every variable in the following sections is written to the generated
`PalWorldSettings.ini` unless explicitly noted otherwise. The tables list the
environment variable, project default, practical/documented range, and effect.

### Server and connection

| Variable | Default | Allowed value / range | Effect |
|---|---:|---|---|
| `SERVER_NAME` | `Palworld Server` | Text | Name shown in the server browser and connection UI. |
| `SERVER_DESCRIPTION` | `A Palworld dedicated server` | Text | Description shown in the server browser. |
| `SERVER_PASSWORD` | empty | Text; empty disables the join password | Password required to join. |
| `ADMIN_PASSWORD` | required | Non-empty text | Grants admin commands and is also used by RCON. Keep it secret. |
| `MAX_PLAYERS` | `32` | `1–32` | Manager/Compose-side maximum player validation. |
| `SERVER_PLAYER_MAX_NUM` | `32` | Positive integer; practical limit depends on the game build | Value written to `ServerPlayerMaxNum`. |
| `COOP_PLAYER_MAX_NUM` | `4` | Positive integer | Co-op player limit used by the game. |
| `SERVER_PORT` | `8211` | `1024–65535` | Game server UDP listening port and Compose mapping. |
| `PUBLIC_IP` | empty | Public IPv4, hostname, or empty | Explicit address advertised to clients. |
| `PUBLIC_PORT` | `8211` | `1–65535` | Publicly advertised game port; does not change the local listening port. |
| `REGION` | empty | Text | Optional region metadata. |
| `USE_AUTH` | `true` | Boolean | Enables server authentication. |
| `BAN_LIST_URL` | official URL | URL | Remote ban-list URL used by the game. |
| `CROSSPLAY_PLATFORMS` | `(Steam,Xbox,PS5,Mac)` | Parenthesized comma-separated list | Platforms allowed to connect. Keep the surrounding parentheses. |
| `REST_API_ENABLED` | `true` | Boolean | Enables Palworld’s REST API. Keep the API private unless protected. |
| `REST_API_PORT` | `8212` | `1024–65535` | REST API listening port. |
| `REST_API_HOST` | `localhost` | Hostname/IP | Manager-side REST API connection address. |
| `RCON_ENABLED` | `true` | Boolean | Enables RCON in the generated game settings. |
| `RCON_PORT` | `25575` | `1–65535` | RCON listening port. |
| `RCON_HOST` | `localhost` | Hostname/IP | Manager-side RCON connection address. |

`QUERY_PORT` (`27018` by default) is the Steam server-query UDP port used by
Compose and the server startup command. It is not a `PalWorldSettings.ini`
option. `SERVER_PORT`, `REST_API_PORT`, and `QUERY_PORT` are validated by the
manager/health-check path; Compose also uses them when it creates port
mappings.

### Difficulty, modes, and randomization

| Variable | Default | Allowed value / range | Effect |
|---|---:|---|---|
| `DIFFICULTY` | `None` | `None`, `Normal`, `Difficult` | Selects the game difficulty preset. |
| `DEATH_PENALTY` | `All` | `None`, `Item`, `ItemAndEquipment`, `All` | `None`: no drops; `Item`: items except equipment; `ItemAndEquipment`: items and equipment; `All`: items, equipment, and team Pals. |
| `HARDCORE` | `false` | Boolean | Enables Hardcore mode and its death behavior. |
| `IS_MULTIPLAY` | `true` | Boolean | Enables multiplayer behavior. |
| `IS_PVP` | `false` | Boolean | Enables PvP. Combine with the explicit PvP damage switches when needed. |
| `RANDOMIZER_TYPE` | `None` | `None`, `Region`, `All` | Pal spawn randomization: disabled, by region, or fully randomized. |
| `RANDOMIZER_SEED` | empty | Text | Seed used by the randomizer. |
| `IS_RANDOMIZER_PAL_LEVEL_RANDOM` | `false` | Boolean | Randomizes wild Pal levels when randomization is enabled. |

### Time, experience, Pal, and player rates

Unless noted otherwise, these are decimal multipliers with a default of `1.0`.

| Variable | Default | Effect |
|---|---:|---|
| `DAY_TIME_SPEED_RATE` | `1.0` | Daytime world-clock progression; higher values make daytime pass faster. |
| `NIGHT_TIME_SPEED_RATE` | `1.0` | Nighttime world-clock progression; higher values make nighttime pass faster. |
| `EXP_RATE` | `1.0` | Player and Pal experience gain. |
| `WORK_SPEED_RATE` | `1.0` | Pal work and production speed. |
| `PAL_CAPTURE_RATE` | `1.0` | Capture success multiplier. |
| `PAL_SPAWN_NUM_RATE` | `1.0` | Number of wild Pals spawned; higher values increase CPU and replication load. |
| `PAL_DAMAGE_RATE_ATTACK` | `1.0` | Damage dealt by Pals. |
| `PAL_DAMAGE_RATE_DEFENSE` | `1.0` | Damage received by Pals. |
| `PAL_AUTO_HP_REGENE_RATE` | `1.0` | Pal natural HP regeneration. |
| `PAL_AUTO_HP_REGENE_RATE_IN_SLEEP` | `1.0` | Pal HP regeneration while sleeping in the Palbox. |
| `PAL_STAMINA_DECREACE_RATE` | `1.0` | Pal stamina depletion; the spelling follows the game’s INI key. |
| `PAL_STOMACH_DECREACE_RATE` | `1.0` | Pal hunger depletion; the spelling follows the game’s INI key. |
| `PAL_EGG_DEFAULT_HATCHING_TIME` | `72.0` | Huge Egg incubation time in hours; other egg types use the game’s corresponding incubation behavior. |
| `PLAYER_DAMAGE_RATE_ATTACK` | `1.0` | Damage dealt by players. |
| `PLAYER_DAMAGE_RATE_DEFENSE` | `1.0` | Damage received by players. |
| `PLAYER_AUTO_HP_REGENE_RATE` | `1.0` | Player natural HP regeneration. |
| `PLAYER_AUTO_HP_REGENE_RATE_IN_SLEEP` | `1.0` | Player HP regeneration while sleeping. |
| `PLAYER_STAMINA_DECREACE_RATE` | `1.0` | Player stamina depletion. |
| `PLAYER_STOMACH_DECREACE_RATE` | `1.0` | Player hunger depletion. |

### Combat, building, bases, guilds, items, and drops

| Variable | Default | Allowed value / range | Effect |
|---|---:|---|---|
| `ENABLE_PLAYER_TO_PLAYER_DAMAGE` | `false` | Boolean | Allows direct player damage. |
| `ENABLE_FRIENDLY_FIRE` | `false` | Boolean | Allows damage to friendly players. |
| `ENABLE_INVADER_ENEMY` | `true` | Boolean | Enables invader enemies. |
| `ACTIVE_UNKO` | `false` | Boolean | Enables the game’s UNKO drop feature. |
| `ENABLE_AIM_ASSIST_PAD` | `true` | Boolean | Enables controller aim assist. |
| `ENABLE_AIM_ASSIST_KEYBOARD` | `false` | Boolean | Enables keyboard aim assist. |
| `BUILD_OBJECT_HP_RATE` | `1.0` | Non-negative multiplier | Structure HP multiplier. |
| `BUILD_OBJECT_DAMAGE_RATE` | `1.0` | Non-negative multiplier | Damage dealt to structures. |
| `BUILD_OBJECT_DETERIORATION_DAMAGE_RATE` | `1.0` | Non-negative multiplier | Structure deterioration/decay speed. |
| `COLLECTION_DROP_RATE` | `1.0` | Non-negative multiplier | Quantity obtained from gatherable resources. |
| `COLLECTION_OBJECT_HP_RATE` | `1.0` | Non-negative multiplier | HP of gatherable objects. |
| `COLLECTION_OBJECT_RESPAWN_SPEED_RATE` | `1.0` | Non-negative multiplier | Gatherable respawn interval; smaller values respawn faster. |
| `ENEMY_DROP_ITEM_RATE` | `1.0` | Non-negative multiplier | Quantity of items dropped by enemies. |
| `BUILD_AREA_LIMIT` | `false` | Boolean | Restricts building in areas near structures such as fast-travel points. |
| `MAX_BUILDING_LIMIT_NUM` | `0` | Non-negative integer; `0` means unlimited | Per-player building count cap. |
| `BASE_CAMP_MAX_NUM` | `128` | Non-negative integer | Total base-camp count across the server. |
| `BASE_CAMP_MAX_NUM_IN_GUILD` | `4` | Documented default `4`, maximum `10` | Maximum bases per guild; increasing it raises processing load. |
| `BASE_CAMP_WORKER_MAX_NUM` | `15` | Documented maximum `50` | Maximum Pals working at each base; increasing it raises processing load. Some Palworld versions have a game-side bug where this has no effect. |
| `GUILD_PLAYER_MAX_NUM` | `20` | Positive integer | Maximum guild members. |
| `AUTO_RESET_GUILD_NO_ONLINE_PLAYERS` | `false` | Boolean | Deletes guild structures and base Pals when no guild members log in. |
| `AUTO_RESET_GUILD_TIME_NO_ONLINE_PLAYERS` | `72.0` | Non-negative hours | Offline duration before automatic guild reset; ignored when the switch is false. |
| `DROP_ITEM_MAX_NUM` | `3000` | Non-negative integer | Maximum ordinary dropped items in the world. |
| `DROP_ITEM_MAX_NUM_UNKO` | `100` | Non-negative integer | Maximum UNKO drops in the world. |
| `PHYSICS_ACTIVE_DROP_ITEM_MAX_NUM` | `-1` | Integer; `-1` follows game default behavior | Maximum active physics drops. |
| `DROP_ITEM_ALIVE_MAX_HOURS` | `1.0` | Non-negative hours | Time before dropped items despawn. |
| `ITEM_WEIGHT_RATE` | `1.0` | Non-negative multiplier | Item weight multiplier. |
| `EQUIPMENT_DURABILITY_DAMAGE_RATE` | `1.0` | Non-negative multiplier | Equipment durability loss multiplier. |

### Travel, persistence, communication, and Global Palbox

| Variable | Default | Allowed value / range | Effect |
|---|---:|---|---|
| `CAN_PICKUP_OTHER_GUILD_DEATH_PENALTY_DROP` | `false` | Boolean | Allows another guild to pick up death-penalty drops. |
| `ALLOW_CLIENT_MOD` | `true` | Boolean | Allows clients with mods to join. Use only when the server’s trust model permits it. |
| `ENABLE_NON_LOGIN_PENALTY` | `true` | Boolean | Enables the non-login penalty mechanic. |
| `ENABLE_FAST_TRAVEL` | `true` | Boolean | Enables fast travel. |
| `ENABLE_FAST_TRAVEL_ONLY_BASE_CAMP` | `false` | Boolean | Restricts fast travel to base-camp travel points. |
| `IS_START_LOCATION_SELECT_BY_MAP` | `true` | Boolean | Allows selecting the starting location on the map. |
| `EXIST_PLAYER_AFTER_LOGOUT` | `false` | Boolean | Leaves a sleeping player at the logout location instead of removing them. |
| `ENABLE_DEFENSE_OTHER_GUILD_PLAYER` | `false` | Boolean | Enables defense against players from another guild. |
| `INVISIBLE_OTHER_GUILD_BASE_CAMP_AREA_FX` | `false` | Boolean | Controls visibility of other-guild base-area boundary effects. |
| `AUTO_SAVE_SPAN` | `30.0` | Non-negative seconds | Interval between automatic saves. |
| `IS_USE_BACKUP_SAVE_DATA` | `true` | Boolean | Enables the game’s backup save data; increases disk usage. |
| `SHOW_PLAYER_LIST` | `false` | Boolean | Shows the player list in the ESC menu. |
| `CHAT_POST_LIMIT_PER_MINUTE` | `30` | Non-negative integer | Maximum chat messages per player per minute. |
| `PAL_LOST` | `false` | Boolean | Permanently loses Pals on death. |
| `CHARACTER_RECREATE_IN_HARDCORE` | `false` | Boolean | Allows character recreation after death in Hardcore mode. |
| `ALLOW_GLOBAL_PALBOX_EXPORT` | `true` | Boolean | Allows saving to the Global Palbox. |
| `ALLOW_GLOBAL_PALBOX_IMPORT` | `false` | Boolean | Allows loading from the Global Palbox. |
| `LOG_FORMAT_TYPE` | `Text` | `Text` or `Json` | Palworld server log format. |
| `ENABLE_PREDATOR_BOSS_PAL` | `true` | Boolean | Enables Predator boss Pals. |
| `SUPPLY_DROP_SPAN` | `180` | Non-negative minutes | Meteorite/supply-drop interval. |

### Advanced game-balance and server management

| Variable | Default | Allowed value / range | Effect |
|---|---:|---|---|
| `SERVER_REPLICATE_PAWN_CULL_DISTANCE` | `15000.0` | Documented `5000–15000` cm | Distance at which Pal/actor replication is culled; larger values increase replication load. |
| `ITEM_CONTAINER_FORCE_MARK_DIRTY_INTERVAL` | `1.0` | Non-negative seconds | How often an open item container is force-synchronized. |
| `ITEM_CORRUPTION_MULTIPLIER` | `1.0` | Non-negative multiplier | Item corruption speed. |
| `MONSTER_FARM_ACTION_SPEED_RATE` | `1.0` | Non-negative multiplier | Production speed from grazing/monster farms. |
| `PLAYER_DATA_STORAGE_UPDATE_CHECK_INTERVAL` | `1.0` | Non-negative seconds | Interval between checks for updates to Pal storage data. |
| `DENY_TECHNOLOGY_LIST` | empty | Technology ID list/string | Disables named technologies; follow the game’s list syntax. |
| `GUILD_REJOIN_COOLDOWN_MINUTES` | `0` | Non-negative minutes | Guild rejoin cooldown. |
| `AUTO_TRANSFER_MASTER_CHECK_INTERVAL` | `3600` | Non-negative seconds | Interval for checking whether guild leadership should transfer. |
| `AUTO_TRANSFER_MASTER_THRESHOLD_DAYS` | `14` | Non-negative days | Inactivity period before guild-master transfer. |
| `MAX_GUILDS_PER_FRAME` | `10` | Positive integer | Maximum guilds processed per server frame; higher values can increase frame work. |
| `BUILDING_NAME_DISPLAY_CACHE_TTL` | `60` | Non-negative seconds | Cache lifetime for building-name display data. |
| `ENABLE_BUILDING_PLAYER_UID_DISPLAY` | `false` | Boolean | Shows the creator’s player ID on structures. |
| `SHOW_JOIN_LEFT_MESSAGE` | `true` | Boolean | Shows join/leave messages in the dedicated server. |
| `ALLOW_ENHANCE_STAT_HEALTH` | `true` | Boolean | Allows enhancement of Health stat. |
| `ALLOW_ENHANCE_STAT_ATTACK` | `true` | Boolean | Allows enhancement of Attack stat. |
| `ALLOW_ENHANCE_STAT_STAMINA` | `true` | Boolean | Allows enhancement of Stamina stat. |
| `ALLOW_ENHANCE_STAT_WEIGHT` | `true` | Boolean | Allows enhancement of Weight stat. |
| `ALLOW_ENHANCE_STAT_WORK_SPEED` | `true` | Boolean | Allows enhancement of Work Speed stat. |
| `DISPLAY_PVP_ITEM_ON_MAP_BASE_CAMP` | `false` | Boolean | Shows PvP-only item counts at bases on the world map. |
| `DISPLAY_PVP_ITEM_ON_MAP_PLAYER` | `false` | Boolean | Shows player locations and PvP-only item counts on the map. |
| `ENABLE_VOICE_CHAT` | `false` | Boolean | Enables in-game voice chat. |
| `VOICE_CHAT_MAX_DISTANCE` | `3000` | Non-negative distance units | Distance at which voice volume is no longer attenuated. |
| `VOICE_CHAT_ZERO_DISTANCE` | `15000` | Non-negative distance units | Distance at which voice volume reaches zero. |
| `ENABLE_ADDITIONAL_PVP_DROP_ITEM` | `false` | Boolean | Enables an extra item drop when a player is killed in PvP. |
| `ADDITIONAL_PVP_DROP_ITEM_ID` | `PlayerDropItem` | Item ID string | Item dropped when the preceding switch is enabled. |
| `ADDITIONAL_PVP_DROP_ITEM_NUM` | `1` | Positive integer | Quantity of the additional PvP drop. |
| `BLOCK_RESPAWN_TIME` | `5` | Non-negative seconds | Cooldown before respawning after death. |
| `RESPAWN_PENALTY_DURATION_THRESHOLD` | `0` | Non-negative seconds | Survival-time threshold for applying the respawn penalty scale after a later death. |
| `RESPAWN_PENALTY_TIME_SCALE` | `2.0` | Non-negative multiplier | Multiplier applied to the respawn cooldown. |

## Generated Engine.ini performance settings

The repository’s `config/DefaultEngine.ini` contains the base Unreal content
paths. The generator preserves that content and appends the performance values
below to the active `Engine.ini`. These are the 13 `ENGINE_*` variables in
`.env.palworld.example`.

| Variable | Default | Allowed value / range | Effect |
|---|---:|---|---|
| `ENGINE_LAN_TICK_RATE` | `120` | Positive integer | Maximum network update tick rate for LAN connections. |
| `ENGINE_NET_TICK_RATE` | `120` | Positive integer | Maximum network update tick rate for online connections. |
| `ENGINE_INTERNET_SPEED` | `104857600` | Positive integer; bytes/second in this project | Configured Internet client bandwidth limit, not guaranteed throughput. |
| `ENGINE_LAN_SPEED` | `104857600` | Positive integer; bytes/second in this project | Configured LAN client bandwidth limit. |
| `ENGINE_MAX_CLIENT_RATE` | `104857600` | Positive integer; bytes/second in this project | Maximum client transfer rate. |
| `ENGINE_MAX_INTERNET_CLIENT_RATE` | `104857600` | Positive integer; bytes/second in this project | Maximum Internet client transfer rate. |
| `ENGINE_SMOOTH_FRAME_RATE` | `true` | Boolean | Enables Unreal frame-rate smoothing. |
| `ENGINE_USE_FIXED_FRAME_RATE` | `false` | Boolean | Uses the fixed frame-rate value when enabled. |
| `ENGINE_MIN_FRAME_RATE` | `60.0` | Non-negative FPS | Minimum desired frame rate. |
| `ENGINE_FIXED_FRAME_RATE` | `120.0` | Positive FPS | Fixed frame rate used when fixed-rate mode is enabled. |
| `ENGINE_CLIENT_TICKS` | `120` | Positive integer | Client network ticks per second. |
| `ENGINE_FRAME_RATE_LOWER` | `30.0` | Non-negative FPS; below upper bound | Lower edge of the smoothing range. |
| `ENGINE_FRAME_RATE_UPPER` | `120.0` | Positive FPS; above lower bound | Upper edge of the smoothing range. |

Higher tick rates and bandwidth ceilings can improve responsiveness on a
well-provisioned host, but they also consume more CPU and network capacity.
Tune them with `MAX_PLAYERS`, `PAL_SPAWN_NUM_RATE`, and
`SERVER_REPLICATE_PAWN_CULL_DISTANCE`. Keep the smoothing lower bound below the
upper bound; both values are written into Unreal’s `SmoothedFrameRateRange`
structure.

## Container and management settings

The variables in this section configure the image’s manager layer, not
`PalWorldSettings.ini`.

### Startup and identity

| Variable | Default | Allowed value / range | Effect |
|---|---:|---|---|
| `PUID` | `1000` | Positive integer; `0` is not accepted for remapping | UID used by the container’s `steam` user. Match the owner of bind-mounted files when needed. |
| `PGID` | `1000` | Positive integer; `0` is not accepted for remapping | GID used by the container’s `steam` user. |
| `USE_PERFORMANCE_THREADS` | `true` | Boolean | Enables the server’s performance-thread startup option. |
| `DISABLE_ASYNC_LOADING` | `true` | Boolean | Disables asynchronous loading according to the image’s startup configuration. |
| `USE_MULTITHREAD_FOR_DS` | `true` | Boolean | Enables the dedicated-server multithreading startup option. |
| `WORKER_THREADS_COUNT` | `0` | Non-negative integer; `0` lets the server choose | Number of worker threads passed at startup. |
| `ADDITIONAL_SERVER_OPTIONS` | empty | Space-separated option string | Extra command-line arguments for the server process. Verify arguments against the current Palworld version. |
| `ENABLE_PUBLIC_LOBBY` | `false` | Boolean | Enables the public-lobby startup option. |
| `LOG_FORMAT` | `text` | `text` or `json` | Format emitted by the manager/application logs. |

### Monitoring and idle restart

| Variable | Default | Allowed value / range | Effect |
|---|---:|---|---|
| `MONITORING_MODE` | `logs` | `logs`, `prometheus`, or `both` | Selects log monitoring, Prometheus metrics, or both. |
| `METRICS_INTERVAL` | `60` | Positive seconds | Metrics collection interval. |
| `ENABLE_DASHBOARD` | `true` | Boolean | Enables the manager dashboard. |
| `DASHBOARD_PORT` | `8080` | `1–65535` | Manager dashboard port. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` | Manager log verbosity. |
| `LOG_FORMAT_STYLE` | `simple` | Supported logging style | Manager log presentation style. |
| `IDLE_RESTART_ENABLED` | `true` | Boolean | Restarts the server after the configured no-player period. |
| `IDLE_RESTART_MINUTES` | `30` | Positive minutes | No-player period before an idle restart. |

Idle restart is useful for small or personal servers, but it interrupts any
background activity that occurs while no players are connected. Set
`DISCORD_EVENT_IDLE_RESTART=true` if you want a notification when it happens.

### Backups

| Variable | Default | Allowed value / range | Effect |
|---|---:|---|---|
| `BACKUP_ENABLED` | `true` | Boolean | Enables automatic backups. |
| `BACKUP_INTERVAL` | `3600` | Positive seconds | Time between backups. |
| `BACKUP_RETENTION_DAYS` | `7` | Non-negative days | Daily backup retention period. |
| `BACKUP_RETENTION_WEEKS` | `4` | Non-negative weeks | Weekly backup retention period. |
| `BACKUP_RETENTION_MONTHS` | `6` | Non-negative months | Monthly backup retention period. |
| `BACKUP_COMPRESS` | `true` | Boolean | Compresses backup archives. |
| `BACKUP_MAX_COUNT` | `100` | Non-negative integer | Maximum number of backup archives retained by the manager. |
| `BACKUP_CLEANUP_INTERVAL` | `86400` | Positive seconds | How often expired backups are removed. |

Backups are stored under `/home/steam/backups` by default. They are not a
substitute for an off-host backup: copy important archives to another disk or
object-storage provider. Back up the world before changing death penalties,
Hardcore/PAL loss, randomization, Global Palbox, or guild-reset settings.

### Discord notifications and language

| Variable | Default | Allowed value / range | Effect |
|---|---:|---|---|
| `DISCORD_ENABLED` | `false` | Boolean | Enables Discord notifications. |
| `DISCORD_WEBHOOK_URL` | empty | Discord webhook URL | Destination webhook; required when notifications are enabled. |
| `DISCORD_MENTION_ROLE` | empty | Role ID or mention string | Optional role to mention in notifications. |
| `DISCORD_EVENT_START` | `true` | Boolean | Notify when the server starts. |
| `DISCORD_EVENT_STOP` | `true` | Boolean | Notify when the server stops. |
| `DISCORD_EVENT_JOIN` | `true` | Boolean | Notify when a player joins. |
| `DISCORD_EVENT_LEAVE` | `true` | Boolean | Notify when a player leaves. |
| `DISCORD_EVENT_BACKUP` | `true` | Boolean | Notify when a backup completes. |
| `DISCORD_EVENT_ERRORS` | `true` | Boolean | Notify on manager errors. |
| `DISCORD_EVENT_IDLE_RESTART` | `true` | Boolean | Notify before or after an idle restart. |
| `LANGUAGE` | `ko` | `ko`, `en`, or `ja` | Language used by Discord notifications. |

### Paths and SteamCMD

| Variable | Default | Allowed value / range | Effect |
|---|---:|---|---|
| `SERVER_DIR` | `/home/steam/palworld_server` | Container path | Root directory for the dedicated server. |
| `BACKUP_DIR` | `/home/steam/backups` | Container path | Backup destination. |
| `LOG_DIR` | `/home/steam/logs` | Container path | Manager and server log destination. |
| `STEAMCMD_DIR` | `/home/steam/steamcmd` | Container path | SteamCMD installation directory. |
| `STEAMCMD_APP_ID` | `2394010` | Steam App ID integer | App ID used by SteamCMD to install/update Palworld. |
| `STEAMCMD_VALIDATE` | `true` | Boolean | Validates installed files during SteamCMD operations. |
| `CHECK_VERSION_UPDATE` | `true` | Boolean | Checks periodically for a newer Palworld server version and reports it without automatically restarting an active server. |
| `UPDATE_ON_START` | `true` | Boolean | Checks for an update during container startup. |

`DISCORD_EVENT_UPDATE` (`true` by default) controls whether update detections
are sent to Discord. When an update is found during runtime, the manager can
also notify players through RCON; it does not restart the server automatically.

## Operations and security

### REST API and RCON

The manager can use the Palworld REST API and RCON for monitoring and
administration. Example local calls are:

```bash
curl http://localhost:8212/v1/api/info
curl http://localhost:8212/v1/api/players
curl http://localhost:8212/v1/api/settings

rcon-cli --host localhost --port 25575 \
  --password "$ADMIN_PASSWORD" ShowPlayers
rcon-cli --host localhost --port 25575 \
  --password "$ADMIN_PASSWORD" "Broadcast Hello!"
```

Do not expose these interfaces directly to the public internet. Use a strong
`ADMIN_PASSWORD`, bind ports to localhost/private interfaces, and use a
firewall or VPN for remote administration.

### World settings that may not apply immediately

Palworld’s active settings file is the copy under
`Pal/Saved/Config/LinuxServer/`, not the repository template. In addition,
some world settings can be overridden by `WorldOption.sav`. If a changed value
does not take effect, stop the server, back up the world, and check whether the
world-option save needs to be removed or regenerated for the Palworld version
in use.

### Health checks and logs

Check the container health status and recent logs with:

```bash
docker ps
docker inspect --format '{{.State.Health.Status}}' palworld-server
docker logs --tail 100 palworld-server
```

The bundled health check can also be invoked directly in the container:

```bash
docker exec palworld-server python /app/scripts/healthcheck.py
```

## ARM64 performance

On ARM64, the image uses FEX to run the x86_64 Palworld server. The container
enables the relevant FEX settings automatically, including JIT caching, lazy
memory deletion, and static register allocation. FEX generally has lower
overhead than QEMU for this workload, but actual performance depends on the
host CPU, memory, storage, and Palworld version.

Plan resources around the actual workload rather than the player count alone:
Pal spawn rate, replication distance, base worker count, tick rates, and build
activity can all affect CPU and memory use.

| Concurrent players | Suggested CPU | Suggested RAM | Suggested storage |
|---:|---:|---:|---:|
| 1–8 | 2 cores | 2 GB | 10 GB |
| 9–16 | 4 cores | 4 GB | 15 GB |
| 17–24 | 6 cores | 6 GB | 20 GB |
| 25–32 | 8 cores | 8 GB | 25 GB |

These are starting points, not guarantees. Monitor the server under real player
load and leave headroom for the host OS, backups, and monitoring services.

Common ARM64 cloud options include AWS Graviton (`c7g`, `m7g`), Oracle Cloud
Ampere A1, Hetzner CAX, and Scaleway ARM64 instances.

## Advanced usage

### Build the image

```bash
git clone https://github.com/supersunho/docker-palworld-server.git
cd docker-palworld-server

# Native build
docker build -t palworld-server .

# Explicit ARM64 build
docker buildx build --platform linux/arm64 -t palworld-server .
```

### Use a custom YAML configuration

The normal interface is `.env.palworld`. For development or advanced image
customization, a replacement YAML file can be mounted at the path read by the
application:

```bash
docker run -d \
  -v ./my-config.yaml:/app/config/default.yaml:ro \
  -v palworld-data:/home/steam/palworld_server \
  supersunho/palworld-server:latest
```

Keep the YAML structure compatible with the repository’s
[`config/default.yaml`](config/default.yaml). A custom file can bypass the
documented environment defaults, so review it after image updates.

### Development shell

```bash
docker run -it --rm \
  -v "$(pwd):/app" \
  -p 8211:8211/udp \
  supersunho/palworld-server:latest bash
```

## References and support

### Palworld and Unreal documentation

- [Palworld Server Guide — Configuration parameters](https://docs.palworldgame.com/settings-and-operation/configuration/)
- [Palworld Server Guide — Configure the server](https://docs.palworldgame.com/settings-and-operation/arguments/)
- [Unreal Engine — Configuration Files](https://dev.epicgames.com/documentation/en-us/unreal-engine/configuration-files-in-unreal-engine)
- [Unreal Engine — Avoiding Hitches in Networking](https://dev.epicgames.com/community/learning/knowledge-base/eZyq/unreal-engine-avoiding-hitches-in-networking)

## License

MIT License. See the repository for the complete license text.
