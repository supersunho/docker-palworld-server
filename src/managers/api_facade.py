#!/usr/bin/env python3
"""
Unified API facade for Palworld server management
Integrates REST API and RCON calls with fallback logic.
Single entry point for all server API interactions.
"""

from typing import Optional, Dict, List, Any

from ..config_loader import PalworldConfig
from ..clients import RestAPIClient, RconClient
from ..logging_setup import get_logger
from ..protocols import IServerAPI, ServerInfo


class ServerAPIFacade(IServerAPI):
    """Unified API facade that integrates REST API and RCON with fallback logic"""

    def __init__(
        self,
        config: PalworldConfig,
        logger=None,
        rest_client: Optional[RestAPIClient] = None,
        rcon_client: Optional[RconClient] = None,
    ):
        self.config = config
        self.logger = logger or get_logger("palworld.api_facade")
        self._rest = rest_client
        self._rcon = rcon_client
        self._rest_available = False
        self._rcon_available = False

    async def initialize_clients(self):
        """Initialize API clients"""
        if self.config.rest_api.enabled:
            try:
                self._rest = RestAPIClient(self.config, self.logger)
                await self._rest.__aenter__()
                self._rest_available = True
                self.logger.info("REST API client initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize REST API client: {e}")
                self._rest = None
                self._rest_available = False

        if self.config.rcon.enabled:
            try:
                self._rcon = RconClient(self.config, self.logger)
                await self._rcon.__aenter__()
                self._rcon_available = True
                self.logger.info("RCON client initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize RCON client: {e}")
                self._rcon = None
                self._rcon_available = False

    async def cleanup_clients(self):
        """Cleanup API clients"""
        if self._rest and self._rest_available:
            try:
                await self._rest.__aexit__(None, None, None)
                self.logger.info("REST API client cleaned up")
            except Exception as e:
                self.logger.error(f"Error cleaning up REST API client: {e}")
            finally:
                self._rest = None
                self._rest_available = False

        if self._rcon and self._rcon_available:
            try:
                await self._rcon.__aexit__(None, None, None)
                self.logger.info("RCON client cleaned up")
            except Exception as e:
                self.logger.error(f"Error cleaning up RCON client: {e}")
            finally:
                self._rcon = None
                self._rcon_available = False

    def _is_rest_available(self) -> bool:
        """Check if REST API client is available"""
        return (
            self._rest is not None
            and self._rest_available
            and hasattr(self._rest, "session")
            and self._rest.session is not None
            and not self._rest.session.closed
        )

    def _is_rcon_available(self) -> bool:
        """Check if RCON client is available"""
        return self._rcon is not None and self._rcon_available

    # --- Direct client access ---

    def get_api_client(self) -> Optional[RestAPIClient]:
        """Get REST API client instance"""
        return self._rest if self._is_rest_available() else None

    def get_rcon_client(self) -> Optional[RconClient]:
        """Get RCON client instance"""
        return self._rcon if self._is_rcon_available() else None

    # --- REST API methods ---

    async def api_get_server_info(self) -> Optional[Dict]:
        """Get server information via REST API"""
        if not self._is_rest_available():
            return None
        try:
            return await self._rest.get_server_info()
        except Exception as e:
            self.logger.error(f"REST API get_server_info error: {e}")
            return None

    async def api_get_players(self) -> Optional[List[Dict]]:
        """Get online player list via REST API"""
        if not self._is_rest_available():
            return None
        try:
            return await self._rest.get_players()
        except Exception as e:
            self.logger.error(f"REST API get_players error: {e}")
            return None

    async def api_get_server_settings(self) -> Optional[Dict]:
        """Get server settings via REST API"""
        if not self._is_rest_available():
            return None
        try:
            return await self._rest.get_server_settings()
        except Exception as e:
            self.logger.error(f"REST API get_server_settings error: {e}")
            return None

    async def api_get_server_metrics(self) -> Optional[Dict]:
        """Get server metrics via REST API"""
        if not self._is_rest_available():
            return None
        try:
            return await self._rest.get_server_metrics()
        except Exception as e:
            self.logger.error(f"REST API get_server_metrics error: {e}")
            return None

    async def api_announce_message(self, message: str) -> bool:
        """Announce message to all players via REST API"""
        if not self._is_rest_available():
            return False
        try:
            return await self._rest.announce_message(message)
        except Exception as e:
            self.logger.error(f"REST API announce_message error: {e}")
            return False

    async def api_kick_player(self, player_uid: str, message: str = "") -> bool:
        """Kick player from server via REST API"""
        if not self._is_rest_available():
            return False
        try:
            return await self._rest.kick_player(player_uid, message)
        except Exception as e:
            self.logger.error(f"REST API kick_player error: {e}")
            return False

    async def api_ban_player(self, player_uid: str, message: str = "") -> bool:
        """Ban player from server via REST API"""
        if not self._is_rest_available():
            return False
        try:
            return await self._rest.ban_player(player_uid, message)
        except Exception as e:
            self.logger.error(f"REST API ban_player error: {e}")
            return False

    async def api_unban_player(self, player_uid: str) -> bool:
        """Unban player from server via REST API"""
        if not self._is_rest_available():
            return False
        try:
            return await self._rest.unban_player(player_uid)
        except Exception as e:
            self.logger.error(f"REST API unban_player error: {e}")
            return False

    async def api_save_world(self) -> bool:
        """Save world data via REST API"""
        if not self._is_rest_available():
            return False
        try:
            return await self._rest.save_world()
        except Exception as e:
            self.logger.error(f"REST API save_world error: {e}")
            return False

    async def api_shutdown_server(
        self, waittime: int = 1, message: str = "Server shutdown"
    ) -> bool:
        """Shutdown server gracefully via REST API"""
        if not self._is_rest_available():
            return False
        try:
            return await self._rest.shutdown_server(waittime, message)
        except Exception as e:
            self.logger.error(f"REST API shutdown_server error: {e}")
            return False

    # --- RCON methods ---

    async def rcon_get_server_info(self) -> Optional[str]:
        """Get server information via RCON"""
        if not self._is_rcon_available():
            return None
        try:
            return await self._rcon.get_server_info()
        except Exception as e:
            self.logger.error(f"RCON get_server_info error: {e}")
            return None

    async def rcon_get_players(self) -> Optional[str]:
        """Get online player list via RCON"""
        if not self._is_rcon_available():
            return None
        try:
            return await self._rcon.get_players()
        except Exception as e:
            self.logger.error(f"RCON get_players error: {e}")
            return None

    async def rcon_announce_message(self, message: str) -> bool:
        """Announce message to all players via RCON"""
        if not self._is_rcon_available():
            return False
        try:
            return await self._rcon.announce_message(message)
        except Exception as e:
            self.logger.error(f"RCON announce_message error: {e}")
            return False

    async def rcon_kick_player(self, player_name: str) -> bool:
        """Kick player from server via RCON"""
        if not self._is_rcon_available():
            return False
        try:
            return await self._rcon.kick_player(player_name)
        except Exception as e:
            self.logger.error(f"RCON kick_player error: {e}")
            return False

    async def rcon_ban_player(self, player_name: str) -> bool:
        """Ban player from server via RCON"""
        if not self._is_rcon_available():
            return False
        try:
            return await self._rcon.ban_player(player_name)
        except Exception as e:
            self.logger.error(f"RCON ban_player error: {e}")
            return False

    async def rcon_save_world(self) -> bool:
        """Save world data via RCON"""
        if not self._is_rcon_available():
            return False
        try:
            return await self._rcon.save_world()
        except Exception as e:
            self.logger.error(f"RCON save_world error: {e}")
            return False

    async def rcon_shutdown_server(
        self, waittime: int = 1, message: str = "Server shutdown"
    ) -> bool:
        """Shutdown server gracefully via RCON"""
        if not self._is_rcon_available():
            return False
        try:
            return await self._rcon.shutdown_server(waittime, message)
        except Exception as e:
            self.logger.error(f"RCON shutdown_server error: {e}")
            return False

    async def rcon_execute_command(self, command: str, *args: str) -> Optional[str]:
        """Execute custom RCON command"""
        if not self._is_rcon_available():
            return None
        try:
            return await self._rcon.execute_custom_command(command, *args)
        except Exception as e:
            self.logger.error(f"RCON execute_command error: {e}")
            return None

    # --- Fallback methods (REST first, then RCON) ---

    async def get_server_info(self) -> Optional[ServerInfo]:
        """Get server information using available API (REST first, then RCON)"""
        if self._is_rest_available():
            try:
                rest_info = await self._rest.get_server_info()
                if rest_info:
                    return ServerInfo(
                        name=rest_info.get("name", ""),
                        players=rest_info.get("players", 0),
                        max_players=rest_info.get("max_players", 0),
                        uptime=rest_info.get("uptime", ""),
                        version=rest_info.get("version", ""),
                        ip=rest_info.get("ip", ""),
                        port=rest_info.get("port", 0),
                    )
            except Exception as e:
                self.logger.error(f"REST API get_server_info error: {e}")

        if self._is_rcon_available():
            try:
                rcon_result = await self._rcon.get_server_info()
                if rcon_result:
                    return ServerInfo(info=rcon_result)
            except Exception as e:
                self.logger.error(f"RCON get_server_info error: {e}")

        return None

    async def get_players(self) -> Optional[List[Dict[str, Any]]]:
        """Get online player list using available API (REST first, then RCON)"""
        if self._is_rest_available():
            try:
                players = await self._rest.get_players()
                if players is not None:
                    return players
            except Exception as e:
                self.logger.error(f"REST API get_players error: {e}")

        if self._is_rcon_available():
            try:
                rcon_result = await self._rcon.get_players()
                if rcon_result:
                    if rcon_result.strip():
                        lines = rcon_result.strip().split("\n")
                        if len(lines) > 1:
                            headers = lines[0].split(",")
                            players_data = []
                            for line in lines[1:]:
                                values = line.split(",")
                                if len(values) == len(headers):
                                    player = {
                                        headers[i].strip(): values[i].strip()
                                        for i in range(len(headers))
                                    }
                                    players_data.append(player)
                            return players_data
            except Exception as e:
                self.logger.error(f"RCON get_players error: {e}")

        return None

    async def get_server_info_any(self) -> Optional[Dict]:
        """Get server info using available API (REST first, then RCON)"""
        info = await self.api_get_server_info()
        if info:
            return info
        rcon_result = await self.rcon_get_server_info()
        if rcon_result:
            return {"source": "rcon", "info": rcon_result}
        return None

    async def announce(self, message: str) -> bool:
        """Announce message using available API (REST first, then RCON)"""
        if self._is_rest_available():
            try:
                if await self._rest.announce_message(message):
                    return True
            except Exception as e:
                self.logger.error(f"REST API announce error: {e}")

        if self._is_rcon_available():
            try:
                return await self._rcon.announce_message(message)
            except Exception as e:
                self.logger.error(f"RCON announce error: {e}")

        return False

    async def announce_message_any(self, message: str) -> bool:
        """Announce message using available API (alias)"""
        return await self.announce(message)

    async def save_world(self) -> bool:
        """Save world data using available API (REST first, then RCON)"""
        if self._is_rest_available():
            try:
                if await self._rest.save_world():
                    return True
            except Exception as e:
                self.logger.error(f"REST API save_world error: {e}")

        if self._is_rcon_available():
            try:
                return await self._rcon.save_world()
            except Exception as e:
                self.logger.error(f"RCON save_world error: {e}")

        return False

    async def save_world_any(self) -> bool:
        """Save world using available API (alias)"""
        return await self.save_world()

    async def get_server_settings(self) -> Optional[Dict[str, Any]]:
        """Get server settings using available API (REST first, then RCON)"""
        if self._is_rest_available():
            try:
                settings = await self._rest.get_server_settings()
                if settings:
                    return settings
            except Exception as e:
                self.logger.error(f"REST API get_server_settings error: {e}")

        if self._is_rcon_available():
            try:
                rcon_result = await self._rcon.get_server_settings()
                if rcon_result:
                    return {"raw_settings": rcon_result}
            except Exception as e:
                self.logger.error(f"RCON get_server_settings error: {e}")

        return None

    async def kick_player(self, player_identifier: str, message: str = "") -> bool:
        """Kick player using available API (REST first, then RCON)"""
        if self._is_rest_available():
            try:
                if await self._rest.kick_player(player_identifier, message):
                    return True
            except Exception as e:
                self.logger.error(f"REST API kick_player error: {e}")

        if self._is_rcon_available():
            try:
                return await self._rcon.kick_player(player_identifier)
            except Exception as e:
                self.logger.error(f"RCON kick_player error: {e}")

        return False

    async def ban_player(self, player_identifier: str, message: str = "") -> bool:
        """Ban player using available API (REST first, then RCON)"""
        if self._is_rest_available():
            try:
                if await self._rest.ban_player(player_identifier, message):
                    return True
            except Exception as e:
                self.logger.error(f"REST API ban_player error: {e}")

        if self._is_rcon_available():
            try:
                return await self._rcon.ban_player(player_identifier)
            except Exception as e:
                self.logger.error(f"RCON ban_player error: {e}")

        return False

    async def unban_player(self, player_identifier: str) -> bool:
        """Unban player (REST API only)"""
        if self._is_rest_available():
            try:
                return await self._rest.unban_player(player_identifier)
            except Exception as e:
                self.logger.error(f"REST API unban_player error: {e}")
        return False

    async def shutdown_server(self, waittime: int = 1, message: str = "Server shutdown") -> bool:
        """Shutdown server gracefully (REST first, then RCON)"""
        if self._is_rest_available():
            try:
                if await self._rest.shutdown_server(waittime, message):
                    return True
            except Exception as e:
                self.logger.error(f"REST API shutdown_server error: {e}")

        if self._is_rcon_available():
            try:
                return await self._rcon.shutdown_server(waittime, message)
            except Exception as e:
                self.logger.error(f"RCON shutdown_server error: {e}")

        return False

    def get_client_status(self) -> Dict[str, bool]:
        """Get client availability status"""
        return {
            "rest_available": self._is_rest_available(),
            "rcon_available": self._is_rcon_available(),
            "rest_initialized": self._rest_available,
            "rcon_initialized": self._rcon_available,
        }
