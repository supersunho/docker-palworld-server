#!/usr/bin/env python3
"""
Configuration loader module
YAML + environment variable hybrid approach implementation
"""

import os
import re
import yaml
from pathlib import Path
from typing import Any, Dict, Optional, Union
from dataclasses import dataclass, field


@dataclass
class ConfigPaths:
    """Configuration paths data class"""
    server_dir: Path = field(default_factory=lambda: Path("/home/steam/palworld_server"))
    backup_dir: Path = field(default_factory=lambda: Path("/home/steam/backups"))
    log_dir: Path = field(default_factory=lambda: Path("/home/steam/logs"))
    steamcmd_dir: Path = field(default_factory=lambda: Path("/home/steam/steamcmd"))


@dataclass
class ServerConfig:
    """Server configuration data class"""
    name: str = "Palworld Server"
    password: str = ""
    admin_password: str = "admin123"
    max_players: int = 32
    port: int = 8211
    description: str = "A Palworld dedicated server"


@dataclass
class RestAPIConfig:
    """REST API configuration data class"""
    enabled: bool = True
    port: int = 8212
    host: str = "host.docker.internal" 


@dataclass
class RconConfig:
    """RCON configuration data class"""
    enabled: bool = False
    port: int = 25575
    host: str = "host.docker.internal"


@dataclass
class ServerStartupConfig:
    """Server startup options configuration for PalServer.sh execution"""
    # Performance optimization options (official documentation recommended)
    use_performance_threads: bool = True
    disable_async_loading: bool = True
    use_multithread_for_ds: bool = True
    
    # Network settings
    query_port: int = 27018  # Change from default 27015 to avoid conflicts
    
    # Community server settings
    enable_public_lobby: bool = False
    
    # Logging configuration
    log_format: str = "text"  # Options: text, json
    
    # Advanced performance settings
    worker_threads_count: int = 0  # 0 = auto (CPU cores - 1)
    
    # Custom additional options
    additional_options: str = ""


@dataclass
class MonitoringConfig:
    """Monitoring configuration data class"""
    mode: str = "both"  # logs, prometheus, both
    log_level: str = "INFO"
    metrics_interval: int = 60
    enable_dashboard: bool = True
    dashboard_port: int = 8080


@dataclass
class BackupConfig:
    """Backup configuration data class with retention policies"""
    enabled: bool = True
    interval_seconds: int = 3600
    retention_days: int = 7
    retention_weeks: int = 4  
    retention_months: int = 6
    compress: bool = True
    max_backups: int = 100
    cleanup_interval: int = 86400  # 24 hours in seconds


@dataclass
class DiscordConfig:
    """Discord configuration data class"""
    webhook_url: str = ""
    enabled: bool = False
    mention_role: str = ""
    events: Dict[str, bool] = field(default_factory=lambda: {
        "server_start": True,
        "server_stop": True,
        "player_join": True,
        "player_leave": True,
        "backup_complete": True,
        "errors": True,
    })


@dataclass  
class GameplayConfig:
    """Gameplay configuration data class"""
    region: str = ""
    banlist_url: str = "https://api.palworldgame.com/api/banlist.txt"
    enable_player_to_player_damage: bool = False
    enable_friendly_fire: bool = False
    enable_invader_enemy: bool = True
    is_multiplay: bool = True
    is_pvp: bool = False
    coop_player_max_num: int = 4
    enable_non_login_penalty: bool = True
    enable_fast_travel: bool = True
    is_start_location_select_by_map: bool = True
    exist_player_after_logout: bool = False
    enable_defense_other_guild_player: bool = False
    can_pickup_other_guild_death_penalty_drop: bool = False
    enable_aim_assist_pad: bool = True
    enable_aim_assist_keyboard: bool = False
    active_unko: bool = False
    use_auth: bool = True


@dataclass
class ItemsConfig:
    """Items and drops configuration data class"""
    drop_item_max_num: int = 3000
    drop_item_max_num_unko: int = 100
    drop_item_alive_max_hours: float = 1.0


@dataclass
class BaseCampConfig:
    """Base camp configuration data class"""
    max_num: int = 128
    worker_max_num: int = 15


@dataclass
class GuildConfig:
    """Guild configuration data class"""
    player_max_num: int = 20
    auto_reset_guild_no_online_players: bool = False
    auto_reset_guild_time_no_online_players: float = 72.0


@dataclass
class PalSettingsConfig:
    """Pal and gameplay rate configuration data class"""
    egg_default_hatching_time: float = 72.0
    work_speed_rate: float = 1.0
    day_time_speed_rate: float = 1.0
    night_time_speed_rate: float = 1.0
    exp_rate: float = 1.0
    pal_capture_rate: float = 1.0
    pal_spawn_num_rate: float = 1.0
    pal_damage_rate_attack: float = 1.0
    pal_damage_rate_defense: float = 1.0
    pal_stomach_decrease_rate: float = 1.0
    pal_stamina_decrease_rate: float = 1.0
    pal_auto_hp_regene_rate: float = 1.0
    pal_auto_hp_regene_rate_in_sleep: float = 1.0
    player_damage_rate_attack: float = 1.0
    player_damage_rate_defense: float = 1.0
    player_stomach_decrease_rate: float = 1.0
    player_stamina_decrease_rate: float = 1.0
    player_auto_hp_regene_rate: float = 1.0
    player_auto_hp_regene_rate_in_sleep: float = 1.0


