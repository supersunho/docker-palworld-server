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
        
        # API client created on demand
        self._api_client: Optional[RestAPIClient] = None
    
    async def __aenter__(self):
        """Async context manager enter"""
        # Initialize API client
        self._api_client = RestAPIClient(self.config, self.logger)
        await self._api_client.__aenter__()
        
        # Create directories
        self._ensure_directories()
        
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
        """Generate settings file content"""
        server_cfg = self.config.server
        api_cfg = self.config.rest_api
        
        # Reflect user's YAML + environment variable hybrid approach
        settings = f"""[/Script/Pal.PalGameWorldSettings]
OptionSettings=(
    Difficulty=None,
    DayTimeSpeedRate=1.000000,
    NightTimeSpeedRate=1.000000,
    ExpRate=1.000000,
    PalCaptureRate=1.000000,
    PalSpawnNumRate=1.000000,
    PalDamageRateAttack=1.000000,
    PalDamageRateDefense=1.000000,
    PlayerDamageRateAttack=1.000000,
    PlayerDamageRateDefense=1.000000,
    PlayerStomachDecreaseRate=1.000000,
    PlayerStaminaDecreaseRate=1.000000,
    PlayerAutoHPRegeneRate=1.000000,
    PlayerAutoHpRegeneRateInSleep=1.000000,
    PalStomachDecreaseRate=1.000000,
    PalStaminaDecreaseRate=1.000000,
    PalAutoHPRegeneRate=1.000000,
    PalAutoHpRegeneRateInSleep=1.000000,
    BuildObjectDamageRate=1.000000,
    BuildObjectDeteriorationDamageRate=1.000000,
    CollectionDropRate=1.000000,
    CollectionObjectHpRate=1.000000,
    CollectionObjectRespawnSpeedRate=1.000000,
    EnemyDropItemRate=1.000000,
    DeathPenalty=All,
    bEnablePlayerToPlayerDamage=False,
    bEnableFriendlyFire=False,
    bEnableInvaderEnemy=True,
    bActiveUNKO=False,
    bEnableAimAssistPad=True,
    bEnableAimAssistKeyboard=False,
    DropItemMaxNum=3000,
    DropItemMaxNum_UNKO=100,
    BaseCampMaxNum=128,
    BaseCampWorkerMaxNum=15,
    DropItemAliveMaxHours=1.000000,
    bAutoResetGuildNoOnlinePlayers=False,
    AutoResetGuildTimeNoOnlinePlayers=72.000000,
    GuildPlayerMaxNum=20,
    PalEggDefaultHatchingTime=72.000000,
    WorkSpeedRate=1.000000,
    bIsMultiplay=True,
    bIsPvP=False,
    bCanPickupOtherGuildDeathPenaltyDrop=False,
    bEnableNonLoginPenalty=True,
    bEnableFastTravel=True,
    bIsStartLocationSelectByMap=True,
    bExistPlayerAfterLogout=False,
    bEnableDefenseOtherGuildPlayer=False,
    CoopPlayerMaxNum=4,
    ServerPlayerMaxNum={server_cfg.max_players},
    ServerName="{server_cfg.name}",
    ServerDescription="{server_cfg.description}",
    AdminPassword="{server_cfg.admin_password}",
    ServerPassword="{server_cfg.password}",
    PublicPort={server_cfg.port},
    PublicIP="",
    RCONEnabled=False,
    RCONPort=25575,
    Region="",
    bUseAuth=True,
    BanListURL="https://api.palworldgame.com/api/banlist.txt",
    RESTAPIEnabled={str(api_cfg.enabled).lower()},
    RESTAPIPort={api_cfg.port}
)"""
        return settings
    
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
        
        if not server_executable.exists():
            log_server_event(self.logger, "server_start_fail", 
                           f"Server executable not found: {server_executable}")
            return False
        
        try:
            log_server_event(self.logger, "server_start", 
                           "Starting Palworld server")
            
            # Start server process
            self.server_process = subprocess.Popen(
                [str(server_executable)],
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
                await self._api_client.announce_message(f"{message}. Shutting down in 30 seconds.")
                await asyncio.sleep(30)
                
                await self._api_client.shutdown_server(1, message)
                
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
         
        print("🎮 Starting Palworld server...")
        if manager.start_server():
            print("✅ Palworld server started successfully!")
            print(f"🌐 Server running on port {config.server.port}")
            print(f"🔧 REST API available on port {config.rest_api.port}")
             
            try:
                while manager.is_server_running():
                    await asyncio.sleep(30)   
                    print(f"📊 Server status: Running (Players: checking...)")
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
 