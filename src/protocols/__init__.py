#!/usr/bin/env python3
"""
Protocol definitions for dependency injection
"""

from typing import Protocol, runtime_checkable, Dict, List, Any, Optional
from dataclasses import dataclass


@runtime_checkable
class IProcessManager(Protocol):
    """Process management interface"""

    def is_server_running(self) -> bool:
        """Check if server is currently running"""
        ...

    async def start_server(self) -> bool:
        """Start Palworld server with dynamic configuration options"""
        ...

    async def stop_server(self, message: str = "Server is shutting down", api_client=None) -> bool:
        """Stop Palworld server gracefully and clean up zombie processes"""
        ...

    def get_server_status(self) -> Dict[str, Any]:
        """Get detailed server process status"""
        ...

    def get_startup_options_summary(self) -> Dict[str, Any]:
        """Get summary of current startup options configuration"""
        ...


@runtime_checkable
class IConfigProvider(Protocol):
    """Configuration provider interface"""

    def load_config(self):
        """Load configuration file and apply environment variables"""
        ...

    def validate_config(self, config) -> bool:
        """Validate configuration"""
        ...


@dataclass
class ServerInfo:
    """Server information data class"""

    name: str = ""
    players: int = 0
    max_players: int = 0
    uptime: str = ""
    version: str = ""
    ip: str = ""
    port: int = 0
    info: str = ""


@runtime_checkable
class IServerAPI(Protocol):
    """Server API interface"""

    async def get_server_info(self) -> Optional[ServerInfo]:
        """Get server information using available API"""
        ...

    async def get_players(self) -> Optional[List[Dict[str, Any]]]:
        """Get online player list using available API"""
        ...

    async def announce(self, message: str) -> bool:
        """Announce message to all players using available API"""
        ...

    async def save_world(self) -> bool:
        """Save world data using available API"""
        ...

    async def kick_player(self, player_identifier: str, message: str = "") -> bool:
        """Kick player from server using available API"""
        ...

    async def ban_player(self, player_identifier: str, message: str = "") -> bool:
        """Ban player from server using available API"""
        ...

    async def unban_player(self, player_identifier: str) -> bool:
        """Unban player from server using available API"""
        ...

    async def shutdown_server(self, waittime: int = 1, message: str = "Server shutdown") -> bool:
        """Shutdown server gracefully using available API"""
        ...

    def get_client_status(self) -> Dict[str, bool]:
        """Get client availability status"""
        ...
