"""
Shared test fixtures for Palworld server manager tests.

Provides mock configurations, mock clients, and async test support.
"""

import pytest
import asyncio
import json
import os
import tempfile
from pathlib import Path
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch

from src.config.base import ConfigLoader
from src.config.palworld.main import PalworldConfig
from src.config.server.server import ServerConfig, ServerStartupConfig
from src.config.server.rcon import RconConfig
from src.config.server.rest_api import RestAPIConfig
from src.config.monitoring.monitoring import MonitoringConfig
from src.config.monitoring.backup import BackupConfig
from src.config.monitoring.idle_restart import IdleRestartConfig
from src.config.integration.discord import DiscordConfig
from src.config.integration.steamcmd import SteamCMDConfig
from src.config.game.gameplay import GameplayConfig
from src.config.game.items import ItemsConfig
from src.config.game.base_camp import BaseCampConfig
from src.config.game.guild import GuildConfig
from src.config.game.pal_settings import PalSettingsConfig
from src.config.game.building import BuildingConfig
from src.config.game.difficulty import DifficultyConfig
from src.config.palworld.engine import EngineConfig
from src.config.palworld.settings import PalworldSettings
from src.container import ServiceContainer
from src.protocols import IProcessManager, IServerAPI, ServerInfo

# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def sample_yaml():
    """Minimal valid YAML config content."""
    return """server:
  name: "Test Server"
  admin_password: "test123"
  max_players: 16
  port: 8211

rest_api:
  enabled: true
  port: 8212
  host: localhost

rcon:
  enabled: true
  port: 25575
  host: localhost

monitoring:
  mode: logs
  log_level: DEBUG

backup:
  enabled: false

discord:
  enabled: false

steamcmd:
  app_id: 2394010

paths:
  server_dir: /tmp/palworld_test
  backup_dir: /tmp/palworld_test/backups
  log_dir: /tmp/palworld_test/logs
  steamcmd_dir: /tmp/palworld_test/steamcmd

language: ko
"""


