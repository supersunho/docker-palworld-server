#!/usr/bin/env python3
"""
Configuration package initialization

Re-exports all configuration classes for backward compatibility.
"""

# Re-export base classes
from .base import ConfigPaths, ConfigLoader

# Re-export server configuration classes
from .server.server import ServerConfig, ServerStartupConfig
from .server.rcon import RconConfig
from .server.rest_api import RestAPIConfig

# Re-export game configuration classes
from .game.gameplay import GameplayConfig
from .game.items import ItemsConfig
from .game.base_camp import BaseCampConfig
from .game.guild import GuildConfig
from .game.pal_settings import PalSettingsConfig
from .game.building import BuildingConfig
from .game.difficulty import DifficultyConfig

# Re-export monitoring configuration classes
from .monitoring.monitoring import MonitoringConfig
from .monitoring.backup import BackupConfig
from .monitoring.idle_restart import IdleRestartConfig

# Re-export integration configuration classes
from .integration.discord import DiscordConfig
from .integration.steamcmd import SteamCMDConfig

# Re-export palworld configuration classes
from .palworld.engine import EngineConfig
from .palworld.settings import PalworldSettings
from .palworld.main import PalworldConfig

# Make all classes available in the package namespace
__all__ = [
    "ConfigPaths",
    "ConfigLoader",
    "ServerConfig",
    "ServerStartupConfig",
    "RestAPIConfig",
    "RconConfig",
    "IdleRestartConfig",
    "MonitoringConfig",
    "BackupConfig",
    "DiscordConfig",
    "GameplayConfig",
    "ItemsConfig",
    "BaseCampConfig",
    "GuildConfig",
    "PalSettingsConfig",
    "BuildingConfig",
    "DifficultyConfig",
    "SteamCMDConfig",
    "EngineConfig",
    "PalworldSettings",
    "PalworldConfig",
]
