#!/usr/bin/env python3
"""
Items and drops configuration classes
"""

from dataclasses import dataclass


@dataclass
class ItemsConfig:
    """Items and drops configuration data class"""

    drop_item_max_num: int = 3000
    drop_item_max_num_unko: int = 100
    drop_item_alive_max_hours: float = 1.0
