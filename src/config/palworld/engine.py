#!/usr/bin/env python3
"""
Engine.ini configuration classes
"""

from dataclasses import dataclass


@dataclass
class EngineConfig:
    """Engine.ini configuration data class"""

    lan_server_max_tick_rate: int = 120
    net_server_max_tick_rate: int = 120
    configured_internet_speed: int = 104857600
    configured_lan_speed: int = 104857600
    max_client_rate: int = 104857600
    max_internet_client_rate: int = 104857600
    smooth_frame_rate: bool = True
    use_fixed_frame_rate: bool = False
    min_desired_frame_rate: float = 60.0
    fixed_frame_rate: float = 120.0
    net_client_ticks_per_second: int = 120
    frame_rate_lower_bound: float = 30.0
    frame_rate_upper_bound: float = 120.0