@dataclass
class BuildingConfig:
    """Building and collection configuration data class"""
    build_object_damage_rate: float = 1.0
    build_object_deterioration_damage_rate: float = 1.0
    collection_drop_rate: float = 1.0
    collection_object_hp_rate: float = 1.0
    collection_object_respawn_speed_rate: float = 1.0
    enemy_drop_item_rate: float = 1.0


@dataclass
class DifficultyConfig:
    """Difficulty configuration data class"""
    level: str = "None"
    death_penalty: str = "All"


@dataclass
class SteamCMDConfig:
    """SteamCMD configuration data class"""
    app_id: int = 2394010
    validate: bool = True
    auto_update: bool = True
    update_on_start: bool = True


@dataclass
class EngineConfig:
    """Engine.ini configuration data class"""
    # Network and tick rate settings
    lan_server_max_tick_rate: int = 120
    net_server_max_tick_rate: int = 120
    
    # Player network speed settings
    configured_internet_speed: int = 104857600
    configured_lan_speed: int = 104857600
    
    # Client rate settings
    max_client_rate: int = 104857600
    max_internet_client_rate: int = 104857600
    
    # Frame rate and smoothing settings
    smooth_frame_rate: bool = True
    use_fixed_frame_rate: bool = False
    min_desired_frame_rate: float = 60.0
    fixed_frame_rate: float = 120.0
    net_client_ticks_per_second: int = 120
    
    # Smoothed frame rate range settings
    frame_rate_lower_bound: float = 30.0
    frame_rate_upper_bound: float = 120.0


@dataclass
class PalworldSettings:
    """Direct Palworld settings with INI key names for automatic conversion"""
    # Core server settings
    ServerName: str = "Palworld Server"
    ServerDescription: str = "A Palworld dedicated server"
    AdminPassword: str = "admin123"
    ServerPassword: str = ""
    PublicPort: int = 8211
    PublicIP: str = ""
    ServerPlayerMaxNum: int = 32
    CoopPlayerMaxNum: int = 4
    
    # API and RCON settings
    RESTAPIEnabled: bool = True
    RESTAPIPort: int = 8212
    RCONEnabled: bool = True
    RCONPort: int = 25575
    
    # Authentication and region
    bUseAuth: bool = True
    Region: str = ""
    BanListURL: str = "https://api.palworldgame.com/api/banlist.txt"
    
    # Game difficulty and mode
    Difficulty: str = "None"
    bIsMultiplay: bool = True
    bIsPvP: bool = False
    bHardcore: bool = False
    DeathPenalty: str = "All"
    
    # Randomizer settings
    RandomizerType: str = "None"
    RandomizerSeed: str = ""
    bIsRandomizerPalLevelRandom: bool = False
    
    # Time and experience rates
    DayTimeSpeedRate: float = 1.0
    NightTimeSpeedRate: float = 1.0
    ExpRate: float = 1.0
    WorkSpeedRate: float = 1.0
    
    # Pal settings
    PalCaptureRate: float = 1.0
    PalSpawnNumRate: float = 1.0
    PalDamageRateAttack: float = 1.0
    PalDamageRateDefense: float = 1.0
    PalStomachDecreaceRate: float = 1.0
    PalStaminaDecreaceRate: float = 1.0
    PalAutoHPRegeneRate: float = 1.0
    PalAutoHpRegeneRateInSleep: float = 1.0
    PalEggDefaultHatchingTime: float = 72.0
    
    # Player settings
    PlayerDamageRateAttack: float = 1.0
    PlayerDamageRateDefense: float = 1.0
    PlayerStomachDecreaceRate: float = 1.0
    PlayerStaminaDecreaceRate: float = 1.0
    PlayerAutoHPRegeneRate: float = 1.0
    PlayerAutoHpRegeneRateInSleep: float = 1.0
    
    # PvP and combat settings
    bEnablePlayerToPlayerDamage: bool = False
    bEnableFriendlyFire: bool = False
    bEnableInvaderEnemy: bool = True
    
    # Building and objects
    BuildObjectHpRate: float = 1.0
    BuildObjectDamageRate: float = 1.0
    BuildObjectDeteriorationDamageRate: float = 1.0
    CollectionDropRate: float = 1.0
    CollectionObjectHpRate: float = 1.0
    CollectionObjectRespawnSpeedRate: float = 1.0
    bBuildAreaLimit: bool = False
    MaxBuildingLimitNum: int = 0
    EnemyDropItemRate: float = 1.0
    
    # Base camp settings
    BaseCampMaxNum: int = 128
    BaseCampWorkerMaxNum: int = 15
    BaseCampMaxNumInGuild: int = 4
    
    # Guild settings
    GuildPlayerMaxNum: int = 20
    bAutoResetGuildNoOnlinePlayers: bool = False
    AutoResetGuildTimeNoOnlinePlayers: float = 72.0
    
    # Items and drops
    DropItemMaxNum: int = 3000
    DropItemMaxNum_UNKO: int = 100
    DropItemAliveMaxHours: float = 1.0
    ItemWeightRate: float = 1.0
    EquipmentDurabilityDamageRate: float = 1.0
    
    # Game mechanics
    bActiveUNKO: bool = False
    bEnableAimAssistPad: bool = True
    bEnableAimAssistKeyboard: bool = False
    bCanPickupOtherGuildDeathPenaltyDrop: bool = False
    bEnableNonLoginPenalty: bool = True
    bEnableFastTravel: bool = True
    bIsStartLocationSelectByMap: bool = True
    bExistPlayerAfterLogout: bool = False
    bEnableDefenseOtherGuildPlayer: bool = False
    bInvisibleOtherGuildBaseCampAreaFX: bool = False
    
    # Save and backup
    AutoSaveSpan: float = 30.0
    bIsUseBackupSaveData: bool = True
    
    # Chat and communication
    bShowPlayerList: bool = False
    ChatPostLimitPerMinute: int = 30
    
    # Loss and hardcore settings
    bPalLost: bool = False
    bCharacterRecreateInHardcore: bool = False
    
    # Logging and monitoring
    LogFormatType: str = "Text"
    
    # Special events and features
    SupplyDropSpan: int = 180
    EnablePredatorBossPal: bool = True
    
    # Platform settings
    CrossplayPlatforms: str = "(Steam,Xbox,PS5,Mac)"
    
    # Global Palbox settings
    bAllowGlobalPalboxExport: bool = True
    bAllowGlobalPalboxImport: bool = False
    
    # Network settings
    ServerReplicatePawnCullDistance: float = 15000.0
    ItemContainerForceMarkDirtyInterval: float = 1.0


