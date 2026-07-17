#!/usr/bin/env python3
"""
Monitoring configuration classes
"""

from dataclasses import dataclass, field
from typing import Dict, Any
from .idle_restart import IdleRestartConfig


@dataclass
class MonitoringConfig:
    """Monitoring configuration data class"""

    mode: str = "both"
    log_level: str = "INFO"
    metrics_interval: int = 60
    enable_dashboard: bool = True
    dashboard_port: int = 8080
    log_format_style: str = "simple"
    idle_restart: IdleRestartConfig = field(default_factory=IdleRestartConfig)
