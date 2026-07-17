#!/usr/bin/env python3
"""
Configuration loader module - Proxy for backward compatibility

This file serves as a compatibility layer that re-exports all configuration classes
from the new modular structure. New code should import directly from src.config.
"""

# Import all classes from the new package structure for backward compatibility
from src.config import (
    ConfigPaths,
    ConfigLoader,
    ServerConfig,
    ServerStartupConfig,
    RestAPIConfig,
    RconConfig,
    IdleRestartConfig,
    MonitoringConfig,
    BackupConfig,
    DiscordConfig,
    GameplayConfig,
    ItemsConfig,
    BaseCampConfig,
    GuildConfig,
    PalSettingsConfig,
    BuildingConfig,
    DifficultyConfig,
    SteamCMDConfig,
    EngineConfig,
    PalworldSettings,
    PalworldConfig,
)

# Also re-export the helper functions
from src.config.base import get_config, reload_config

# Keep the same public API for backward compatibility
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
    "get_config",
    "reload_config",
]
