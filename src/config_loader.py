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
    server_dir: Path = field(default_factory=lambda: Path("$HOME/palworld_server"))
    backup_dir: Path = field(default_factory=lambda: Path("$HOME/backups"))
    log_dir: Path = field(default_factory=lambda: Path("$HOME/logs"))
    steamcmd_dir: Path = field(default_factory=lambda: Path("$HOME/steamcmd"))


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
    host: str = "0.0.0.0"


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
    """Backup configuration data class"""
    enabled: bool = True
    interval_seconds: int = 3600
    retention_days: int = 7
    compress: bool = True


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
class SteamCMDConfig:
    """SteamCMD configuration data class"""
    app_id: int = 2394010
    validate: bool = True
    auto_update: bool = True
    update_on_start: bool = True


@dataclass
class PalworldConfig:
    """Main data class containing all configurations"""
    server: ServerConfig = field(default_factory=ServerConfig)
    rest_api: RestAPIConfig = field(default_factory=RestAPIConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    backup: BackupConfig = field(default_factory=BackupConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    paths: ConfigPaths = field(default_factory=ConfigPaths)
    steamcmd: SteamCMDConfig = field(default_factory=SteamCMDConfig)


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
            host=config_dict.get('rest_api', {}).get('host', '0.0.0.0'),
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
            compress=config_dict.get('backup', {}).get('compress', True),
        )
        
        # Discord configuration
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
            server_dir=Path(config_dict.get('paths', {}).get('server_dir', '$HOME/palworld_server')),
            backup_dir=Path(config_dict.get('paths', {}).get('backup_dir', '$HOME/backups')),
            log_dir=Path(config_dict.get('paths', {}).get('log_dir', '$HOME/logs')),
            steamcmd_dir=Path(config_dict.get('paths', {}).get('steamcmd_dir', '$HOME/steamcmd')),
        )
        
        # SteamCMD configuration
        steamcmd_config = SteamCMDConfig(
            app_id=config_dict.get('steamcmd', {}).get('app_id', 2394010),
            validate=config_dict.get('steamcmd', {}).get('validate', True),
            auto_update=config_dict.get('steamcmd', {}).get('auto_update', True),
            update_on_start=config_dict.get('steamcmd', {}).get('update_on_start', True),
        )
        
        return PalworldConfig(
            server=server_config,
            rest_api=rest_api_config,
            monitoring=monitoring_config,
            backup=backup_config,
            discord=discord_config,
            paths=paths_config,
            steamcmd=steamcmd_config,
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
    except Exception as e:
        print(f"❌ Configuration load failed: {e}")
