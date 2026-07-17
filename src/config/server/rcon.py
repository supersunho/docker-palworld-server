#!/usr/bin/env python3
"""
RCON configuration classes
"""

from dataclasses import dataclass


@dataclass
class RconConfig:
    """RCON configuration data class"""

    enabled: bool = False
    port: int = 25575
    host: str = "localhost"
