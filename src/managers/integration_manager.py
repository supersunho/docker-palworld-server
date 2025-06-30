#!/usr/bin/env python3
"""
API integration management for Palworld server
Handles REST API and RCON client integration with fallback logic
"""

from typing import Optional, Dict, List, Any

from ..config_loader import PalworldConfig
from ..clients import RestAPIClient, RconClient


class IntegrationManager:
    """API integration and fallback management"""
    
    def __init__(self, config: PalworldConfig, logger):
        self.config = config
        self.logger = logger
        self._api_client: Optional[RestAPIClient] = None
        self._rcon_client: Optional[RconClient] = None
    
    async def initialize_clients(self) -> None:
        """Initialize API clients"""
        # Initialize REST API client
        self._api_client = RestAPIClient(self.config, self.logger)
        await self._api_client.__aenter__()
        
        # Initialize RCON client
        self._rcon_client = RconClient(self.config, self.logger)
        await self._rcon_client.__aenter__()
    
    async def cleanup_clients(self) -> None:
        """Cleanup API clients"""
        if self._api_client:
            await self._api_client.__aexit__(None, None, None)
        
        if self._rcon_client:
            await self._rcon_client.__aexit__(None, None, None)
    
    # REST API wrapper methods
    async def api_get_server_info(self) -> Optional[Dict]:
        """Get server information via REST API"""
        if self._api_client:
            return await self._api_client.get_server_info()
        return None
    
    async def api_get_players(self) -> Optional[List[Dict]]:
        """Get online player list via REST API"""
        if self._api_client:
            return await self._api_client.get_players()
        return None
    
    async def api_get_server_settings(self) -> Optional[Dict]:
        """Get server settings via REST API"""
        if self._api_client:
            return await self._api_client.get_server_settings()
        return None
    
    async def api_get_server_metrics(self) -> Optional[Dict]:
        """Get server metrics via REST API"""
        if self._api_client:
            return await self._api_client.get_server_metrics()
        return None
    
    async def api_announce_message(self, message: str) -> bool:
        """Announce message to all players via REST API"""
        if self._api_client:
            return await self._api_client.announce_message(message)
        return False
    
    async def api_kick_player(self, player_uid: str, message: str = "") -> bool:
        """Kick player from server via REST API"""
        if self._api_client:
            return await self._api_client.kick_player(player_uid, message)
        return False
    
    async def api_ban_player(self, player_uid: str, message: str = "") -> bool:
        """Ban player from server via REST API"""
        if self._api_client:
            return await self._api_client.ban_player(player_uid, message)
        return False
    
    async def api_unban_player(self, player_uid: str) -> bool:
        """Unban player from server via REST API"""
        if self._api_client:
            return await self._api_client.unban_player(player_uid)
        return False
    
    async def api_save_world(self) -> bool:
        """Save world data via REST API"""
        if self._api_client:
            return await self._api_client.save_world()
        return False
    
    async def api_shutdown_server(self, waittime: int = 1, message: str = "Server shutdown") -> bool:
        """Shutdown server gracefully via REST API"""
        if self._api_client:
            return await self._api_client.shutdown_server(waittime, message)
        return False
    
    # RCON wrapper methods
    async def rcon_get_server_info(self) -> Optional[str]:
        """Get server information via RCON"""
        if self._rcon_client:
            return await self._rcon_client.get_server_info()
        return None
    
    async def rcon_get_players(self) -> Optional[str]:
        """Get online player list via RCON"""
        if self._rcon_client:
            return await self._rcon_client.get_players()
        return None
    
    async def rcon_announce_message(self, message: str) -> bool:
        """Announce message to all players via RCON"""
        if self._rcon_client:
            return await self._rcon_client.announce_message(message)
        return False
    
    async def rcon_kick_player(self, player_name: str) -> bool:
        """Kick player from server via RCON"""
        if self._rcon_client:
            return await self._rcon_client.kick_player(player_name)
        return False
    
    async def rcon_ban_player(self, player_name: str) -> bool:
        """Ban player from server via RCON"""
        if self._rcon_client:
            return await self._rcon_client.ban_player(player_name)
        return False
    
    async def rcon_save_world(self) -> bool:
        """Save world data via RCON"""
        if self._rcon_client:
            return await self._rcon_client.save_world()
        return False
    
    async def rcon_shutdown_server(self, waittime: int = 1, message: str = "Server shutdown") -> bool:
        """Shutdown server gracefully via RCON"""
        if self._rcon_client:
            return await self._rcon_client.shutdown_server(waittime, message)
        return False
    
    async def rcon_execute_command(self, command: str, *args: str) -> Optional[str]:
        """Execute custom RCON command"""
        if self._rcon_client:
            return await self._rcon_client.execute_custom_command(command, *args)
        return None
    
    # Integrated management methods (REST API or RCON auto-select)
    async def get_server_info_any(self) -> Optional[Dict]:
        """Get server info using available API (REST first, then RCON)"""
        # Try REST API first
        info = await self.api_get_server_info()
        if info:
            return info
        
        # Fallback to RCON
        rcon_result = await self.rcon_get_server_info()
        if rcon_result:
            return {"source": "rcon", "info": rcon_result}
        
        return None
    
    async def announce_message_any(self, message: str) -> bool:
        """Announce message using available API"""
        # Try REST API first
        if await self.api_announce_message(message):
            return True
        
        # Fallback to RCON
        return await self.rcon_announce_message(message)
    
    async def save_world_any(self) -> bool:
        """Save world using available API"""
        # Try REST API first
        if await self.api_save_world():
            return True
        
        # Fallback to RCON
        return await self.rcon_save_world()
    
    def get_api_client(self) -> Optional[RestAPIClient]:
        """Get REST API client instance"""
        return self._api_client
    
    def get_rcon_client(self) -> Optional[RconClient]:
        """Get RCON client instance"""
        return self._rcon_client
