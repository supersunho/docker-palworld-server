"""Tests for the configuration system."""

import os
import yaml
import pytest
from pathlib import Path
from unittest.mock import patch

from src.config.base import ConfigLoader, get_config, reload_config
from src.config.palworld.main import PalworldConfig
from src.config.server.server import ServerConfig, ServerStartupConfig
from src.config.server.rcon import RconConfig
from src.config.server.rest_api import RestAPIConfig

pytestmark = pytest.mark.unit


class TestConfigLoader:
    """FS-1.1.x: Configuration loader behavior."""

    def test_load_valid_yaml(self, config_loader):
        """FS-1.1.1: Load YAML config from path."""
        config = config_loader.load_config()
        assert isinstance(config, PalworldConfig)
        assert config.server.name == "Test Server"

    def test_env_var_substitution(self, config_loader, tmp_path):
        """FS-1.1.2: ${ENV_VAR:default} substitution."""
        config_file = tmp_path / "env_test.yaml"
        config_file.write_text(
            """server:
  name: "${TEST_SERVER_NAME:DefaultName}"
  max_players: ${TEST_MAX_PLAYERS:16}
language: ko
""",
            encoding="utf-8",
        )
        loader = ConfigLoader(config_file)
        config = loader.load_config()
        assert config.server.name == "DefaultName"
        assert config.server.max_players == 16

    def test_env_var_override(self, config_loader, tmp_path):
        """FS-1.1.2: Environment variable override via ${ENV_VAR}."""
        config_file = tmp_path / "env_override.yaml"
        config_file.write_text(
            """server:
  name: "${TEST_SERVER_NAME_OVERRIDE:Default}"
language: ko
""",
            encoding="utf-8",
        )
        with patch.dict(os.environ, {"TEST_SERVER_NAME_OVERRIDE": "EnvName"}):
            loader = ConfigLoader(config_file)
            config = loader.load_config()
            assert config.server.name == "EnvName"

    def test_type_conversion_bool(self, tmp_path):
        """FS-1.1.3: String-to-bool conversion for true/false/yes/no/1/0/on/off."""
        config_file = tmp_path / "type_test.yaml"
        config_file.write_text(
            """rest_api:
  enabled: "true"
rcon:
  enabled: "false"
monitoring:
  mode: logs
discord:
  enabled: "yes"
backup:
  enabled: "no"
steamcmd:
  app_id: 2394010
language: ko
paths:
  server_dir: /tmp
  backup_dir: /tmp
  log_dir: /tmp
  steamcmd_dir: /tmp
server:
  name: Test
  admin_password: pass
  max_players: 8
  port: 8211
""",
            encoding="utf-8",
        )
        loader = ConfigLoader(config_file)
        config = loader.load_config()
        assert config.rest_api.enabled is True
        assert config.rcon.enabled is False
        assert config.discord.enabled is True
        assert config.backup.enabled is False

    def test_type_conversion_int_float(self, tmp_path):
        """FS-1.1.3: String-to-int and string-to-float conversion."""
        config_file = tmp_path / "type_int.yaml"
        config_file.write_text(
            """server:
  name: Test
  admin_password: pass
  max_players: "16"
  port: "8211"
monitoring:
  mode: logs
discord:
  enabled: false
steamcmd:
  app_id: 2394010
paths:
  server_dir: /tmp
  backup_dir: /tmp
  log_dir: /tmp
  steamcmd_dir: /tmp
language: ko
""",
            encoding="utf-8",
        )
        loader = ConfigLoader(config_file)
        config = loader.load_config()
        assert config.server.max_players == 16
        assert config.server.port == 8211

    def test_file_not_found(self, tmp_path):
        """FS-1.1.1: Raises FileNotFoundError for missing config."""
        loader = ConfigLoader(tmp_path / "nonexistent.yaml")
        with pytest.raises(FileNotFoundError):
            loader.load_config()

    def test_validate_valid_config(self, config_loader):
        """FS-1.1.4: Valid config passes validation."""
        config = config_loader.load_config()
        assert config_loader.validate_config(config) is True

    def test_validate_invalid_port(self, config_loader):
        """FS-1.1.4: Invalid port raises ValueError."""
        config_loader._processed_config = {
            "server": {"name": "Test", "admin_password": "pass", "max_players": 8, "port": 80},
            "rest_api": {"enabled": True, "port": 8212, "host": "localhost"},
            "rcon": {"enabled": False, "port": 25575, "host": "localhost"},
            "server_startup": {
                "query_port": 27018,
                "log_format": "text",
                "worker_threads_count": 4,
            },
            "monitoring": {
                "mode": "logs",
                "log_level": "INFO",
                "idle_restart": {"enabled": True, "idle_minutes": 30},
            },
            "backup": {"enabled": False},
            "discord": {"enabled": False},
            "steamcmd": {"app_id": 2394010},
            "paths": {},
            "gameplay": {},
            "items": {},
            "base_camp": {},
            "guild": {},
            "pal_settings": {},
            "building": {},
            "difficulty": {},
            "engine": {},
            "palworld_settings": {},
            "language": "ko",
        }
        with pytest.raises(ValueError, match="Invalid server port"):
            config = config_loader._create_config_instance()
            config_loader.validate_config(config)

    def test_validate_invalid_language(self, config_loader):
        """FS-1.1.4: Invalid language raises ValueError."""
        config_loader._processed_config = {
            "server": {"name": "Test", "admin_password": "pass", "max_players": 8, "port": 8211},
            "rest_api": {"enabled": True, "port": 8212, "host": "localhost"},
            "rcon": {"enabled": False, "port": 25575, "host": "localhost"},
            "server_startup": {
                "query_port": 27018,
                "log_format": "text",
                "worker_threads_count": 4,
            },
            "monitoring": {
                "mode": "logs",
                "log_level": "INFO",
                "idle_restart": {"enabled": True, "idle_minutes": 30},
            },
            "backup": {"enabled": False},
            "discord": {"enabled": False},
            "steamcmd": {"app_id": 2394010},
            "paths": {},
            "gameplay": {},
            "items": {},
            "base_camp": {},
            "guild": {},
            "pal_settings": {},
            "building": {},
            "difficulty": {},
            "engine": {},
            "palworld_settings": {},
            "language": "xx",
        }
        config = config_loader._create_config_instance()
        with pytest.raises(ValueError, match="Invalid language"):
            config_loader.validate_config(config)

    def test_singleton_get_config(self, config_loader, tmp_path):
        """FS-1.1.5: get_config() returns the same instance."""
        config_file = tmp_path / "singleton_test.yaml"
        config_file.write_text(
            """server:
  name: SingletonTest
  admin_password: pass
  max_players: 8
  port: 8211
monitoring:
  mode: logs
discord:
  enabled: false
steamcmd:
  app_id: 2394010
paths:
  server_dir: /tmp
  backup_dir: /tmp
  log_dir: /tmp
  steamcmd_dir: /tmp
language: ko
""",
            encoding="utf-8",
        )

        with (
            patch("src.config.base._config_instance", None),
            patch("src.config.base._config_loader", None),
        ):
            c1 = get_config(config_file)
            c2 = get_config(config_file)
            assert c1 is c2

    def test_reload_config(self, config_loader, tmp_path):
        """FS-1.1.5: reload_config() returns new instance."""
        config_file = tmp_path / "reload_test.yaml"
        config_file.write_text(
            """server:
  name: First
  admin_password: pass
  max_players: 8
  port: 8211
monitoring:
  mode: logs
discord:
  enabled: false
steamcmd:
  app_id: 2394010
paths:
  server_dir: /tmp
  backup_dir: /tmp
  log_dir: /tmp
  steamcmd_dir: /tmp
language: ko
""",
            encoding="utf-8",
        )

        with (
            patch("src.config.base._config_instance", None),
            patch("src.config.base._config_loader", None),
        ):
            first = get_config(config_file)
            config_file.write_text(
                """server:
  name: Second
  admin_password: pass
  max_players: 8
  port: 8211
monitoring:
  mode: logs
discord:
  enabled: false
steamcmd:
  app_id: 2394010
paths:
  server_dir: /tmp
  backup_dir: /tmp
  log_dir: /tmp
  steamcmd_dir: /tmp
language: ko
""",
                encoding="utf-8",
            )
            second = reload_config()
            assert first is not second
            assert second.server.name == "Second"


