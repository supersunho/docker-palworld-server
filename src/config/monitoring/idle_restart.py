#!/usr/bin/env python3
"""
Idle restart/pause configuration classes
"""

from dataclasses import dataclass
from typing import Literal


@dataclass
class IdleRestartConfig:
    """Idle restart/pause configuration

    Attributes:
        enabled: Whether idle management is enabled.
        idle_minutes: Minutes of inactivity before action is triggered.
        mode: Action to take — 'restart' (full restart) or 'pause' (SIGSTOP/SIGCONT).
    """

    enabled: bool = True
    idle_minutes: int = 30
    mode: str = "restart"  # "restart" | "pause"
