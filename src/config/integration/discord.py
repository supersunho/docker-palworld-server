#!/usr/bin/env python3
"""
Discord configuration classes
"""

from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class DiscordConfig:
    """Discord configuration data class"""

    webhook_url: str = ""
    enabled: bool = False
    mention_role: str = ""
    events: Dict[str, bool] = field(
        default_factory=lambda: {
            "server_start": True,
            "server_stop": True,
            "player_join": True,
            "player_leave": True,
            "backup_complete": True,
            "errors": True,
            "idle_restart": True,
            "update": True,
        }
    )
