#!/usr/bin/env python3
"""
API integration management for Palworld server
Handles REST API and RCON client integration with fallback logic
"""

from typing import Optional, Dict, List, Any

from ..config_loader import PalworldConfig
from ..clients import RestAPIClient, RconClient


class IntegrationManager:
    """API integration and fallback management with proper client handling"""
    
    def __init__(self, config: PalworldConfig, logger):
        self.config = config
        self.logger = logger
        self._api_client: Optional[RestAPIClient] = None
        self._rcon_client: Optional[RconClient] = None
        self._api_initialized = False
        self._rcon_initialized = False
    
    async def initialize_clients(self) -> None:
        """Initialize API clients with proper error handling"""
        # Initialize REST API client
        if self.config.rest_api.enabled:
            try:
                self._api_client = RestAPIClient(self.config, self.logger)
                await self._api_client.__aenter__()
                self._api_initialized = True
                self.logger.info("REST API client initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize REST API client: {e}")
                self._api_client = None
                self._api_initialized = False
        
        # Initialize RCON client
        if self.config.rcon.enabled:
            try:
                self._rcon_client = RconClient(self.config, self.logger)
                await self._rcon_client.__aenter__()
                self._rcon_initialized = True
                self.logger.info("RCON client initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize RCON client: {e}")
                self._rcon_client = None
                self._rcon_initialized = False
    
    async def cleanup_clients(self) -> None:
        """Cleanup API clients with proper error handling"""
        if self._api_client and self._api_initialized:
            try:
                await self._api_client.__aexit__(None, None, None)
                self.logger.info("REST API client cleaned up")
            except Exception as e:
                self.logger.error(f"Error cleaning up REST API client: {e}")
            finally:
                self._api_client = None
                self._api_initialized = False
        
        if self._rcon_client and self._rcon_initialized:
            try:
                await self._rcon_client.__aexit__(None, None, None)
                self.logger.info("RCON client cleaned up")
            except Exception as e:
                self.logger.error(f"Error cleaning up RCON client: {e}")
            finally:
                self._rcon_client = None
                self._rcon_initialized = False
    
    def _is_api_available(self) -> bool:
        """Check if REST API client is available and healthy"""
        return (self._api_client is not None and 
                self._api_initialized and 
                hasattr(self._api_client, 'session') and 
                self._api_client.session is not None and
                not self._api_client.session.closed)
    
    def _is_rcon_available(self) -> bool:
        """Check if RCON client is available and healthy"""
        return (self._rcon_client is not None and 
                self._rcon_initialized)
    
    # REST API wrapper methods with better error handling
    async def api_get_server_info(self) -> Optional[Dict]:
        """Get server information via REST API"""
        if not self._is_api_available():
            self.logger.debug("REST API client not available for server info")
            return None
        
        try:
            return await self._api_client.get_server_info()
        except Exception as e:
            self.logger.error(f"REST API get_server_info error: {e}")
            return None
    
    async def api_get_players(self) -> Optional[List[Dict]]:
        """Get online player list via REST API"""
        if not self._is_api_available():
            self.logger.debug("REST API client not available for players")
            return None
        
        try:
            return await self._api_client.get_players()
        except Exception as e:
            self.logger.error(f"REST API get_players error: {e}")
            return None
    
    async def api_get_server_settings(self) -> Optional[Dict]:
        """Get server settings via REST API"""
        if not self._is_api_available():
            return None
        
        try:
            return await self._api_client.get_server_settings()
        except Exception as e:
            self.logger.error(f"REST API get_server_settings error: {e}")
            return None
    
    async def api_get_server_metrics(self) -> Optional[Dict]:
        """Get server metrics via REST API"""
        if not self._is_api_available():
            return None
        
        try:
            return await self._api_client.get_server_metrics()
        except Exception as e:
            self.logger.error(f"REST API get_server_metrics error: {e}")
            return None
    
    async def api_announce_message(self, message: str) -> bool:
        """Announce message to all players via REST API"""
        if not self._is_api_available():
            return False
        
        try:
            return await self._api_client.announce_message(message)
        except Exception as e:
            self.logger.error(f"REST API announce_message error: {e}")
            return False
    
    async def api_kick_player(self, player_uid: str, message: str = "") -> bool:
        """Kick player from server via REST API"""
        if not self._is_api_available():
            return False
        
        try:
            return await self._api_client.kick_player(player_uid, message)
        except Exception as e:
            self.logger.error(f"REST API kick_player error: {e}")
            return False
    
    async def api_ban_player(self, player_uid: str, message: str = "") -> bool:
        """Ban player from server via REST API"""
        if not self._is_api_available():
            return False
        
        try:
            return await self._api_client.ban_player(player_uid, message)
        except Exception as e:
            self.logger.error(f"REST API ban_player error: {e}")
            return False
    
    async def api_unban_player(self, player_uid: str) -> bool:
        """Unban player from server via REST API"""
        if not self._is_api_available():
            return False
        
        try:
            return await self._api_client.unban_player(player_uid)
        except Exception as e:
            self.logger.error(f"REST API unban_player error: {e}")
            return False
    
    async def api_save_world(self) -> bool:
        """Save world data via REST API"""
        if not self._is_api_available():
            return False
        
        try:
            return await self._api_client.save_world()
        except Exception as e:
            self.logger.error(f"REST API save_world error: {e}")
            return False
    
    async def api_shutdown_server(self, waittime: int = 1, message: str = "Server shutdown") -> bool:
        """Shutdown server gracefully via REST API"""
        if not self._is_api_available():
            return False
        
        try:
            return await self._api_client.shutdown_server(waittime, message)
        except Exception as e:
            self.logger.error(f"REST API shutdown_server error: {e}")
            return False
    
    # RCON wrapper methods with better error handling
    async def rcon_get_server_info(self) -> Optional[str]:
        """Get server information via RCON"""
        if not self._is_rcon_available():
            return None
        
        try:
            return await self._rcon_client.get_server_info()
        except Exception as e:
            self.logger.error(f"RCON get_server_info error: {e}")
            return None
    
    async def rcon_get_players(self) -> Optional[str]:
        """Get online player list via RCON"""
        if not self._is_rcon_available():
            return None
        
        try:
            return await self._rcon_client.get_players()
        except Exception as e:
            self.logger.error(f"RCON get_players error: {e}")
            return None
    
    async def rcon_announce_message(self, message: str) -> bool:
        """Announce message to all players via RCON"""
        if not self._is_rcon_available():
            return False
        
        try:
            return await self._rcon_client.announce_message(message)
        except Exception as e:
            self.logger.error(f"RCON announce_message error: {e}")
            return False
    
    async def rcon_kick_player(self, player_name: str) -> bool:
        """Kick player from server via RCON"""
        if not self._is_rcon_available():
            return False
        
        try:
            return await self._rcon_client.kick_player(player_name)
        except Exception as e:
            self.logger.error(f"RCON kick_player error: {e}")
            return False
    
    async def rcon_ban_player(self, player_name: str) -> bool:
        """Ban player from server via RCON"""
        if not self._is_rcon_available():
            return False
        
        try:
            return await self._rcon_client.ban_player(player_name)
        except Exception as e:
            self.logger.error(f"RCON ban_player error: {e}")
            return False
    
    async def rcon_save_world(self) -> bool:
        """Save world data via RCON"""
        if not self._is_rcon_available():
            return False
        
        try:
            return await self._rcon_client.save_world()
        except Exception as e:
            self.logger.error(f"RCON save_world error: {e}")
            return False
    
    async def rcon_shutdown_server(self, waittime: int = 1, message: str = "Server shutdown") -> bool:
        """Shutdown server gracefully via RCON"""
        if not self._is_rcon_available():
            return False
        
        try:
            return await self._rcon_client.shutdown_server(waittime, message)
        except Exception as e:
            self.logger.error(f"RCON shutdown_server error: {e}")
            return False
    
    async def rcon_execute_command(self, command: str, *args: str) -> Optional[str]:
        """Execute custom RCON command"""
        if not self._is_rcon_available():
            return None
        
        try:
            return await self._rcon_client.execute_custom_command(command, *args)
        except Exception as e:
            self.logger.error(f"RCON execute_command error: {e}")
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
        return self._api_client if self._is_api_available() else None
    
    def get_rcon_client(self) -> Optional[RconClient]:
        """Get RCON client instance"""
        return self._rcon_client if self._is_rcon_available() else None
    
    def get_client_status(self) -> Dict[str, bool]:
        """Get client availability status for debugging"""
        return {
            "api_available": self._is_api_available(),
            "rcon_available": self._is_rcon_available(),
            "api_initialized": self._api_initialized,
            "rcon_initialized": self._rcon_initialized
        }
