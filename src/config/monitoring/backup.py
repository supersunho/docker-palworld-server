#!/usr/bin/env python3
"""
Backup configuration classes
"""

from dataclasses import dataclass


@dataclass
class BackupConfig:
    """Backup configuration data class with retention policies"""

    enabled: bool = True
    interval_seconds: int = 3600
    retention_days: int = 7
    retention_weeks: int = 4
    retention_months: int = 6
    compress: bool = True
    max_backups: int = 100
    cleanup_interval: int = 86400