class TestConfigDataclasses:
    """FS-1.2: Config dataclass defaults."""

    def test_server_config_defaults(self):
        config = ServerConfig()
        assert config.name == "Palworld Server"
        assert config.max_players == 32
        assert config.port == 8211

    def test_server_startup_config_defaults(self):
        config = ServerStartupConfig()
        assert config.use_performance_threads is True
        assert config.query_port == 27018

    def test_rcon_config_defaults(self):
        config = RconConfig()
        assert config.enabled is False
        assert config.port == 25575

    def test_rest_api_config_defaults(self):
        config = RestAPIConfig()
        assert config.enabled is True
        assert config.port == 8212


class TestConfigLoaderBackwardsCompat:
    """FS-1.3: config_loader.py re-exports."""

    def test_reimport_from_config_loader(self):
        from src.config_loader import (
            ConfigLoader,
            ServerConfig,
            PalworldConfig,
            get_config,
            reload_config,
        )

        assert ConfigLoader is not None
        assert ServerConfig is not None
        assert PalworldConfig is not None
        assert callable(get_config)
        assert callable(reload_config)


class TestConfigLoaderEdgeCases:
    """Additional edge-case tests for ConfigLoader coverage."""

    def test_init_without_path_defaults_to_default_yaml(self):
        """ConfigLoader() without path uses default.yaml location."""
        loader = ConfigLoader()
        assert loader.config_path.name == "default.yaml"
        assert loader.config_path.parent.name == "config"

    def test_yaml_parse_error_raises(self, tmp_path):
        """Invalid YAML content raises YAMLError."""
        config_file = tmp_path / "bad.yaml"
        config_file.write_text("{invalid: yaml: broken", encoding="utf-8")
        loader = ConfigLoader(config_file)
        with pytest.raises(yaml.YAMLError, match="YAML file parsing error"):
            loader.load_config()

    def test_validate_config_invalid_rest_api_port(self, config_loader):
        config = config_loader.load_config()
        config.rest_api.port = 80
        with pytest.raises(ValueError, match="Invalid REST API port"):
            config_loader.validate_config(config)

    def test_validate_config_invalid_max_players(self, config_loader):
        config = config_loader.load_config()
        config.server.max_players = 0
        with pytest.raises(ValueError, match="Invalid max players count"):
            config_loader.validate_config(config)

    def test_validate_config_invalid_monitoring_mode(self, config_loader):
        config = config_loader.load_config()
        config.monitoring.mode = "unknown"
        with pytest.raises(ValueError, match="Invalid monitoring mode"):
            config_loader.validate_config(config)

    def test_validate_config_discord_enabled_no_webhook(self, config_loader):
        config = config_loader.load_config()
        config.discord.enabled = True
        config.discord.webhook_url = ""
        with pytest.raises(
            ValueError, match="Discord notifications enabled but webhook URL not set"
        ):
            config_loader.validate_config(config)

    def test_validate_config_invalid_log_format(self, config_loader):
        config = config_loader.load_config()
        config.server_startup.log_format = "binary"
        with pytest.raises(ValueError, match="Invalid log format"):
            config_loader.validate_config(config)

    def test_validate_config_invalid_query_port(self, config_loader):
        config = config_loader.load_config()
        config.server_startup.query_port = 99
        with pytest.raises(ValueError, match="Invalid query port"):
            config_loader.validate_config(config)

    def test_validate_config_invalid_worker_threads(self, config_loader):
        config = config_loader.load_config()
        config.server_startup.worker_threads_count = -1
        with pytest.raises(ValueError, match="Invalid worker threads count"):
            config_loader.validate_config(config)

    def test_reload_config_not_initialized(self):
        with (
            patch("src.config.base._config_loader", None),
            patch("src.config.base._config_instance", None),
        ):
            with pytest.raises(RuntimeError, match="Configuration loader not initialized"):
                reload_config()

    def test_convert_types_bool_edge_cases(self):
        loader = ConfigLoader.__new__(ConfigLoader)
        assert loader._convert_types("yes") is True
        assert loader._convert_types("on") is True
        assert loader._convert_types("1") is True
        assert loader._convert_types("no") is False
        assert loader._convert_types("off") is False
        assert loader._convert_types("0") is False

    def test_convert_types_int_negative(self):
        loader = ConfigLoader.__new__(ConfigLoader)
        assert loader._convert_types("-5") == -5

    def test_convert_types_float_value_error(self):
        loader = ConfigLoader.__new__(ConfigLoader)
        result = loader._convert_types("not.a.float")
        assert result == "not.a.float"
