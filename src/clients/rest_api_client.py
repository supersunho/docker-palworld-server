#!/usr/bin/env python3
"""
REST API client for Palworld server management
Handles server communication via official Palworld REST API
"""

import asyncio
import aiohttp
import time
from typing import Optional, Dict, List

from ..config_loader import PalworldConfig
from ..logging_setup import log_api_call


class RestAPIClient:
    """Palworld REST API client class"""
    
    def __init__(self, config: PalworldConfig, logger):
        self.config = config
        self.logger = logger
        self.session: Optional[aiohttp.ClientSession] = None
        self.base_url = f"http://{config.rest_api.host}:{config.rest_api.port}/v1/api"
        self._retry_count = 3
        self._retry_delay = 1.0
    
    async def __aenter__(self):
        """Async context manager enter"""
        auth = aiohttp.BasicAuth("admin", self.config.server.admin_password)
        timeout = aiohttp.ClientTimeout(
            total=30,
            connect=10,
            sock_read=20
        )
        
        connector = aiohttp.TCPConnector(
            limit=10,
            limit_per_host=5,
            keepalive_timeout=60
        )
        
        self.session = aiohttp.ClientSession(
            auth=auth,
            timeout=timeout,
            connector=connector,
            headers={
                "User-Agent": "PalworldServerManager/1.0",
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def _make_request_with_retry(
        self, 
        endpoint: str, 
        method: str = "GET", 
        data: Optional[Dict] = None,
        retry_count: Optional[int] = None
    ) -> Optional[Dict]:
        """
        API request with retry logic
        
        Args:
            endpoint: API endpoint
            method: HTTP method
            data: Request data
            retry_count: Number of retries (default if None)
            
        Returns:
            API response data or None
        """
        if retry_count is None:
            retry_count = self._retry_count
        
        last_exception = None
        
        for attempt in range(retry_count + 1):
            try:
                start_time = time.time()
                result = await self._make_request(endpoint, method, data)
                duration_ms = (time.time() - start_time) * 1000
                
                if result is not None:
                    log_api_call(self.logger, endpoint, 200, duration_ms, 
                               attempt=attempt + 1)
                    return result
                
            except Exception as e:
                last_exception = e
                duration_ms = (time.time() - start_time) * 1000
                
                log_api_call(self.logger, endpoint, 0, duration_ms, 
                           attempt=attempt + 1, error=str(e))
                
                if attempt < retry_count:
                    await asyncio.sleep(self._retry_delay * (2 ** attempt))
        
        # All retries failed
        self.logger.error("API request final failure", 
                         endpoint=endpoint, 
                         attempts=retry_count + 1,
                         last_error=str(last_exception))
        return None
    
    async def _make_request(
        self, 
        endpoint: str, 
        method: str = "GET", 
        data: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        Single API request execution
        """
        if not self.session:
            self.logger.error("API client session not initialized")
            return None
        
        url = f"{self.base_url}{endpoint}"
        
        kwargs = {
            "method": method,
            "url": url
        }
        
        if data is not None:
            kwargs["json"] = data
        
        try:
            async with self.session.request(**kwargs) as response:
                response_text = await response.text()
                
                if response.status == 200:
                    try:
                        return await response.json() if response_text else {}
                    except ValueError:
                        # Return raw text if JSON parsing fails
                        return {"raw_response": response_text}
                else:
                    self.logger.warning("API request failed", 
                                      status=response.status,
                                      response=response_text[:200])
                    return None
                    
        except asyncio.TimeoutError:
            self.logger.error("API request timeout", endpoint=endpoint)
            return None
        except aiohttp.ClientError as e:
            self.logger.error("API client error", endpoint=endpoint, error=str(e))
            return None
    
    # API methods (based on official Palworld REST API documentation)
    async def get_server_info(self) -> Optional[Dict]:
        """Get server information"""
        return await self._make_request_with_retry("/info")
    
    async def get_players(self) -> Optional[List[Dict]]:
        """Get online player list"""
        result = await self._make_request_with_retry("/players")
        return result.get("players", []) if result else None
    
    async def get_server_settings(self) -> Optional[Dict]:
        """Get server settings"""
        return await self._make_request_with_retry("/settings")
    
    async def get_server_metrics(self) -> Optional[Dict]:
        """Get server metrics"""
        return await self._make_request_with_retry("/metrics")
    
    async def announce_message(self, message: str) -> bool:
        """Announce message to all players"""
        data = {"message": message}
        result = await self._make_request_with_retry("/announce", "POST", data)
        return result is not None
    
    async def kick_player(self, player_uid: str, message: str = "") -> bool:
        """Kick player from server"""
        data = {"userid": player_uid, "message": message}
        result = await self._make_request_with_retry("/kick", "POST", data)
        return result is not None
    
    async def ban_player(self, player_uid: str, message: str = "") -> bool:
        """Ban player from server"""
        data = {"userid": player_uid, "message": message}
        result = await self._make_request_with_retry("/ban", "POST", data)
        return result is not None
    
    async def unban_player(self, player_uid: str) -> bool:
        """Unban player from server"""
        data = {"userid": player_uid}
        result = await self._make_request_with_retry("/unban", "POST", data)
        return result is not None
    
    async def save_world(self) -> bool:
        """Save world data"""
        result = await self._make_request_with_retry("/save", "POST")
        return result is not None
    
    async def shutdown_server(self, waittime: int = 1, message: str = "Server shutdown") -> bool:
        """Shutdown server gracefully"""
        data = {"waittime": waittime, "message": message}
        result = await self._make_request_with_retry("/shutdown", "POST", data)
        return result is not None
