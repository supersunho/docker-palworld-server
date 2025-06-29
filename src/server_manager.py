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
        
        full_cmd = ["FEXBash", "-c", server_executable]

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
 