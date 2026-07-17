#!/usr/bin/env python3
"""
Pal and gameplay rate configuration classes
"""

from dataclasses import dataclass


@dataclass
class PalSettingsConfig:
    """Pal and gameplay rate configuration data class"""

    egg_default_hatching_time: float = 72.0
    work_speed_rate: float = 1.0
    day_time_speed_rate: float = 1.0
    night_time_speed_rate: float = 1.0
    exp_rate: float = 1.0
    pal_capture_rate: float = 1.0
    pal_spawn_num_rate: float = 1.0
    pal_damage_rate_attack: float = 1.0
    pal_damage_rate_defense: float = 1.0
    pal_stomach_decrease_rate: float = 1.0
    pal_stamina_decrease_rate: float = 1.0
    pal_auto_hp_regene_rate: float = 1.0
    pal_auto_hp_regene_rate_in_sleep: float = 1.0
    player_damage_rate_attack: float = 1.0
    player_damage_rate_defense: float = 1.0
    player_stomach_decrease_rate: float = 1.0
    player_stamina_decrease_rate: float = 1.0
    player_auto_hp_regene_rate: float = 1.0
    player_auto_hp_regene_rate_in_sleep: float = 1.0
