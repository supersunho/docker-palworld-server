#!/usr/bin/env python3
"""
Base configuration classes
"""

import os
import re
import yaml
from pathlib import Path
from typing import Any, Dict, Optional, Union, TypeVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..protocols import IConfigProvider

_DC = TypeVar("_DC")


@dataclass
class ConfigPaths:
    """Configuration paths data class"""

    server_dir: Path = field(default_factory=lambda: Path("/home/steam/palworld_server"))
    backup_dir: Path = field(default_factory=lambda: Path("/home/steam/backups"))
    log_dir: Path = field(default_factory=lambda: Path("/home/steam/logs"))
    steamcmd_dir: Path = field(default_factory=lambda: Path("/home/steam/steamcmd"))


# Use TYPE_CHECKING to avoid circular imports during runtime
if TYPE_CHECKING:
    from .server.server import ServerConfig, ServerStartupConfig  # noqa: F401
    from .server.rcon import RconConfig  # noqa: F401
    from .server.rest_api import RestAPIConfig  # noqa: F401
    from .monitoring.monitoring import MonitoringConfig  # noqa: F401
    from .monitoring.backup import BackupConfig  # noqa: F401
    from .monitoring.idle_restart import IdleRestartConfig  # noqa: F401
    from .integration.discord import DiscordConfig  # noqa: F401
    from .integration.steamcmd import SteamCMDConfig  # noqa: F401
    from .game.gameplay import GameplayConfig  # noqa: F401
    from .game.items import ItemsConfig  # noqa: F401
    from .game.base_camp import BaseCampConfig  # noqa: F401
    from .game.guild import GuildConfig  # noqa: F401
    from .game.pal_settings import PalSettingsConfig  # noqa: F401
    from .game.building import BuildingConfig  # noqa: F401
    from .game.difficulty import DifficultyConfig  # noqa: F401
    from .palworld.engine import EngineConfig  # noqa: F401
    from .palworld.settings import PalworldSettings  # noqa: F401
    from .palworld.main import PalworldConfig  # noqa: F401


