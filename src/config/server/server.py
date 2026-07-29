#!/usr/bin/env python3
"""
Server configuration classes
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ServerConfig:
    """Server configuration data class"""

    name: str = "Palworld Server"
    password: str = ""
    admin_password: str = ""
    max_players: int = 32
    port: int = 8211
    description: str = "A Palworld dedicated server"


@dataclass
class ServerStartupConfig:
    """Server startup options configuration for PalServer.sh execution"""

    use_performance_threads: bool = True
    disable_async_loading: bool = True
    use_multithread_for_ds: bool = True
    query_port: int = 27018
    enable_public_lobby: bool = False
    log_format: str = "text"
    worker_threads_count: int = 0
    additional_options: str = ""
