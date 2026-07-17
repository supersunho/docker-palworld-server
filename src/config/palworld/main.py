#!/usr/bin/env python3
"""
Complete Palworld configuration
"""

from dataclasses import dataclass, field
from pathlib import Path
from ..base import ConfigPaths
from ..server.server import ServerConfig, ServerStartupConfig
from ..server.rest_api import RestAPIConfig
from ..server.rcon import RconConfig
from ..monitoring.monitoring import MonitoringConfig
from ..monitoring.backup import BackupConfig
from ..integration.discord import DiscordConfig
from ..integration.steamcmd import SteamCMDConfig
from ..game.gameplay import GameplayConfig
from ..game.items import ItemsConfig
from ..game.base_camp import BaseCampConfig
from ..game.guild import GuildConfig
from ..game.pal_settings import PalSettingsConfig
from ..game.building import BuildingConfig
from ..game.difficulty import DifficultyConfig
from .engine import EngineConfig
from .settings import PalworldSettings


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
    language: str = "ko"