class ConfigLoader(IConfigProvider):
    """Configuration loader class"""

    ENV_VAR_PATTERN = re.compile(r"\$\{([^}:]+)(?::([^}]*))?\}")

    def __init__(self, config_path: Optional[Union[str, Path]] = None):
        """Initialize configuration loader"""
        if config_path is None:
            current_dir = Path(__file__).parent.parent.parent
            config_path = current_dir / "config" / "default.yaml"

        self.config_path = Path(config_path)
        self._raw_config: Dict[str, Any] = {}
        self._processed_config: Dict[str, Any] = {}

    def _substitute_env_vars(self, value: Any) -> Any:
        """Process environment variable substitution"""
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

    def _convert_value(self, value: str, target_type: type, field_path: str = "") -> Any:
        """Convert a single env-var string to the target dataclass type.

        Raises ValueError with field_path context on conversion failure.
        """
        if target_type is str:
            return value
        if target_type is int:
            try:
                return int(value)
            except (ValueError, TypeError):
                raise ValueError(
                    f"{field_path}: cannot convert '{value}' to int"
                )
        if target_type is float:
            try:
                return float(value)
            except (ValueError, TypeError):
                raise ValueError(
                    f"{field_path}: cannot convert '{value}' to float"
                )
        if target_type is bool:
            if isinstance(value, bool):
                return value
            if value.lower() in ("true", "yes", "1", "on"):
                return True
            if value.lower() in ("false", "no", "0", "off"):
                return False
            raise ValueError(
                f"{field_path}: unrecognised boolean value '{value}' — "
                "expected one of true/false/yes/no/1/0/on/off"
            )
        return value

    def _convert_types(self, value: Any) -> Any:
        """Convert strings to appropriate types (per-env-var global pass).

        String fields may get distorted here (e.g. '00123' -> 123).
        _dict_to_dataclass later restores the raw value for str fields
        from self._raw_config_after_env.
        """
        if isinstance(value, str):
            if value.lower() in ("true", "yes", "1", "on"):
                return True
            elif value.lower() in ("false", "no", "0", "off"):
                return False

            if value.isdigit():
                return int(value)

            # 음수 처리 추가
            if value.startswith("-") and value[1:].isdigit():
                return int(value)

            try:
                if "." in value:
                    return float(value)
            except ValueError:
                pass

        elif isinstance(value, dict):
            return {k: self._convert_types(v) for k, v in value.items()}

        elif isinstance(value, list):
            return [self._convert_types(item) for item in value]

        return value

    def load_config(self):
        """Load configuration file and apply environment variables"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._raw_config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"YAML file parsing error: {e}")

        self._processed_config = self._substitute_env_vars(self._raw_config)
        # Preserve raw env-var substituted values for string fields so
        # _dict_to_dataclass can restore the original value (e.g.
        # ADMIN_PASSWORD=00123 vs the int 123 that _convert_types produces).
        self._raw_config_after_env = self._processed_config
        self._processed_config = self._convert_types(self._processed_config)

        return self._create_config_instance()

    def _dict_to_dataclass(self, dc_type: type[_DC], section: dict) -> _DC:
        """Build a dataclass instance from a config dict section.

        Introspects dataclass fields and maps them to dict keys with
        the same name.  Missing keys fall back to the field default.
        Unknown keys in the section are silently ignored (see
        _warn_unknown_keys).

        For str-typed fields the value is looked up from the raw
        env-var substituted dict (_raw_config_after_env) so that the
        original string is preserved even when _convert_types has
        coerced '00123' to 123 or 'true' to True.
        """
        import dataclasses

        kwargs = {}
        for f in dataclasses.fields(dc_type):
            if f.name in section:
                value = section[f.name]
                # Restore raw string for str fields from pre-conversion data
                raw_env = getattr(self, "_raw_config_after_env", None)
                if f.type is str and raw_env:
                    raw = raw_env
                    for key in self._config_path_for_section(dc_type, f.name):
                        raw = raw.get(key, {}) if isinstance(raw, dict) else {}
                    raw_val = raw.get(f.name, value) if isinstance(raw, dict) else value
                    if isinstance(raw_val, str):
                        value = raw_val
                    elif not isinstance(value, str):
                        value = str(value)
                elif not isinstance(value, str) and f.type is not str:
                    pass  # already typed correctly
                elif isinstance(value, str) and f.type is not str:
                    value = self._convert_value(value, f.type, field_path=dc_type.__name__ + "." + f.name)
                elif f.type is str and not isinstance(value, str):
                    value = str(value)
                kwargs[f.name] = value
            elif f.default is not dataclasses.MISSING:
                kwargs[f.name] = f.default
            elif f.default_factory is not dataclasses.MISSING:
                kwargs[f.name] = f.default_factory()
        return dc_type(**kwargs)

    @staticmethod
    def _config_path_for_section(dc_type: type, field_name: str) -> tuple:
        """Map a dataclass type to its config section key path.

        Returns the sequence of dict keys to reach the raw config
        section that corresponds to this dataclass.
        """
        from .server.server import ServerConfig, ServerStartupConfig
        from .server.rcon import RconConfig
        from .server.rest_api import RestAPIConfig
        from .monitoring.monitoring import MonitoringConfig
        from .monitoring.backup import BackupConfig
        from .monitoring.idle_restart import IdleRestartConfig
        from .integration.discord import DiscordConfig
        from .integration.steamcmd import SteamCMDConfig
        from .game.gameplay import GameplayConfig
        from .game.items import ItemsConfig
        from .game.base_camp import BaseCampConfig
        from .game.guild import GuildConfig
        from .game.pal_settings import PalSettingsConfig
        from .game.building import BuildingConfig
        from .game.difficulty import DifficultyConfig
        from .palworld.engine import EngineConfig
        from .palworld.settings import PalworldSettings

        mapping = {
            ServerConfig: ("server",),
            ServerStartupConfig: ("server_startup",),
            RconConfig: ("rcon",),
            RestAPIConfig: ("rest_api",),
            MonitoringConfig: ("monitoring",),
            BackupConfig: ("backup",),
            IdleRestartConfig: ("monitoring", "idle_restart"),
            DiscordConfig: ("discord",),
            SteamCMDConfig: ("steamcmd",),
            GameplayConfig: ("gameplay",),
            ItemsConfig: ("items",),
            BaseCampConfig: ("base_camp",),
            GuildConfig: ("guild",),
            PalSettingsConfig: ("pal_settings",),
            BuildingConfig: ("building",),
            DifficultyConfig: ("difficulty",),
            EngineConfig: ("engine",),
            PalworldSettings: ("palworld_settings",),
        }
        return mapping.get(dc_type, ())

    @staticmethod
    def _warn_unknown_keys(section_name: str, dc_type: type, section: dict, logger=None) -> None:
        """Log a warning for unknown keys in a config section."""
        import dataclasses

        known = {f.name for f in dataclasses.fields(dc_type)}
        unknown = set(section.keys()) - known
        if unknown:
            msg = f"Unknown config key(s) in [{section_name}]: {', '.join(sorted(unknown))}"
            if logger:
                logger.warning(msg)
            else:
                import logging

                logging.getLogger("palworld.config").warning(msg)

    def _create_config_instance(self):
        """Create PalworldConfig instance from dictionary"""
        from .palworld.main import PalworldConfig
        from .server.server import ServerConfig, ServerStartupConfig
        from .server.rcon import RconConfig
        from .server.rest_api import RestAPIConfig
        from .monitoring.monitoring import MonitoringConfig
        from .monitoring.backup import BackupConfig
        from .monitoring.idle_restart import IdleRestartConfig
        from .integration.discord import DiscordConfig
        from .integration.steamcmd import SteamCMDConfig
        from .game.gameplay import GameplayConfig
        from .game.items import ItemsConfig
        from .game.base_camp import BaseCampConfig
        from .game.guild import GuildConfig
        from .game.pal_settings import PalSettingsConfig
        from .game.building import BuildingConfig
        from .game.difficulty import DifficultyConfig
        from .palworld.engine import EngineConfig
        from .palworld.settings import PalworldSettings

        config_dict = self._processed_config
        from pathlib import Path

        # --- Simple section-mapped configs ---
        simple_configs = [
            ("server", ServerConfig),
            ("rest_api", RestAPIConfig),
            ("rcon", RconConfig),
            ("server_startup", ServerStartupConfig),
            ("backup", BackupConfig),
            ("steamcmd", SteamCMDConfig),
            ("gameplay", GameplayConfig),
            ("items", ItemsConfig),
            ("base_camp", BaseCampConfig),
            ("guild", GuildConfig),
            ("pal_settings", PalSettingsConfig),
            ("building", BuildingConfig),
            ("difficulty", DifficultyConfig),
            ("engine", EngineConfig),
        ]
        configs: dict = {}
        for section_key, dc_type in simple_configs:
            section = config_dict.get(section_key, {})
            configs[section_key] = self._dict_to_dataclass(dc_type, section)
            self._warn_unknown_keys(section_key, dc_type, section)

        # --- MonitoringConfig with nested IdleRestartConfig ---
        monitoring_section = config_dict.get("monitoring", {})
        idle_restart_section = monitoring_section.get("idle_restart", {})
        idle_restart_config = self._dict_to_dataclass(IdleRestartConfig, idle_restart_section)
        monitoring_config = MonitoringConfig(
            mode=monitoring_section.get("mode", "both"),
            log_level=monitoring_section.get("log_level", "INFO"),
            metrics_interval=monitoring_section.get("metrics_interval", 60),
            enable_dashboard=monitoring_section.get("enable_dashboard", True),
            dashboard_port=monitoring_section.get("dashboard_port", 8080),
            log_format_style=monitoring_section.get("log_format_style", "simple"),
            idle_restart=idle_restart_config,
        )

        # --- DiscordConfig with nested events dict ---
        discord_section = config_dict.get("discord", {})
        discord_events = discord_section.get("events", {})
        discord_config = DiscordConfig(
            webhook_url=discord_section.get("webhook_url", ""),
            enabled=discord_section.get("enabled", False),
            mention_role=discord_section.get("mention_role", ""),
            events=(
                discord_events
                if discord_events
                else {
                    "server_start": True,
                    "server_stop": True,
                    "player_join": True,
                    "player_leave": True,
                    "backup_complete": True,
                    "errors": True,
                    "idle_restart": True,
                }
            ),
        )

        # --- ConfigPaths with Path() wrapper ---
        paths_section = config_dict.get("paths", {})
        paths_config = ConfigPaths(
            server_dir=Path(paths_section.get("server_dir", "/home/steam/palworld_server")),
            backup_dir=Path(paths_section.get("backup_dir", "/home/steam/backups")),
            log_dir=Path(paths_section.get("log_dir", "/home/steam/logs")),
            steamcmd_dir=Path(paths_section.get("steamcmd_dir", "/home/steam/steamcmd")),
        )

        # --- PalworldSettings with CamelCase keys ---
        palworld_settings_dict = config_dict.get("palworld_settings", {})
        palworld_settings_config = PalworldSettings(
            **{
                f.name: palworld_settings_dict.get(f.name, f.default)
                for f in __import__("dataclasses").fields(PalworldSettings)
            }
        )

        language = config_dict.get("language", "ko")

        return PalworldConfig(
            server=configs["server"],
            rest_api=configs["rest_api"],
            rcon=configs["rcon"],
            server_startup=configs["server_startup"],
            monitoring=monitoring_config,
            backup=configs["backup"],
            discord=discord_config,
            paths=paths_config,
            steamcmd=configs["steamcmd"],
            gameplay=configs["gameplay"],
            items=configs["items"],
            base_camp=configs["base_camp"],
            guild=configs["guild"],
            pal_settings=configs["pal_settings"],
            building=configs["building"],
            difficulty=configs["difficulty"],
            engine=configs["engine"],
            palworld_settings=palworld_settings_config,
            language=language,
        )

    def validate_config(self, config):
        """Validate configuration"""
        from .palworld.main import PalworldConfig

        if not (1024 <= config.server.port <= 65535):
            raise ValueError(f"Invalid server port: {config.server.port}")

        if not (1024 <= config.rest_api.port <= 65535):
            raise ValueError(f"Invalid REST API port: {config.rest_api.port}")

        if not (1 <= config.server.max_players <= 32):
            raise ValueError(f"Invalid max players count: {config.server.max_players}")

        valid_modes = ["logs", "prometheus", "both"]
        if config.monitoring.mode not in valid_modes:
            raise ValueError(f"Invalid monitoring mode: {config.monitoring.mode}")

        if config.discord.enabled and not config.discord.webhook_url:
            raise ValueError("Discord notifications enabled but webhook URL not set")

        valid_log_formats = ["text", "json"]
        if config.server_startup.log_format not in valid_log_formats:
            raise ValueError(f"Invalid log format: {config.server_startup.log_format}")

        if not (1024 <= config.server_startup.query_port <= 65535):
            raise ValueError(f"Invalid query port: {config.server_startup.query_port}")

        if config.server_startup.worker_threads_count < 0:
            raise ValueError(
                f"Invalid worker threads count: {config.server_startup.worker_threads_count}"
            )

        valid_languages = ["ko", "en", "ja"]
        if config.language not in valid_languages:
            raise ValueError(f"Invalid language: {config.language}. Supported: {valid_languages}")

        return True


_config_instance = None
_config_loader = None


def get_config(config_path: Optional[Union[str, Path]] = None):
    """Return global configuration instance (singleton pattern)"""
    global _config_instance, _config_loader

    if _config_instance is None:
        _config_loader = ConfigLoader(config_path)
        _config_instance = _config_loader.load_config()
        _config_loader.validate_config(_config_instance)

    return _config_instance


def reload_config():
    """Reload configuration"""
    global _config_instance

    if _config_loader is None:
        raise RuntimeError("Configuration loader not initialized")

    _config_instance = _config_loader.load_config()
    _config_loader.validate_config(_config_instance)

    return _config_instance
