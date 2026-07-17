#!/usr/bin/env python3
"""
Difficulty configuration classes
"""

from dataclasses import dataclass


@dataclass
class DifficultyConfig:
    """Difficulty configuration data class"""

    level: str = "None"
    death_penalty: str = "All"
