#!/usr/bin/env python3
"""
Guild configuration classes
"""

from dataclasses import dataclass


@dataclass
class GuildConfig:
    """Guild configuration data class"""

    player_max_num: int = 20
    auto_reset_guild_no_online_players: bool = False
    auto_reset_guild_time_no_online_players: float = 72.0
