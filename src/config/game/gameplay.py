#!/usr/bin/env python3
"""
Gameplay configuration classes
"""

from dataclasses import dataclass, field
from typing import Dict, Any


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
