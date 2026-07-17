#!/usr/bin/env python3
"""
Building and collection configuration classes
"""

from dataclasses import dataclass


@dataclass
class BuildingConfig:
    """Building and collection configuration data class"""

    build_object_damage_rate: float = 1.0
    build_object_deterioration_damage_rate: float = 1.0
    collection_drop_rate: float = 1.0
    collection_object_hp_rate: float = 1.0
    collection_object_respawn_speed_rate: float = 1.0
    enemy_drop_item_rate: float = 1.0
