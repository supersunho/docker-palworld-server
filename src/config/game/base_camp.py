#!/usr/bin/env python3
"""
Base camp configuration classes
"""

from dataclasses import dataclass


@dataclass
class BaseCampConfig:
    """Base camp configuration data class"""

    max_num: int = 128
    worker_max_num: int = 15
