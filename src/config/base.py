#!/usr/bin/env python3
"""
Base configuration classes
"""

import os
import re
import types
import yaml
from pathlib import Path
from typing import Any, Dict, Optional, Union, TypeVar, get_args, get_origin, get_type_hints
from dataclasses import dataclass, field
import dataclasses
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

    def _convert_value(self, value: Any, target_type: Any, field_path: str = "") -> Any:
        """Convert a value according to a dataclass field's declared type.

        Raises ValueError with field_path context on conversion failure.
        """
        origin = get_origin(target_type)
        if origin in (Union, types.UnionType):
            union_types = get_args(target_type)
            if value is None and type(None) in union_types:
                return None
            if isinstance(value, str) and str in union_types:
                return value

            conversion_errors = []
            for union_type in union_types:
                if union_type is type(None):
                    continue
                try:
                    return self._convert_value(value, union_type, field_path)
                except (TypeError, ValueError) as error:
                    conversion_errors.append(error)
            raise ValueError(f"{field_path}: cannot convert '{value}' to {target_type}") from (
                conversion_errors[-1] if conversion_errors else None
            )

        if target_type is Any or target_type is None:
            return value

        if value is None:
            return None

        if target_type is str:
            return value if isinstance(value, str) else str(value)

        if target_type is int:
            try:
                return int(value)
            except (ValueError, TypeError) as error:
                raise ValueError(f"{field_path}: cannot convert '{value}' to int") from error

        if target_type is float:
            try:
                return float(value)
            except (ValueError, TypeError) as error:
                raise ValueError(f"{field_path}: cannot convert '{value}' to float") from error

        if target_type is bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, str) and value.lower() in ("true", "yes", "1", "on"):
                return True
            if isinstance(value, str) and value.lower() in ("false", "no", "0", "off"):
                return False
            if isinstance(value, (int, float)):
                return bool(value)
            raise ValueError(
                f"{field_path}: unrecognised boolean value '{value}' — "
                "expected one of true/false/yes/no/1/0/on/off"
            )

        if target_type is Path:
            try:
                return value if isinstance(value, Path) else Path(value)
            except (TypeError, ValueError) as error:
                raise ValueError(f"{field_path}: cannot convert '{value}' to Path") from error

        if isinstance(target_type, type) and dataclasses.is_dataclass(target_type):
            if isinstance(value, target_type):
                return value
            if isinstance(value, dict):
                return self._dict_to_dataclass(target_type, value, field_path)
            raise ValueError(f"{field_path}: expected a mapping for {target_type.__name__}")

        if origin is list:
            if isinstance(value, str):
                value = yaml.safe_load(value)
            if not isinstance(value, list):
                raise ValueError(f"{field_path}: expected a list")
            item_type = get_args(target_type)[0] if get_args(target_type) else Any
            return [
                self._convert_value(item, item_type, f"{field_path}[{index}]")
                for index, item in enumerate(value)
            ]

        if origin is dict:
            if isinstance(value, str):
                value = yaml.safe_load(value)
            if not isinstance(value, dict):
                raise ValueError(f"{field_path}: expected a mapping")
            key_type, item_type = get_args(target_type) or (Any, Any)
            return {
                self._convert_value(key, key_type, f"{field_path}.<key>"): self._convert_value(
                    item, item_type, f"{field_path}.{key}"
                )
                for key, item in value.items()
            }

        return value

    def _convert_types(self, value: Any) -> Any:
        """Legacy recursive lexical conversion helper.

        Configuration loading no longer calls this global pass because it cannot
        distinguish lexical strings from values that belong to numeric fields.
        It remains available for backwards compatibility with callers that use
        this private helper directly.
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
        # Keep the substituted tree intact so field-aware conversion can decide
        # whether each string belongs to a string, numeric, boolean, or nested field.
        self._raw_config_after_env = self._processed_config

        return self._create_config_instance()

    def _dict_to_dataclass(self, dc_type: type[_DC], section: dict, field_prefix: str = "") -> _DC:
        """Build a dataclass instance from a config dict section.

        Introspects dataclass fields and maps them to dict keys with
        the same name.  Missing keys fall back to the field default.
        Unknown keys in the section are silently ignored (see
        _warn_unknown_keys).

        Values are converted according to each field's declared type, including
        nested dataclasses and typed containers.
        """
        kwargs = {}
        try:
            type_hints = get_type_hints(dc_type)
        except (NameError, TypeError):
            type_hints = {}

        for f in dataclasses.fields(dc_type):
            if f.name in section:
                value = section[f.name]
                field_path = ".".join(part for part in (field_prefix, f.name) if part)
                value = self._convert_value(
                    value, type_hints.get(f.name, f.type), field_path=field_path
                )
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
        monitoring_config = self._dict_to_dataclass(MonitoringConfig, monitoring_section)

        # --- DiscordConfig with nested events dict ---
        discord_section = dict(config_dict.get("discord", {}))
        if not discord_section.get("events"):
            discord_section.pop("events", None)
        discord_config = self._dict_to_dataclass(DiscordConfig, discord_section)

        # --- ConfigPaths with Path() wrapper ---
        paths_section = config_dict.get("paths", {})
        paths_config = self._dict_to_dataclass(ConfigPaths, paths_section)

        # --- PalworldSettings with CamelCase keys ---
        palworld_settings_dict = config_dict.get("palworld_settings", {})
        palworld_settings_config = self._dict_to_dataclass(PalworldSettings, palworld_settings_dict)

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