@pytest.fixture
def config_loader(sample_yaml, tmp_path):
    """ConfigLoader with a temporary YAML file."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(sample_yaml, encoding="utf-8")
    return ConfigLoader(config_file)


@pytest.fixture
def palworld_config():
    """Default PalworldConfig instance for unit tests."""
    return PalworldConfig(
        server=ServerConfig(
            name="Test Server", admin_password="test123", max_players=16, port=8211
        ),
        rest_api=RestAPIConfig(enabled=True, port=8212, host="localhost"),
        rcon=RconConfig(enabled=True, port=25575, host="localhost"),
        server_startup=ServerStartupConfig(),
        monitoring=MonitoringConfig(
            mode="logs",
            log_level="DEBUG",
            idle_restart=IdleRestartConfig(enabled=True, idle_minutes=30),
        ),
        backup=BackupConfig(enabled=False),
        discord=DiscordConfig(enabled=False),
        paths=MagicMock(
            server_dir=Path("/tmp/palworld_test"),
            backup_dir=Path("/tmp/palworld_test/backups"),
            log_dir=Path("/tmp/palworld_test/logs"),
            steamcmd_dir=Path("/tmp/palworld_test/steamcmd"),
        ),
        steamcmd=SteamCMDConfig(app_id=2394010),
        gameplay=GameplayConfig(),
        items=ItemsConfig(),
        base_camp=BaseCampConfig(),
        guild=GuildConfig(),
        pal_settings=PalSettingsConfig(),
        building=BuildingConfig(),
        difficulty=DifficultyConfig(),
        engine=EngineConfig(),
        palworld_settings=PalworldSettings(),
        language="ko",
    )


@pytest.fixture
def mock_logger():
    """MagicMock structured logger."""
    return MagicMock()


@pytest.fixture
def container():
    """Empty ServiceContainer for DI tests."""
    return ServiceContainer()


@pytest.fixture
def mock_rest_client():
    """Mock RestAPIClient with async context manager support."""
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.session = MagicMock()
    client.session.closed = False
    client.get_server_info = AsyncMock(
        return_value={
            "name": "Test Server",
            "players": 3,
            "max_players": 16,
            "uptime": "1h 30m",
            "version": "v0.1.0",
        }
    )
    client.get_players = AsyncMock(
        return_value=[
            {"name": "Player1", "playeruid": "uid1"},
            {"name": "Player2", "playeruid": "uid2"},
        ]
    )
    client.get_server_settings = AsyncMock(return_value={"difficulty": "None"})
    client.get_server_metrics = AsyncMock(return_value={"cpu": 45.0})
    client.announce_message = AsyncMock(return_value=True)
    client.kick_player = AsyncMock(return_value=True)
    client.ban_player = AsyncMock(return_value=True)
    client.unban_player = AsyncMock(return_value=True)
    client.save_world = AsyncMock(return_value=True)
    client.shutdown_server = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_rcon_client():
    """Mock RconClient with async context manager support."""
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get_server_info = AsyncMock(return_value="SERVER INFO: Test Server, Players: 3/16")
    client.get_players = AsyncMock(
        return_value="name,playeruid,steamid\nPlayer1,uid1,steam1\nPlayer2,uid2,steam2"
    )
    client.announce_message = AsyncMock(return_value=True)
    client.kick_player = AsyncMock(return_value=True)
    client.ban_player = AsyncMock(return_value=True)
    client.save_world = AsyncMock(return_value=True)
    client.shutdown_server = AsyncMock(return_value=True)
    client.get_server_settings = AsyncMock(return_value="Difficulty=None")
    client.execute_custom_command = AsyncMock(return_value="OK")
    return client


@pytest.fixture
def mock_process_manager():
    """Mock ProcessManager implementing IProcessManager protocol."""
    pm = MagicMock(spec=IProcessManager)
    pm.is_server_running = MagicMock(return_value=True)
    pm.start_server = AsyncMock(return_value=True)
    pm.stop_server = AsyncMock(return_value=True)
    pm.get_server_status = MagicMock(return_value={"running": True, "pid": 12345, "uptime": 3600})
    pm.get_startup_options_summary = MagicMock(
        return_value={
            "performance_optimization": True,
            "query_port": 27018,
            "public_lobby": False,
            "log_format": "text",
            "worker_threads": 4,
            "additional_options": "",
            "generated_options": ["-useperfthreads"],
            "options_count": 1,
        }
    )
    return pm


@pytest.fixture
def mock_api_facade():
    """Mock ServerAPIFacade implementing IServerAPI protocol."""
    api = MagicMock(spec=IServerAPI)
    api.get_server_info = AsyncMock(
        return_value=ServerInfo(
            name="Test Server",
            players=3,
            max_players=16,
            uptime="1h 30m",
            version="v0.1.0",
            ip="127.0.0.1",
            port=8211,
        )
    )
    api.get_players = AsyncMock(
        return_value=[
            {"name": "Player1", "playeruid": "uid1"},
            {"name": "Player2", "playeruid": "uid2"},
        ]
    )
    api.announce = AsyncMock(return_value=True)
    api.save_world = AsyncMock(return_value=True)
    api.kick_player = AsyncMock(return_value=True)
    api.ban_player = AsyncMock(return_value=True)
    api.unban_player = AsyncMock(return_value=True)
    api.shutdown_server = AsyncMock(return_value=True)
    api.get_client_status = MagicMock(return_value={"rest_available": True, "rcon_available": True})
    api.api_get_players = AsyncMock(return_value=[{"name": "Player1"}])
    api.api_get_server_info = AsyncMock(return_value={"name": "Test"})
    api.api_get_server_metrics = AsyncMock(return_value={"cpu": 45.0})
    api.get_api_client = MagicMock(return_value=MagicMock())
    api.get_rcon_client = MagicMock(return_value=MagicMock())
    return api


@pytest.fixture
def mock_player_monitor():
    """Mock PlayerMonitor."""
    monitor = MagicMock()
    monitor.get_current_player_count = MagicMock(return_value=3)
    monitor.get_current_players = MagicMock(return_value={"Player1", "Player2", "Player3"})
    monitor.is_monitoring_active = MagicMock(return_value=True)
    monitor.add_event_callback = MagicMock()
    monitor.remove_event_callback = MagicMock()
    monitor.clear_event_callbacks = MagicMock()
    monitor.clear_user_callbacks = MagicMock()
    monitor.start_monitoring = AsyncMock()
    monitor.stop_monitoring = AsyncMock()
    return monitor


@pytest.fixture
def mock_event_dispatcher():
    """Mock EventDispatcher."""
    dispatcher = MagicMock()
    dispatcher.handle_player_event = AsyncMock()
    dispatcher.handle_server_event = AsyncMock()
    dispatcher.handle_backup_completion = AsyncMock()
    dispatcher.handle_error_event = AsyncMock()
    return dispatcher


# ── Async fixtures ──────────────────────────────────────────────────────

# ── Temp config file fixture ────────────────────────────────────────────


@pytest.fixture
def temp_config_file(tmp_path):
    """Create a temporary config directory with a valid YAML file."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "test.yaml"
    config_file.write_text(
        """server:
  name: "Temp Test Server"
  admin_password: "pass123"
  max_players: 8
  port: 8211
language: ko
""",
        encoding="utf-8",
    )
    return config_file
