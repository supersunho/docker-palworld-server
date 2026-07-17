#!/usr/bin/env python3
"""
REST API configuration classes
"""

from dataclasses import dataclass


@dataclass
class RestAPIConfig:
    """REST API configuration data class"""

    enabled: bool = True
    port: int = 8212
    host: str = "localhost"
