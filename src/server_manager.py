#!/usr/bin/env python3
"""
Palworld server manager core class
Implementing user's YAML + environment variable hybrid approach and workflow optimization preferences
"""

import asyncio
import aiohttp
import subprocess
import signal
import time
import psutil
import os
from pathlib import Path
from typing import Optional, List, Dict, Any, Union, Callable
from datetime import datetime, timedelta
from dataclasses import asdict

# Local module imports
from .config_loader import PalworldConfig, get_config
from .logging_setup import get_logger, log_server_event, log_player_event, log_api_call, log_backup_event


class SteamCMDManager:
    """SteamCMD dedicated management class"""
    
    def __init__(self, steamcmd_path: Path, logger):
        self.steamcmd_path = steamcmd_path
        self.logger = logger
        self.steamcmd_script = steamcmd_path / "steamcmd.sh"
    
    def validate_steamcmd(self) -> bool:
        """Check SteamCMD installation status"""
        if not self.steamcmd_script.exists():
            self.logger.error("SteamCMD executable not found", 
                            script_path=str(self.steamcmd_script))
            return False
        
        if not self.steamcmd_script.is_file():
            self.logger.error("SteamCMD path is not a file", 
                            script_path=str(self.steamcmd_script))
            return False
        
        # Check execute permission
        import stat
        mode = self.steamcmd_script.stat().st_mode
        if not (mode & stat.S_IEXEC):
            self.logger.warning("SteamCMD executable lacks execute permission, trying to set it")
            try:
                self.steamcmd_script.chmod(mode | stat.S_IEXEC)
            except PermissionError:
                self.logger.error("Failed to set execute permission for SteamCMD")
                return False
        
        return True
    
    def run_command(self, commands: List[str], timeout: int = 600) -> bool:
        """
        Run SteamCMD commands
        
        Args:
            commands: List of SteamCMD commands to run
            timeout: Timeout in seconds
            
        Returns:
            Success status
        """
        if not self.validate_steamcmd():
            return False
         
        steamcmd_command = " ".join([
            str(self.steamcmd_script),
            "+login", "anonymous"
        ] + commands + ["+quit"])
         
        full_cmd = ["FEXBash", "-c", steamcmd_command]
        
        log_server_event(self.logger, "steamcmd_start", 
                        f"Executing: FEXBash -c '{steamcmd_command}'")
        
        try:
            # Environment variables for FEX optimization
            env = {
                **dict(os.environ),
                "STEAM_COMPAT_DATA_PATH": str(self.steamcmd_path / "steam_compat"),
                "STEAM_COMPAT_CLIENT_INSTALL_PATH": str(self.steamcmd_path),
            }
            
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=str(self.steamcmd_path)
            )
            
            if result.returncode == 0:
                log_server_event(self.logger, "steamcmd_complete", 
                               "SteamCMD commands completed successfully", 
                               duration_seconds=timeout)
                return True
            else:
                log_server_event(self.logger, "steamcmd_fail", 
                               "SteamCMD commands failed", 
                               return_code=result.returncode,
                               stderr=result.stderr)
                return False
                
        except subprocess.TimeoutExpired:
            log_server_event(self.logger, "steamcmd_fail", 
                           f"SteamCMD timeout after {timeout} seconds")
            return False
        except Exception as e:
            log_server_event(self.logger, "steamcmd_fail", 
                           f"SteamCMD execution error: {e}")
            return False


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