@dataclass
class PalworldConfig:
    """Complete Palworld configuration"""
    server: ServerConfig = field(default_factory=ServerConfig)
    rest_api: RestAPIConfig = field(default_factory=RestAPIConfig)
    rcon: RconConfig = field(default_factory=RconConfig)
    server_startup: ServerStartupConfig = field(default_factory=ServerStartupConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    backup: BackupConfig = field(default_factory=BackupConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    paths: ConfigPaths = field(default_factory=ConfigPaths)
    steamcmd: SteamCMDConfig = field(default_factory=SteamCMDConfig)
    gameplay: GameplayConfig = field(default_factory=GameplayConfig)
    items: ItemsConfig = field(default_factory=ItemsConfig)
    base_camp: BaseCampConfig = field(default_factory=BaseCampConfig)
    guild: GuildConfig = field(default_factory=GuildConfig)
    pal_settings: PalSettingsConfig = field(default_factory=PalSettingsConfig)
    building: BuildingConfig = field(default_factory=BuildingConfig)
    difficulty: DifficultyConfig = field(default_factory=DifficultyConfig)
    engine: EngineConfig = field(default_factory=EngineConfig)
    palworld_settings: PalworldSettings = field(default_factory=PalworldSettings)
    # NEW: Language setting for Discord multi-language support
    language: str = "ko"


class ConfigLoader:
    """Configuration loader class"""
    
    # Environment variable substitution pattern: ${VAR_NAME:default_value}
    ENV_VAR_PATTERN = re.compile(r'\$\{([^}:]+)(?::([^}]*))?\}')
    
    def __init__(self, config_path: Optional[Union[str, Path]] = None):
        """
        Initialize configuration loader
        
        Args:
            config_path: Configuration file path (default: config/default.yaml)
        """
        if config_path is None:
            # Find config directory from current script location
            current_dir = Path(__file__).parent.parent
            config_path = current_dir / "config" / "default.yaml"
        
        self.config_path = Path(config_path)
        self._raw_config: Dict[str, Any] = {}
        self._processed_config: Dict[str, Any] = {}
    
    def _substitute_env_vars(self, value: Any) -> Any:
        """
        Process environment variable substitution
        
        Args:
            value: Value to substitute
            
        Returns:
            Value with environment variables substituted
        """
        if isinstance(value, str):
            def replace_env_var(match):
                var_name = match.group(1)
                default_value = match.group(2) if match.group(2) is not None else ""
                return os.getenv(var_name, default_value)
            
            return self.ENV_VAR_PATTERN.sub(replace_env_var, value)
        
        elif isinstance(value, dict):
            return {k: self._substitute_env_vars(v) for k, v in value.items()}
        
        elif isinstance(value, list):
            return [self._substitute_env_vars(item) for item in value]
        
        return value
    
    def _convert_types(self, value: Any) -> Any:
        """
        Convert strings to appropriate types
        
        Args:
            value: Value to convert
            
        Returns:
            Type-converted value
        """
        if isinstance(value, str):
            # Boolean value processing
            if value.lower() in ('true', 'yes', '1', 'on'):
                return True
            elif value.lower() in ('false', 'no', '0', 'off'):
                return False
            
            # Numeric value processing
            if value.isdigit():
                return int(value)
            
            try:
                if '.' in value:
                    return float(value)
            except ValueError:
                pass
        
        elif isinstance(value, dict):
            return {k: self._convert_types(v) for k, v in value.items()}
        
        elif isinstance(value, list):
            return [self._convert_types(item) for item in value]
        
        return value
    
    def load_config(self) -> PalworldConfig:
        """
        Load configuration file and apply environment variables
        
        Returns:
            PalworldConfig instance
            
        Raises:
            FileNotFoundError: When configuration file is not found
            yaml.YAMLError: YAML parsing error
        """
        # Load YAML file
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._raw_config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"YAML file parsing error: {e}")
        
        # Environment variable substitution
        self._processed_config = self._substitute_env_vars(self._raw_config)
        
        # Type conversion
        self._processed_config = self._convert_types(self._processed_config)
        
        # Create data class instance
        return self._create_config_instance()
    
    def _create_config_instance(self) -> PalworldConfig:
        """
        Create PalworldConfig instance from dictionary
        
        Returns:
            PalworldConfig instance
        """
        config_dict = self._processed_config
        
        # Server configuration
        server_config = ServerConfig(
            name=config_dict.get('server', {}).get('name', 'Palworld Server'),
            password=config_dict.get('server', {}).get('password', ''),
            admin_password=config_dict.get('server', {}).get('admin_password', 'admin123'),
            max_players=config_dict.get('server', {}).get('max_players', 32),
            port=config_dict.get('server', {}).get('port', 8211),
            description=config_dict.get('server', {}).get('description', 'A Palworld dedicated server'),
        )
        
        # REST API configuration
        rest_api_config = RestAPIConfig(
            enabled=config_dict.get('rest_api', {}).get('enabled', True),
            port=config_dict.get('rest_api', {}).get('port', 8212),
            host=config_dict.get('rest_api', {}).get('host', 'host.docker.internal'),
        )
        
        # RCON configuration
        rcon_config = RconConfig(
            enabled=config_dict.get('rcon', {}).get('enabled', False),
            port=config_dict.get('rcon', {}).get('port', 25575),
            host=config_dict.get('rcon', {}).get('host', 'host.docker.internal'),
        )
        
        # Server startup configuration
        server_startup_config = ServerStartupConfig(
            use_performance_threads=config_dict.get('server_startup', {}).get('use_performance_threads', True),
            disable_async_loading=config_dict.get('server_startup', {}).get('disable_async_loading', True),
            use_multithread_for_ds=config_dict.get('server_startup', {}).get('use_multithread_for_ds', True),
            query_port=config_dict.get('server_startup', {}).get('query_port', 27018),
            enable_public_lobby=config_dict.get('server_startup', {}).get('enable_public_lobby', False),
            log_format=config_dict.get('server_startup', {}).get('log_format', 'text'),
            worker_threads_count=config_dict.get('server_startup', {}).get('worker_threads_count', 0),
            additional_options=config_dict.get('server_startup', {}).get('additional_options', ''),
        )
        
        # Monitoring configuration
        monitoring_config = MonitoringConfig(
            mode=config_dict.get('monitoring', {}).get('mode', 'both'),
            log_level=config_dict.get('monitoring', {}).get('log_level', 'INFO'),
            metrics_interval=config_dict.get('monitoring', {}).get('metrics_interval', 60),
            enable_dashboard=config_dict.get('monitoring', {}).get('enable_dashboard', True),
            dashboard_port=config_dict.get('monitoring', {}).get('dashboard_port', 8080),
        )
        
        # Backup configuration
        backup_config = BackupConfig(
            enabled=config_dict.get('backup', {}).get('enabled', True),
            interval_seconds=config_dict.get('backup', {}).get('interval_seconds', 3600),
            retention_days=config_dict.get('backup', {}).get('retention_days', 7),
            retention_weeks=config_dict.get('backup', {}).get('retention_weeks', 4),
            retention_months=config_dict.get('backup', {}).get('retention_months', 6),
            compress=config_dict.get('backup', {}).get('compress', True),
            max_backups=config_dict.get('backup', {}).get('max_backups', 100),
            cleanup_interval=config_dict.get('backup', {}).get('cleanup_interval', 86400),
        )
        
        # Discord configuration with enhanced event mapping
        discord_events = config_dict.get('discord', {}).get('events', {})
        discord_config = DiscordConfig(
            webhook_url=config_dict.get('discord', {}).get('webhook_url', ''),
            enabled=config_dict.get('discord', {}).get('enabled', False),
            mention_role=config_dict.get('discord', {}).get('mention_role', ''),
            events=discord_events if discord_events else {
                "server_start": True,
                "server_stop": True,
                "player_join": True,
                "player_leave": True,
                "backup_complete": True,
                "errors": True,
            }
        )
        
        # Path configuration
        paths_config = ConfigPaths(
            server_dir=Path(config_dict.get('paths', {}).get('server_dir', '/home/steam/palworld_server')),
            backup_dir=Path(config_dict.get('paths', {}).get('backup_dir', '/home/steam/backups')),
            log_dir=Path(config_dict.get('paths', {}).get('log_dir', '/home/steam/logs')),
            steamcmd_dir=Path(config_dict.get('paths', {}).get('steamcmd_dir', '/home/steam/steamcmd')),
        )
        
        # SteamCMD configuration
        steamcmd_config = SteamCMDConfig(
            app_id=config_dict.get('steamcmd', {}).get('app_id', 2394010),
            validate=config_dict.get('steamcmd', {}).get('validate', True),
            auto_update=config_dict.get('steamcmd', {}).get('auto_update', True),
            update_on_start=config_dict.get('steamcmd', {}).get('update_on_start', True),
        )
        
        # Gameplay configuration
        gameplay_config = GameplayConfig(
            region=config_dict.get('gameplay', {}).get('region', ''),
            banlist_url=config_dict.get('gameplay', {}).get('banlist_url', 'https://api.palworldgame.com/api/banlist.txt'),
            enable_player_to_player_damage=config_dict.get('gameplay', {}).get('enable_player_to_player_damage', False),
            enable_friendly_fire=config_dict.get('gameplay', {}).get('enable_friendly_fire', False),
            enable_invader_enemy=config_dict.get('gameplay', {}).get('enable_invader_enemy', True),
            is_multiplay=config_dict.get('gameplay', {}).get('is_multiplay', True),
            is_pvp=config_dict.get('gameplay', {}).get('is_pvp', False),
            coop_player_max_num=config_dict.get('gameplay', {}).get('coop_player_max_num', 4),
            enable_non_login_penalty=config_dict.get('gameplay', {}).get('enable_non_login_penalty', True),
            enable_fast_travel=config_dict.get('gameplay', {}).get('enable_fast_travel', True),
            is_start_location_select_by_map=config_dict.get('gameplay', {}).get('is_start_location_select_by_map', True),
            exist_player_after_logout=config_dict.get('gameplay', {}).get('exist_player_after_logout', False),
            enable_defense_other_guild_player=config_dict.get('gameplay', {}).get('enable_defense_other_guild_player', False),
            can_pickup_other_guild_death_penalty_drop=config_dict.get('gameplay', {}).get('can_pickup_other_guild_death_penalty_drop', False),
            enable_aim_assist_pad=config_dict.get('gameplay', {}).get('enable_aim_assist_pad', True),
            enable_aim_assist_keyboard=config_dict.get('gameplay', {}).get('enable_aim_assist_keyboard', False),
            active_unko=config_dict.get('gameplay', {}).get('active_unko', False),
            use_auth=config_dict.get('gameplay', {}).get('use_auth', True),
        )
        
        # Items configuration
        items_config = ItemsConfig(
            drop_item_max_num=config_dict.get('items', {}).get('drop_item_max_num', 3000),
            drop_item_max_num_unko=config_dict.get('items', {}).get('drop_item_max_num_unko', 100),
            drop_item_alive_max_hours=config_dict.get('items', {}).get('drop_item_alive_max_hours', 1.0),
        )
        
        # Base camp configuration
        base_camp_config = BaseCampConfig(
            max_num=config_dict.get('base_camp', {}).get('max_num', 128),
            worker_max_num=config_dict.get('base_camp', {}).get('worker_max_num', 15),
        )
        
        # Guild configuration
        guild_config = GuildConfig(
            player_max_num=config_dict.get('guild', {}).get('player_max_num', 20),
            auto_reset_guild_no_online_players=config_dict.get('guild', {}).get('auto_reset_guild_no_online_players', False),
            auto_reset_guild_time_no_online_players=config_dict.get('guild', {}).get('auto_reset_guild_time_no_online_players', 72.0),
        )
        
        # Pal settings configuration
        pal_settings_config = PalSettingsConfig(
            egg_default_hatching_time=config_dict.get('pal_settings', {}).get('egg_default_hatching_time', 72.0),
            work_speed_rate=config_dict.get('pal_settings', {}).get('work_speed_rate', 1.0),
            day_time_speed_rate=config_dict.get('pal_settings', {}).get('day_time_speed_rate', 1.0),
            night_time_speed_rate=config_dict.get('pal_settings', {}).get('night_time_speed_rate', 1.0),
            exp_rate=config_dict.get('pal_settings', {}).get('exp_rate', 1.0),
            pal_capture_rate=config_dict.get('pal_settings', {}).get('pal_capture_rate', 1.0),
            pal_spawn_num_rate=config_dict.get('pal_settings', {}).get('pal_spawn_num_rate', 1.0),
            pal_damage_rate_attack=config_dict.get('pal_settings', {}).get('pal_damage_rate_attack', 1.0),
            pal_damage_rate_defense=config_dict.get('pal_settings', {}).get('pal_damage_rate_defense', 1.0),
            pal_stomach_decrease_rate=config_dict.get('pal_settings', {}).get('pal_stomach_decrease_rate', 1.0),
            pal_stamina_decrease_rate=config_dict.get('pal_settings', {}).get('pal_stamina_decrease_rate', 1.0),
            pal_auto_hp_regene_rate=config_dict.get('pal_settings', {}).get('pal_auto_hp_regene_rate', 1.0),
            pal_auto_hp_regene_rate_in_sleep=config_dict.get('pal_settings', {}).get('pal_auto_hp_regene_rate_in_sleep', 1.0),
            player_damage_rate_attack=config_dict.get('pal_settings', {}).get('player_damage_rate_attack', 1.0),
            player_damage_rate_defense=config_dict.get('pal_settings', {}).get('player_damage_rate_defense', 1.0),
            player_stomach_decrease_rate=config_dict.get('pal_settings', {}).get('player_stomach_decrease_rate', 1.0),
            player_stamina_decrease_rate=config_dict.get('pal_settings', {}).get('player_stamina_decrease_rate', 1.0),
            player_auto_hp_regene_rate=config_dict.get('pal_settings', {}).get('player_auto_hp_regene_rate', 1.0),
            player_auto_hp_regene_rate_in_sleep=config_dict.get('pal_settings', {}).get('player_auto_hp_regene_rate_in_sleep', 1.0),
        )
        
        # Building configuration
        building_config = BuildingConfig(
            build_object_damage_rate=config_dict.get('building', {}).get('build_object_damage_rate', 1.0),
            build_object_deterioration_damage_rate=config_dict.get('building', {}).get('build_object_deterioration_damage_rate', 1.0),
            collection_drop_rate=config_dict.get('building', {}).get('collection_drop_rate', 1.0),
            collection_object_hp_rate=config_dict.get('building', {}).get('collection_object_hp_rate', 1.0),
            collection_object_respawn_speed_rate=config_dict.get('building', {}).get('collection_object_respawn_speed_rate', 1.0),
            enemy_drop_item_rate=config_dict.get('building', {}).get('enemy_drop_item_rate', 1.0),
        )
        
        # Difficulty configuration
        difficulty_config = DifficultyConfig(
            level=config_dict.get('difficulty', {}).get('level', 'None'),
            death_penalty=config_dict.get('difficulty', {}).get('death_penalty', 'All'),
        )
        
        # Engine configuration
        engine_config = EngineConfig(
            lan_server_max_tick_rate=config_dict.get('engine', {}).get('lan_server_max_tick_rate', 120),
            net_server_max_tick_rate=config_dict.get('engine', {}).get('net_server_max_tick_rate', 120),
            configured_internet_speed=config_dict.get('engine', {}).get('configured_internet_speed', 104857600),
            configured_lan_speed=config_dict.get('engine', {}).get('configured_lan_speed', 104857600),
            max_client_rate=config_dict.get('engine', {}).get('max_client_rate', 104857600),
            max_internet_client_rate=config_dict.get('engine', {}).get('max_internet_client_rate', 104857600),
            smooth_frame_rate=config_dict.get('engine', {}).get('smooth_frame_rate', True),
            use_fixed_frame_rate=config_dict.get('engine', {}).get('use_fixed_frame_rate', False),
            min_desired_frame_rate=config_dict.get('engine', {}).get('min_desired_frame_rate', 60.0),
            fixed_frame_rate=config_dict.get('engine', {}).get('fixed_frame_rate', 120.0),
            net_client_ticks_per_second=config_dict.get('engine', {}).get('net_client_ticks_per_second', 120),
            frame_rate_lower_bound=config_dict.get('engine', {}).get('frame_rate_lower_bound', 30.0),
            frame_rate_upper_bound=config_dict.get('engine', {}).get('frame_rate_upper_bound', 120.0),
        )

        # Palworld settings configuration (new section)
        palworld_settings_dict = config_dict.get('palworld_settings', {})
        palworld_settings_config = PalworldSettings(
            # Core server settings
            ServerName=palworld_settings_dict.get('ServerName', 'Palworld Server'),
            ServerDescription=palworld_settings_dict.get('ServerDescription', 'A Palworld dedicated server'),
            AdminPassword=palworld_settings_dict.get('AdminPassword', 'admin123'),
            ServerPassword=palworld_settings_dict.get('ServerPassword', ''),
            PublicPort=palworld_settings_dict.get('PublicPort', 8211),
            PublicIP=palworld_settings_dict.get('PublicIP', ''),
            ServerPlayerMaxNum=palworld_settings_dict.get('ServerPlayerMaxNum', 32),
            CoopPlayerMaxNum=palworld_settings_dict.get('CoopPlayerMaxNum', 4),
            
            # API and RCON settings
            RESTAPIEnabled=palworld_settings_dict.get('RESTAPIEnabled', True),
            RESTAPIPort=palworld_settings_dict.get('RESTAPIPort', 8212),
            RCONEnabled=palworld_settings_dict.get('RCONEnabled', True),
            RCONPort=palworld_settings_dict.get('RCONPort', 25575),
            
            # Authentication and region
            bUseAuth=palworld_settings_dict.get('bUseAuth', True),
            Region=palworld_settings_dict.get('Region', ''),
            BanListURL=palworld_settings_dict.get('BanListURL', 'https://api.palworldgame.com/api/banlist.txt'),
            
            # Game difficulty and mode
            Difficulty=palworld_settings_dict.get('Difficulty', 'None'),
            bIsMultiplay=palworld_settings_dict.get('bIsMultiplay', True),
            bIsPvP=palworld_settings_dict.get('bIsPvP', False),
            bHardcore=palworld_settings_dict.get('bHardcore', False),
            DeathPenalty=palworld_settings_dict.get('DeathPenalty', 'All'),
            
            # Randomizer settings
            RandomizerType=palworld_settings_dict.get('RandomizerType', 'None'),
            RandomizerSeed=palworld_settings_dict.get('RandomizerSeed', ''),
            bIsRandomizerPalLevelRandom=palworld_settings_dict.get('bIsRandomizerPalLevelRandom', False),
            
            # Time and experience rates
            DayTimeSpeedRate=palworld_settings_dict.get('DayTimeSpeedRate', 1.0),
            NightTimeSpeedRate=palworld_settings_dict.get('NightTimeSpeedRate', 1.0),
            ExpRate=palworld_settings_dict.get('ExpRate', 1.0),
            WorkSpeedRate=palworld_settings_dict.get('WorkSpeedRate', 1.0),
            
            # Pal settings
            PalCaptureRate=palworld_settings_dict.get('PalCaptureRate', 1.0),
            PalSpawnNumRate=palworld_settings_dict.get('PalSpawnNumRate', 1.0),
            PalDamageRateAttack=palworld_settings_dict.get('PalDamageRateAttack', 1.0),
            PalDamageRateDefense=palworld_settings_dict.get('PalDamageRateDefense', 1.0),
            PalStomachDecreaceRate=palworld_settings_dict.get('PalStomachDecreaceRate', 1.0),
            PalStaminaDecreaceRate=palworld_settings_dict.get('PalStaminaDecreaceRate', 1.0),
            PalAutoHPRegeneRate=palworld_settings_dict.get('PalAutoHPRegeneRate', 1.0),
            PalAutoHpRegeneRateInSleep=palworld_settings_dict.get('PalAutoHpRegeneRateInSleep', 1.0),
            PalEggDefaultHatchingTime=palworld_settings_dict.get('PalEggDefaultHatchingTime', 72.0),
            
            # Player settings
            PlayerDamageRateAttack=palworld_settings_dict.get('PlayerDamageRateAttack', 1.0),
            PlayerDamageRateDefense=palworld_settings_dict.get('PlayerDamageRateDefense', 1.0),
            PlayerStomachDecreaceRate=palworld_settings_dict.get('PlayerStomachDecreaceRate', 1.0),
            PlayerStaminaDecreaceRate=palworld_settings_dict.get('PlayerStaminaDecreaceRate', 1.0),
            PlayerAutoHPRegeneRate=palworld_settings_dict.get('PlayerAutoHPRegeneRate', 1.0),
            PlayerAutoHpRegeneRateInSleep=palworld_settings_dict.get('PlayerAutoHpRegeneRateInSleep', 1.0),
            
            # PvP and combat settings
            bEnablePlayerToPlayerDamage=palworld_settings_dict.get('bEnablePlayerToPlayerDamage', False),
            bEnableFriendlyFire=palworld_settings_dict.get('bEnableFriendlyFire', False),
            bEnableInvaderEnemy=palworld_settings_dict.get('bEnableInvaderEnemy', True),
            
            # Building and objects
            BuildObjectHpRate=palworld_settings_dict.get('BuildObjectHpRate', 1.0),
            BuildObjectDamageRate=palworld_settings_dict.get('BuildObjectDamageRate', 1.0),
            BuildObjectDeteriorationDamageRate=palworld_settings_dict.get('BuildObjectDeteriorationDamageRate', 1.0),
            CollectionDropRate=palworld_settings_dict.get('CollectionDropRate', 1.0),
            CollectionObjectHpRate=palworld_settings_dict.get('CollectionObjectHpRate', 1.0),
            CollectionObjectRespawnSpeedRate=palworld_settings_dict.get('CollectionObjectRespawnSpeedRate', 1.0),
            bBuildAreaLimit=palworld_settings_dict.get('bBuildAreaLimit', False),
            MaxBuildingLimitNum=palworld_settings_dict.get('MaxBuildingLimitNum', 0),
            EnemyDropItemRate=palworld_settings_dict.get('EnemyDropItemRate', 1.0),
            
            # Base camp settings
            BaseCampMaxNum=palworld_settings_dict.get('BaseCampMaxNum', 128),
            BaseCampWorkerMaxNum=palworld_settings_dict.get('BaseCampWorkerMaxNum', 15),
            BaseCampMaxNumInGuild=palworld_settings_dict.get('BaseCampMaxNumInGuild', 4),
            
            # Guild settings
            GuildPlayerMaxNum=palworld_settings_dict.get('GuildPlayerMaxNum', 20),
            bAutoResetGuildNoOnlinePlayers=palworld_settings_dict.get('bAutoResetGuildNoOnlinePlayers', False),
            AutoResetGuildTimeNoOnlinePlayers=palworld_settings_dict.get('AutoResetGuildTimeNoOnlinePlayers', 72.0),
            
            # Items and drops
            DropItemMaxNum=palworld_settings_dict.get('DropItemMaxNum', 3000),
            DropItemMaxNum_UNKO=palworld_settings_dict.get('DropItemMaxNum_UNKO', 100),
            DropItemAliveMaxHours=palworld_settings_dict.get('DropItemAliveMaxHours', 1.0),
            ItemWeightRate=palworld_settings_dict.get('ItemWeightRate', 1.0),
            EquipmentDurabilityDamageRate=palworld_settings_dict.get('EquipmentDurabilityDamageRate', 1.0),
            
            # Game mechanics
            bActiveUNKO=palworld_settings_dict.get('bActiveUNKO', False),
            bEnableAimAssistPad=palworld_settings_dict.get('bEnableAimAssistPad', True),
            bEnableAimAssistKeyboard=palworld_settings_dict.get('bEnableAimAssistKeyboard', False),
            bCanPickupOtherGuildDeathPenaltyDrop=palworld_settings_dict.get('bCanPickupOtherGuildDeathPenaltyDrop', False),
            bEnableNonLoginPenalty=palworld_settings_dict.get('bEnableNonLoginPenalty', True),
            bEnableFastTravel=palworld_settings_dict.get('bEnableFastTravel', True),
            bIsStartLocationSelectByMap=palworld_settings_dict.get('bIsStartLocationSelectByMap', True),
            bExistPlayerAfterLogout=palworld_settings_dict.get('bExistPlayerAfterLogout', False),
            bEnableDefenseOtherGuildPlayer=palworld_settings_dict.get('bEnableDefenseOtherGuildPlayer', False),
            bInvisibleOtherGuildBaseCampAreaFX=palworld_settings_dict.get('bInvisibleOtherGuildBaseCampAreaFX', False),
            
            # Save and backup
            AutoSaveSpan=palworld_settings_dict.get('AutoSaveSpan', 30.0),
            bIsUseBackupSaveData=palworld_settings_dict.get('bIsUseBackupSaveData', True),
            
            # Chat and communication
            bShowPlayerList=palworld_settings_dict.get('bShowPlayerList', False),
            ChatPostLimitPerMinute=palworld_settings_dict.get('ChatPostLimitPerMinute', 30),
            
            # Loss and hardcore settings
            bPalLost=palworld_settings_dict.get('bPalLost', False),
            bCharacterRecreateInHardcore=palworld_settings_dict.get('bCharacterRecreateInHardcore', False),
            
            # Logging and monitoring
            LogFormatType=palworld_settings_dict.get('LogFormatType', 'Text'),
            
            # Special events and features
            SupplyDropSpan=palworld_settings_dict.get('SupplyDropSpan', 180),
            EnablePredatorBossPal=palworld_settings_dict.get('EnablePredatorBossPal', True),
            
            # Platform settings
            CrossplayPlatforms=palworld_settings_dict.get('CrossplayPlatforms', '(Steam,Xbox,PS5,Mac)'),
            
            # Global Palbox settings
            bAllowGlobalPalboxExport=palworld_settings_dict.get('bAllowGlobalPalboxExport', True),
            bAllowGlobalPalboxImport=palworld_settings_dict.get('bAllowGlobalPalboxImport', False),
            
            # Network settings
            ServerReplicatePawnCullDistance=palworld_settings_dict.get('ServerReplicatePawnCullDistance', 15000.0),
            ItemContainerForceMarkDirtyInterval=palworld_settings_dict.get('ItemContainerForceMarkDirtyInterval', 1.0),
        )

        # Language configuration (NEW for Discord multi-language support)
        language = config_dict.get('language', 'ko')

        # Return complete PalworldConfig with all configurations
        return PalworldConfig(
            server=server_config,
            rest_api=rest_api_config,
            rcon=rcon_config,
            server_startup=server_startup_config,
            monitoring=monitoring_config,
            backup=backup_config,
            discord=discord_config,
            paths=paths_config,
            steamcmd=steamcmd_config,
            gameplay=gameplay_config,
            items=items_config,
            base_camp=base_camp_config,
            guild=guild_config,
            pal_settings=pal_settings_config,
            building=building_config,
            difficulty=difficulty_config,
            engine=engine_config,
            palworld_settings=palworld_settings_config,
            language=language,  # NEW: Language setting
        )

    
    def validate_config(self, config: PalworldConfig) -> bool:
        """
        Validate configuration
        
        Args:
            config: Configuration to validate
            
        Returns:
            Whether validation passed
        """
        # Port range validation
        if not (1024 <= config.server.port <= 65535):
            raise ValueError(f"Invalid server port: {config.server.port}")
        
        if not (1024 <= config.rest_api.port <= 65535):
            raise ValueError(f"Invalid REST API port: {config.rest_api.port}")
        
        # Player count validation
        if not (1 <= config.server.max_players <= 32):
            raise ValueError(f"Invalid max players count: {config.server.max_players}")
        
        # Monitoring mode validation
        valid_modes = ['logs', 'prometheus', 'both']
        if config.monitoring.mode not in valid_modes:
            raise ValueError(f"Invalid monitoring mode: {config.monitoring.mode}")
        
        # Discord webhook URL validation (if enabled)
        if config.discord.enabled and not config.discord.webhook_url:
            raise ValueError("Discord notifications enabled but webhook URL not set")
        
        # Server startup options validation
        valid_log_formats = ['text', 'json']
        if config.server_startup.log_format not in valid_log_formats:
            raise ValueError(f"Invalid log format: {config.server_startup.log_format}")
        
        if not (1024 <= config.server_startup.query_port <= 65535):
            raise ValueError(f"Invalid query port: {config.server_startup.query_port}")
        
        if config.server_startup.worker_threads_count < 0:
            raise ValueError(f"Invalid worker threads count: {config.server_startup.worker_threads_count}")
        
        # Language validation (NEW)
        valid_languages = ['ko', 'en', 'ja', 'zh']
        if config.language not in valid_languages:
            raise ValueError(f"Invalid language: {config.language}. Supported: {valid_languages}")
        
        return True


# Global configuration instances
_config_instance: Optional[PalworldConfig] = None
_config_loader: Optional[ConfigLoader] = None


def get_config(config_path: Optional[Union[str, Path]] = None) -> PalworldConfig:
    """
    Return global configuration instance (singleton pattern)
    
    Args:
        config_path: Configuration file path
        
    Returns:
        PalworldConfig instance
    """
    global _config_instance, _config_loader
    
    if _config_instance is None:
        _config_loader = ConfigLoader(config_path)
        _config_instance = _config_loader.load_config()
        _config_loader.validate_config(_config_instance)
    
    return _config_instance


def reload_config() -> PalworldConfig:
    """
    Reload configuration
    
    Returns:
        Newly loaded PalworldConfig instance
    """
    global _config_instance, _config_loader
    
    if _config_loader is None:
        raise RuntimeError("Configuration loader not initialized")
    
    _config_instance = _config_loader.load_config()
    _config_loader.validate_config(_config_instance)
    
    return _config_instance


if __name__ == "__main__":
    # Test execution
    try:
        config = get_config()
        print("✅ Configuration loaded successfully!")
        print(f"Server name: {config.server.name}")
        print(f"Max players: {config.server.max_players}")
        print(f"Monitoring mode: {config.monitoring.mode}")
        print(f"Backup enabled: {config.backup.enabled}")
        print(f"Discord enabled: {config.discord.enabled}")
        print(f"Palworld settings ServerName: {config.palworld_settings.ServerName}")
        print(f"Server startup performance threads: {config.server_startup.use_performance_threads}")
        print(f"Server startup query port: {config.server_startup.query_port}")
        print(f"Language: {config.language}")  # NEW
    except Exception as e:
        print(f"❌ Configuration load failed: {e}")
