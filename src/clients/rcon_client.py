#!/usr/bin/env python3
"""
RCON client for Palworld server management
Handles server commands via RCON protocol using rcon-cli binary
"""

import asyncio
import time
from typing import Optional

from ..config_loader import PalworldConfig
from ..logging_setup import log_server_event, log_api_call


class RconClient:
    """Palworld RCON client using rcon-cli binary (no Python library needed)"""
    
    def __init__(self, config: PalworldConfig, logger):
        self.config = config
        self.logger = logger
        self.host = "127.0.0.1"
        self.port = config.rcon.port
        self.password = config.server.admin_password
        self._retry_count = 3
        self._retry_delay = 2.0
        self._is_connected = False
    
    async def __aenter__(self):
        """Async context manager enter (test rcon-cli availability)"""
        if not self.config.rcon.enabled:
            self.logger.warning("RCON is not enabled in configuration")
            return self
        
        # Test rcon-cli availability
        try:
            process = await asyncio.create_subprocess_exec(
                'rcon-cli', '--help',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            if process.returncode == 0:
                self._is_connected = True
                log_server_event(self.logger, "rcon_connect", 
                               "rcon-cli available and ready")
            else:
                self.logger.error("rcon-cli not available")
        except FileNotFoundError:
            self.logger.error("rcon-cli binary not found")
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self._is_connected:
            log_server_event(self.logger, "rcon_disconnect", 
                           "RCON client context closed")
            self._is_connected = False
    
    async def _execute_command_with_retry(
        self, 
        command: str, 
        *args: str,
        retry_count: Optional[int] = None
    ) -> Optional[str]:
        """
        Execute RCON command with retry logic using rcon-cli binary
        
        Args:
            command: RCON command
            *args: Command arguments
            retry_count: Number of retries (default if None)
            
        Returns:
            Command response or None
        """
        if not self._is_connected:
            self.logger.error("RCON not connected")
            return None
        
        if retry_count is None:
            retry_count = self._retry_count
        
        # Build rcon-cli command
        cmd = [
            'rcon-cli',
            '--host', self.host,
            '--port', str(self.port),
            '--password', self.password,
            command
        ]
        cmd.extend(args)
        
        last_exception = None
        
        for attempt in range(retry_count + 1):
            try:
                start_time = time.time()
                
                # Execute command
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=10
                )
                
                duration_ms = (time.time() - start_time) * 1000
                
                if process.returncode == 0:
                    response = stdout.decode('utf-8').strip()
                    log_api_call(self.logger, f"rcon:{command}", 200, duration_ms, 
                               attempt=attempt + 1)
                    return response
                else:
                    error_msg = stderr.decode('utf-8').strip()
                    log_api_call(self.logger, f"rcon:{command}", process.returncode, 
                               duration_ms, attempt=attempt + 1, error=error_msg)
                    
                    if attempt < retry_count:
                        await asyncio.sleep(self._retry_delay * (2 ** attempt))
                        continue
                    else:
                        return None
                        
            except Exception as e:
                last_exception = e
                if attempt < retry_count:
                    await asyncio.sleep(self._retry_delay * (2 ** attempt))
                    continue
                else:
                    self.logger.error("RCON command final failure", 
                                     command=command, error=str(e))
                    return None
        
        return None
    
    # RCON command methods
    async def get_server_info(self) -> Optional[str]:
        """Get server information via RCON"""
        return await self._execute_command_with_retry("Info")
    
    async def get_players(self) -> Optional[str]:
        """Get online player list via RCON"""
        return await self._execute_command_with_retry("ShowPlayers")
    
    async def announce_message(self, message: str) -> bool:
        """Announce message to all players via RCON"""
        result = await self._execute_command_with_retry("Broadcast", message)
        return result is not None
    
    async def kick_player(self, player_name: str) -> bool:
        """Kick player from server via RCON"""
        result = await self._execute_command_with_retry("KickPlayer", player_name)
        return result is not None
    
    async def ban_player(self, player_name: str) -> bool:
        """Ban player from server via RCON"""
        result = await self._execute_command_with_retry("BanPlayer", player_name)
        return result is not None
    
    async def save_world(self) -> bool:
        """Save world data via RCON"""
        result = await self._execute_command_with_retry("Save")
        return result is not None
    
    async def shutdown_server(self, waittime: int = 1, message: str = "Server shutdown") -> bool:
        """Shutdown server gracefully via RCON"""
        result = await self._execute_command_with_retry("Shutdown", str(waittime), message)
        return result is not None
    
    async def get_server_settings(self) -> Optional[str]:
        """Get server settings via RCON"""
        return await self._execute_command_with_retry("GetServerSettings")
    
    async def execute_custom_command(self, command: str, *args: str) -> Optional[str]:
        """Execute custom RCON command"""
        return await self._execute_command_with_retry(command, *args)