class PalworldServerManager:
    """Main Palworld server manager class"""
    
    def __init__(self, config: Optional[PalworldConfig] = None):
        """
        Initialize server manager
        
        Args:
            config: Server configuration (loads default if None)
        """
        self.config = config or get_config()
        self.logger = get_logger("palworld.server")
        
        # Path configuration
        self.server_path = self.config.paths.server_dir
        self.backup_path = self.config.paths.backup_dir
        
        # Component initialization
        self.steamcmd_manager = SteamCMDManager(
            self.config.paths.steamcmd_dir, 
            self.logger
        )
        
        # Process management
        self.server_process: Optional[subprocess.Popen] = None
        self._shutdown_event = asyncio.Event()
        self._monitoring_task: Optional[asyncio.Task] = None
        
        # API clients created on demand
        self._api_client: Optional[RestAPIClient] = None
        self._rcon_client: Optional[RconClient] = None

        self._backup_manager: Optional[Any] = None

    async def __aenter__(self):
        """Async context manager enter"""
        # Initialize API client
        self._api_client = RestAPIClient(self.config, self.logger)
        await self._api_client.__aenter__()
        
        # Initialize RCON client
        self._rcon_client = RconClient(self.config, self.logger)
        await self._rcon_client.__aenter__()

        # Create directories
        self._ensure_directories()
        
        # Initialize backup manager from config_loader
        if self.config.backup.enabled:
            from .backup.backup_manager import get_backup_manager
            self._backup_manager = get_backup_manager(self.config)
            await self._backup_manager.start_backup_scheduler()
            print(f"✅ Backup system started with {self.config.backup.interval_seconds}s interval")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        # Stop monitoring
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        # Stop server
        if self.is_server_running():
            await self.stop_server("System shutdown")
        
        # Cleanup API client
        if self._api_client:
            await self._api_client.__aexit__(exc_type, exc_val, exc_tb)

        # Cleanup RCON client
        if self._rcon_client:
            await self._rcon_client.__aexit__(exc_type, exc_val, exc_tb)
            
        # Stop backup manager
        if self._backup_manager:
            await self._backup_manager.stop_backup_scheduler()

    def _ensure_directories(self) -> None:
        """Create necessary directories"""
        directories = [
            self.server_path,
            self.backup_path,
            self.config.paths.log_dir,
            self.server_path / "Pal" / "Saved" / "Config" / "LinuxServer"
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            self.logger.debug("Directory check/create", path=str(directory))
    
    # SteamCMD related methods
    async def download_server_files(self) -> bool:
        """Download/update Palworld server files"""
        log_server_event(self.logger, "server_download_start", 
                        "Starting Palworld server file download")
        
        commands = [
            f"+force_install_dir {self.server_path}",
            f"+app_update {self.config.steamcmd.app_id}"
        ]
        
        if self.config.steamcmd.validate:
            commands.append("validate")
        
        success = self.steamcmd_manager.run_command(commands, timeout=1800)  # 30 minutes
        
        if success:
            log_server_event(self.logger, "server_download_complete", 
                           "Server file download completed")
        else:
            log_server_event(self.logger, "server_download_fail", 
                           "Server file download failed")
        
        return success
    
    # REST API related methods
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

    # RCON related methods
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

    def generate_server_settings(self) -> bool:
        """Generate Palworld server settings file"""
        try:
            settings_dir = self.server_path / "Pal" / "Saved" / "Config" / "LinuxServer"
            settings_file = settings_dir / "PalWorldSettings.ini"
            
            # Generate settings content
            settings_content = self._generate_settings_content()
            
            settings_file.write_text(settings_content, encoding='utf-8')
            
            log_server_event(self.logger, "config_generate", 
                           "Server settings file generated", 
                           settings_file=str(settings_file))
            return True
            
        except Exception as e:
            log_server_event(self.logger, "config_generate_fail", 
                           f"Failed to generate settings file: {e}")
            return False
    
    def _generate_settings_content(self) -> str:
        """Generate complete settings file content using all config values"""
        server_cfg = self.config.server
        api_cfg = self.config.rest_api
        rcon_cfg = self.config.rcon
        gameplay_cfg = self.config.gameplay
        items_cfg = self.config.items
        base_camp_cfg = self.config.base_camp
        guild_cfg = self.config.guild
        pal_cfg = self.config.pal_settings
        building_cfg = self.config.building
        difficulty_cfg = self.config.difficulty
         
        settings = f"""[/Script/Pal.PalGameWorldSettings]
OptionSettings=(
    Difficulty={difficulty_cfg.level},
    DayTimeSpeedRate={pal_cfg.day_time_speed_rate},
    NightTimeSpeedRate={pal_cfg.night_time_speed_rate},
    ExpRate={pal_cfg.exp_rate},
    PalCaptureRate={pal_cfg.pal_capture_rate},
    PalSpawnNumRate={pal_cfg.pal_spawn_num_rate},
    PalDamageRateAttack={pal_cfg.pal_damage_rate_attack},
    PalDamageRateDefense={pal_cfg.pal_damage_rate_defense},
    PlayerDamageRateAttack={pal_cfg.player_damage_rate_attack},
    PlayerDamageRateDefense={pal_cfg.player_damage_rate_defense},
    PlayerStomachDecreaseRate={pal_cfg.player_stomach_decrease_rate},
    PlayerStaminaDecreaseRate={pal_cfg.player_stamina_decrease_rate},
    PlayerAutoHPRegeneRate={pal_cfg.player_auto_hp_regene_rate},
    PlayerAutoHpRegeneRateInSleep={pal_cfg.player_auto_hp_regene_rate_in_sleep},
    PalStomachDecreaseRate={pal_cfg.pal_stomach_decrease_rate},
    PalStaminaDecreaseRate={pal_cfg.pal_stamina_decrease_rate},
    PalAutoHPRegeneRate={pal_cfg.pal_auto_hp_regene_rate},
    PalAutoHpRegeneRateInSleep={pal_cfg.pal_auto_hp_regene_rate_in_sleep},
    BuildObjectDamageRate={building_cfg.build_object_damage_rate},
    BuildObjectDeteriorationDamageRate={building_cfg.build_object_deterioration_damage_rate},
    CollectionDropRate={building_cfg.collection_drop_rate},
    CollectionObjectHpRate={building_cfg.collection_object_hp_rate},
    CollectionObjectRespawnSpeedRate={building_cfg.collection_object_respawn_speed_rate},
    EnemyDropItemRate={building_cfg.enemy_drop_item_rate},
    DeathPenalty={difficulty_cfg.death_penalty},
    bEnablePlayerToPlayerDamage={str(gameplay_cfg.enable_player_to_player_damage).capitalize()},
    bEnableFriendlyFire={str(gameplay_cfg.enable_friendly_fire).capitalize()},
    bEnableInvaderEnemy={str(gameplay_cfg.enable_invader_enemy).capitalize()},
    bActiveUNKO={str(gameplay_cfg.active_unko).capitalize()},
    bEnableAimAssistPad={str(gameplay_cfg.enable_aim_assist_pad).capitalize()},
    bEnableAimAssistKeyboard={str(gameplay_cfg.enable_aim_assist_keyboard).capitalize()},
    DropItemMaxNum={items_cfg.drop_item_max_num},
    DropItemMaxNum_UNKO={items_cfg.drop_item_max_num_unko},
    BaseCampMaxNum={base_camp_cfg.max_num},
    BaseCampWorkerMaxNum={base_camp_cfg.worker_max_num},
    DropItemAliveMaxHours={items_cfg.drop_item_alive_max_hours},
    bAutoResetGuildNoOnlinePlayers={str(guild_cfg.auto_reset_guild_no_online_players).capitalize()},
    AutoResetGuildTimeNoOnlinePlayers={guild_cfg.auto_reset_guild_time_no_online_players},
    GuildPlayerMaxNum={guild_cfg.player_max_num},
    PalEggDefaultHatchingTime={pal_cfg.egg_default_hatching_time},
    WorkSpeedRate={pal_cfg.work_speed_rate},
    bIsMultiplay={str(gameplay_cfg.is_multiplay).capitalize()},
    bIsPvP={str(gameplay_cfg.is_pvp).capitalize()},
    bCanPickupOtherGuildDeathPenaltyDrop={str(gameplay_cfg.can_pickup_other_guild_death_penalty_drop).capitalize()},
    bEnableNonLoginPenalty={str(gameplay_cfg.enable_non_login_penalty).capitalize()},
    bEnableFastTravel={str(gameplay_cfg.enable_fast_travel).capitalize()},
    bIsStartLocationSelectByMap={str(gameplay_cfg.is_start_location_select_by_map).capitalize()},
    bExistPlayerAfterLogout={str(gameplay_cfg.exist_player_after_logout).capitalize()},
    bEnableDefenseOtherGuildPlayer={str(gameplay_cfg.enable_defense_other_guild_player).capitalize()},
    CoopPlayerMaxNum={gameplay_cfg.coop_player_max_num},
    ServerPlayerMaxNum={server_cfg.max_players},
    ServerName="{server_cfg.name}",
    ServerDescription="{server_cfg.description}",
    AdminPassword="{server_cfg.admin_password}",
    ServerPassword="{server_cfg.password}",
    PublicPort={server_cfg.port},
    PublicIP="",
    RCONEnabled={str(rcon_cfg.enabled).capitalize()},
    RCONPort={rcon_cfg.port},
    Region="{gameplay_cfg.region}",
    bUseAuth={str(gameplay_cfg.use_auth).capitalize()},
    BanListURL="{gameplay_cfg.banlist_url}",
    RESTAPIEnabled={str(api_cfg.enabled).capitalize()},
    RESTAPIPort={api_cfg.port}
)"""
        return settings

    def generate_engine_settings(self) -> bool:
        """Generate Palworld engine settings file"""
        try:
            settings_dir = self.server_path / "Pal" / "Saved" / "Config" / "LinuxServer"
            engine_file = settings_dir / "Engine.ini"
            
            # Ensure directory exists
            settings_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate engine content
            engine_content = self._generate_engine_content()
            
            engine_file.write_text(engine_content, encoding='utf-8')
            
            log_server_event(self.logger, "config_generate", 
                        "Engine settings file generated", 
                        engine_file=str(engine_file))
            return True
            
        except Exception as e:
            log_server_event(self.logger, "config_generate_fail", 
                        f"Failed to generate engine settings file: {e}")
            return False

    def _generate_engine_content(self) -> str:
        """
        Generate complete Engine.ini file content using config values
        
        Returns:
            Complete Engine.ini content as string
        """
        engine_cfg = self.config.engine
        
        # Base Engine.ini content (original paths)
        base_paths = """[Core.System]
Paths=../../../Engine/Content
Paths=%GAMEDIR%Content
Paths=../../../Engine/Plugins/2D/Paper2D/Content
Paths=../../../Engine/Plugins/Animation/ControlRigSpline/Content
Paths=../../../Engine/Plugins/Animation/ControlRig/Content
Paths=../../../Engine/Plugins/Animation/IKRig/Content
Paths=../../../Engine/Plugins/Animation/MotionWarping/Content
Paths=../../../Engine/Plugins/Bridge/Content
Paths=../../../Engine/Plugins/Compositing/Composure/Content
Paths=../../../Engine/Plugins/Compositing/OpenColorIO/Content
Paths=../../../Engine/Plugins/Developer/AnimationSharing/Content
Paths=../../../Engine/Plugins/Developer/Concert/ConcertSync/ConcertSyncClient/Content
Paths=../../../Engine/Plugins/Editor/BlueprintHeaderView/Content
Paths=../../../Engine/Plugins/Editor/GeometryMode/Content
Paths=../../../Engine/Plugins/Editor/ModelingToolsEditorMode/Content
Paths=../../../Engine/Plugins/Editor/ObjectMixer/LightMixer/Content
Paths=../../../Engine/Plugins/Editor/ObjectMixer/ObjectMixer/Content
Paths=../../../Engine/Plugins/Editor/SpeedTreeImporter/Content
Paths=../../../Engine/Plugins/Enterprise/DatasmithContent/Content
Paths=../../../Engine/Plugins/Enterprise/GLTFExporter/Content
Paths=../../../Engine/Plugins/Experimental/ChaosCaching/Content
Paths=../../../Engine/Plugins/Experimental/ChaosClothEditor/Content
Paths=../../../Engine/Plugins/Experimental/ChaosNiagara/Content
Paths=../../../Engine/Plugins/Experimental/ChaosSolverPlugin/Content
Paths=../../../Engine/Plugins/Experimental/CommonUI/Content
Paths=../../../Engine/Plugins/Experimental/Dataflow/Content
Paths=../../../Engine/Plugins/Experimental/FullBodyIK/Content
Paths=../../../Engine/Plugins/Experimental/GeometryCollectionPlugin/Content
Paths=../../../Engine/Plugins/Experimental/GeometryFlow/Content
Paths=../../../Engine/Plugins/Experimental/ImpostorBaker/Content
Paths=../../../Engine/Plugins/Experimental/Landmass/Content
Paths=../../../Engine/Plugins/Experimental/MeshLODToolset/Content
Paths=../../../Engine/Plugins/Experimental/PythonScriptPlugin/Content
Paths=../../../Engine/Plugins/Experimental/StaticMeshEditorModeling/Content
Paths=../../../Engine/Plugins/Experimental/UVEditor/Content
Paths=../../../Engine/Plugins/Experimental/Volumetrics/Content
Paths=../../../Engine/Plugins/Experimental/Water/Content
Paths=../../../Engine/Plugins/FX/Niagara/Content
Paths=../../../Engine/Plugins/JsonBlueprintUtilities/Content
Paths=../../../Engine/Plugins/Media/MediaCompositing/Content
Paths=../../../Engine/Plugins/Media/MediaPlate/Content
Paths=../../../Engine/Plugins/MovieScene/SequencerScripting/Content
Paths=../../../Engine/Plugins/PivotTool/Content
Paths=../../../Engine/Plugins/PlacementTools/Content
Paths=../../../Engine/Plugins/Runtime/AudioSynesthesia/Content
Paths=../../../Engine/Plugins/Runtime/AudioWidgets/Content
Paths=../../../Engine/Plugins/Runtime/GeometryProcessing/Content
Paths=../../../Engine/Plugins/Runtime/Metasound/Content
Paths=../../../Engine/Plugins/Runtime/ResonanceAudio/Content
Paths=../../../Engine/Plugins/Runtime/SunPosition/Content
Paths=../../../Engine/Plugins/Runtime/Synthesis/Content
Paths=../../../Engine/Plugins/Runtime/WaveTable/Content
Paths=../../../Engine/Plugins/Runtime/WebBrowserWidget/Content
Paths=../../../Engine/Plugins/SkyCreatorPlugin/Content
Paths=../../../Engine/Plugins/VirtualProduction/CameraCalibrationCore/Content
Paths=../../../Engine/Plugins/VirtualProduction/LiveLinkCamera/Content
Paths=../../../Engine/Plugins/VirtualProduction/Takes/Content
Paths=../../../Engine/Plugins/Web/HttpBlueprint/Content
Paths=../../../Pal/Plugins/DLSS/Content
Paths=../../../Pal/Plugins/EffectsChecker/Content
Paths=../../../Pal/Plugins/HoudiniEngine/Content
Paths=../../../Pal/Plugins/PPSkyCreatorPlugin/Content
Paths=../../../Pal/Plugins/PocketpairUser/Content
Paths=../../../Pal/Plugins/SpreadSheetToCsv/Content
Paths=../../../Pal/Plugins/WwiseNiagara/Content
Paths=../../../Pal/Plugins/Wwise/Content"""

        # Performance optimization settings using config values
        performance_settings = f"""

[/script/onlinesubsystemutils.ipnetdriver]
LanServerMaxTickRate={engine_cfg.lan_server_max_tick_rate}
NetServerMaxTickRate={engine_cfg.net_server_max_tick_rate}

[/script/engine.player]
ConfiguredInternetSpeed={engine_cfg.configured_internet_speed}
ConfiguredLanSpeed={engine_cfg.configured_lan_speed}

[/script/socketsubsystemepic.epicnetdriver]
MaxClientRate={engine_cfg.max_client_rate}
MaxInternetClientRate={engine_cfg.max_internet_client_rate}

[/script/engine.engine]
bSmoothFrameRate={str(engine_cfg.smooth_frame_rate).capitalize()}
bUseFixedFrameRate={str(engine_cfg.use_fixed_frame_rate).capitalize()}
SmoothedFrameRateRange=(LowerBound=(Type=Inclusive,Value={engine_cfg.frame_rate_lower_bound}),UpperBound=(Type=Exclusive,Value={engine_cfg.frame_rate_upper_bound}))
MinDesiredFrameRate={engine_cfg.min_desired_frame_rate}
FixedFrameRate={engine_cfg.fixed_frame_rate}
NetClientTicksPerSecond={engine_cfg.net_client_ticks_per_second}"""

        return base_paths + performance_settings

    
    # Server control methods
    def is_server_running(self) -> bool:
        """Check if server is currently running"""
        if self.server_process is None:
            return False
        
        poll_result = self.server_process.poll()
        return poll_result is None
    
    def start_server(self) -> bool:
        """Start Palworld server"""
        if self.is_server_running():
            log_server_event(self.logger, "server_start", 
                           "Server is already running")
            return True
        
        server_executable = self.server_path / "PalServer.sh"
        
        full_cmd = ["FEXBash", "-c", str(server_executable)]

        if not server_executable.exists():
            log_server_event(self.logger, "server_start_fail", 
                           f"Server executable not found: {server_executable}")
            return False
        
        try:
            log_server_event(self.logger, "server_start", 
                           "Starting Palworld server")
            
            # Start server process
            self.server_process = subprocess.Popen(
                full_cmd,
                cwd=str(self.server_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Wait for startup
            time.sleep(10)
            
            if not self.is_server_running():
                stdout, stderr = self.server_process.communicate()
                log_server_event(self.logger, "server_start_fail", 
                               f"Server start failed: {stderr}")
                return False
            
            log_server_event(self.logger, "server_start_complete", 
                           "Server started successfully", 
                           pid=self.server_process.pid)
            return True
            
        except Exception as e:
            log_server_event(self.logger, "server_start_fail", 
                           f"Server start error: {e}")
            return False
    
    async def stop_server(self, message: str = "Server is shutting down") -> bool:
        """Stop Palworld server gracefully"""
        if not self.is_server_running():
            log_server_event(self.logger, "server_stop", 
                           "Server is already stopped")
            return True
        
        try:
            # Attempt graceful shutdown via API
            if self._api_client:
                await self.api_announce_message(f"{message}. Shutting down in 30 seconds.")
                await asyncio.sleep(30)
                
                await self.api_shutdown_server(1, message)
                
                # Wait for shutdown
                for _ in range(60):  # Wait up to 60 seconds
                    if not self.is_server_running():
                        break
                    await asyncio.sleep(1)
            
            # Force terminate if still running
            if self.is_server_running():
                log_server_event(self.logger, "server_force_stop", 
                               "Attempting force termination")
                
                self.server_process.terminate()
                
                try:
                    self.server_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.server_process.kill()
                    self.server_process.wait()
            
            log_server_event(self.logger, "server_stop_complete", 
                           "Server stopped successfully")
            return True
            
        except Exception as e:
            log_server_event(self.logger, "server_stop_fail", 
                           f"Server stop error: {e}")
            return False


async def main():
    """Main production server function"""
    config = get_config()
    
    print("🚀 Starting Palworld Dedicated Server")
    print(f"   Server: {config.server.name}")
    print(f"   Port: {config.server.port}")
    print(f"   Max Players: {config.server.max_players}")
    
    async with PalworldServerManager(config) as manager:
        # Optional server file download
        if config.steamcmd.update_on_start:
            print("📥 Downloading/updating server files...")
            await manager.download_server_files()
        
        # Generate server settings
        print("⚙️ Generating server settings...")
        manager.generate_server_settings()
        manager.generate_engine_settings()
        
        print("🎮 Starting Palworld server...")
        if manager.start_server():
            print("✅ Palworld server started successfully!")
            print(f"🌐 Server running on port {config.server.port}")
            print(f"🔧 REST API available on port {config.rest_api.port}")
             
            try:
                while manager.is_server_running():
                    await asyncio.sleep(30)   
                    print(f"📊 Server status: Running")
            except KeyboardInterrupt:
                print("🛑 Received shutdown signal...")
                await manager.stop_server("Server shutdown requested")
        else:
            print("❌ Failed to start Palworld server")
            return 1
    
    return 0


if __name__ == "__main__":
    import sys
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
