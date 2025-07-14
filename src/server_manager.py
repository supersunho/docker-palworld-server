#!/usr/bin/env python3
"""
Palworld server manager - Main orchestrator with API readiness verification
Waits for REST API to be ready before starting monitoring systems 
"""

import asyncio
import time
import aiohttp
from typing import Optional, Any

from .config_loader import PalworldConfig, get_config
from .logging_setup import get_logger, log_server_event, setup_logging

from .clients import SteamCMDManager
from .managers import ProcessManager, ConfigManager, IntegrationManager
from .monitoring import MonitoringManager


async def wait_for_api_ready(manager, max_wait_time: int = 60, check_interval: int = 2) -> bool:
    """Wait for REST API to become available before starting monitoring"""
    logger = get_logger("palworld.api_readiness")
    
    api_host = manager.config.rest_api.host
    api_port = manager.config.rest_api.port
    admin_password = manager.config.server.admin_password
    
    logger.info(f"Checking REST API readiness at {api_host}:{api_port}")
    logger.info(f"Maximum wait time: {max_wait_time} seconds")
    
    start_time = time.time()
    attempt = 0
    
    while (time.time() - start_time) < max_wait_time:
        attempt += 1
        elapsed = int(time.time() - start_time)
        
        try:
            auth = aiohttp.BasicAuth("admin", admin_password)
            timeout = aiohttp.ClientTimeout(total=5)
            
            async with aiohttp.ClientSession(auth=auth, timeout=timeout) as session:
                test_url = f"http://{api_host}:{api_port}/v1/api/info"
                
                async with session.get(test_url) as response:
                    if response.status == 200:
                        logger.info(f"✅ REST API is ready and responding (attempt {attempt}, {elapsed}s elapsed)")
                        return True
                    elif response.status == 401:
                        logger.info(f"✅ REST API is responding (attempt {attempt}, {elapsed}s elapsed)")
                        logger.warning("Authentication issue detected, but API is ready")
                        return True
                    else:
                        logger.debug(f"API responding with status {response.status} (attempt {attempt})")
                        
        except aiohttp.ClientConnectorError as e:
            logger.debug(f"API not ready - connection failed (attempt {attempt}, {elapsed}s): {str(e)[:50]}...")
            
        except asyncio.TimeoutError:
            logger.debug(f"API not ready - timeout (attempt {attempt}, {elapsed}s)")
            
        except Exception as e:
            logger.debug(f"API check error (attempt {attempt}, {elapsed}s): {str(e)[:50]}...")
        
        if attempt % (10 // check_interval) == 0:
            remaining = max_wait_time - elapsed
            logger.info(f"⏳ Still waiting for API... ({elapsed}s elapsed, {remaining}s remaining)")
        
        await asyncio.sleep(check_interval)
    
    total_elapsed = int(time.time() - start_time)
    logger.error(f"❌ REST API did not become ready within {max_wait_time} seconds (total attempts: {attempt})")
    return False


async def verify_server_startup(manager, max_wait_time: int = 30) -> bool:
    """Verify that the Palworld server process is running and stable"""
    logger = get_logger("palworld.startup_verification")
    
    logger.info("Verifying server process startup...")
    
    if not manager.process_manager.is_server_running():
        logger.error("Server process is not running")
        return False
    
    stability_check_duration = min(10, max_wait_time)
    logger.info(f"Checking process stability for {stability_check_duration} seconds...")
    
    start_time = time.time()
    while (time.time() - start_time) < stability_check_duration:
        if not manager.process_manager.is_server_running():
            logger.error("Server process crashed during stability check")
            return False
        await asyncio.sleep(1)
    
    logger.info("✅ Server process is running and stable")
    return True


class PalworldServerManager:
    """Main Palworld server orchestrator with enhanced startup verification"""
    
    def __init__(self, config: Optional[PalworldConfig] = None):
        """Initialize server manager with specialized components"""
        self.config = config or get_config()
        self.logger = get_logger("palworld.server")
        
        self.steamcmd_manager = SteamCMDManager(
            self.config.paths.steamcmd_dir, 
            self.logger
        )
        self.process_manager = ProcessManager(self.config, self.logger)
        self.config_manager = ConfigManager(self.config, self.logger)
        self.integration_manager = IntegrationManager(self.config, self.logger)
        
        self.monitoring_manager = MonitoringManager(
            self.config, 
            self.process_manager, 
            self.integration_manager
        )
        
        self._backup_manager: Optional[Any] = None
        self._startup_completed = False
    
    async def __aenter__(self):
        """Initialize all components"""
        await self.integration_manager.initialize_clients()
        
        self._ensure_directories()
        
        if self.config.backup.enabled:
            from .backup.backup_manager import get_backup_manager
            self._backup_manager = get_backup_manager(self.config)
            await self._backup_manager.start_backup_scheduler()
            
            if hasattr(self._backup_manager, 'add_completion_callback'):
                self._backup_manager.add_completion_callback(
                    self.monitoring_manager.handle_backup_completion
                )
            
            self.logger.info(f"Backup system started with {self.config.backup.interval_seconds}s interval")
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup all components"""
        if hasattr(self, 'monitoring_manager'):
            await self.monitoring_manager.stop_monitoring()
        
        if self.process_manager.is_server_running():
            await self.stop_server("System shutdown")
        
        if self._backup_manager:
            await self._backup_manager.stop_backup_scheduler()
        
        await self.integration_manager.cleanup_clients()
    
    def _ensure_directories(self) -> None:
        """Create necessary directories for server operation"""
        directories = [
            self.config.paths.server_dir,
            self.config.paths.backup_dir,
            self.config.paths.log_dir,
            self.config.paths.server_dir / "Pal" / "Saved" / "Config" / "LinuxServer"
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            self.logger.debug("Directory check/create", path=str(directory))
    
    async def start_server_with_verification(self) -> bool:
        """Start Palworld server and wait for full readiness"""
        success = self.process_manager.start_server()
        if not success:
            self.logger.error("Failed to start server process")
            await self.monitoring_manager.handle_error("Failed to start Palworld server")
            return False
        
        self.logger.info("Server process started, verifying startup...")
        
        process_stable = await verify_server_startup(self, max_wait_time=30)
        if not process_stable:
            self.logger.error("Server process is not stable")
            await self.monitoring_manager.handle_error("Server process unstable after startup")
            return False
        
        if self.config.rest_api.enabled:
            self.logger.info("Waiting for REST API to become ready...")
            api_ready = await wait_for_api_ready(self, max_wait_time=60, check_interval=2)
            
            if api_ready:
                self.logger.info("✅ REST API is ready")
            else:
                self.logger.warning("⚠️ REST API not ready within timeout, starting with limited monitoring")
                await self.monitoring_manager.handle_error("REST API failed to become ready within timeout")
        
        self.logger.info("Starting monitoring systems...")
        try:
            await self.monitoring_manager.start_monitoring()
            self.logger.info("✅ Monitoring systems started successfully")
        except Exception as e:
            self.logger.error(f"Failed to start monitoring systems: {e}")
            await self.monitoring_manager.handle_error(f"Failed to start monitoring: {str(e)}")
        
        self._startup_completed = True
        return True
    
    async def download_server_files(self) -> bool:
        """Download/update Palworld server files via SteamCMD"""
        log_server_event(self.logger, "server_download_start", 
                        "Starting Palworld server file download")
        
        commands = [
            f"+force_install_dir {self.config.paths.server_dir}",
            f"+app_update {self.config.steamcmd.app_id}"
        ]
        
        if self.config.steamcmd.validate:
            commands.append("validate")
        
        success = self.steamcmd_manager.run_command(commands, timeout=1800)
        
        if success:
            log_server_event(self.logger, "server_download_complete", 
                           "Server file download completed")
        else:
            log_server_event(self.logger, "server_download_fail", 
                           "Server file download failed")
            await self.monitoring_manager.handle_error("Server file download failed")
        
        return success
    
    def is_server_running(self) -> bool:
        """Check if server is currently running"""
        return self.process_manager.is_server_running()
    
    def start_server(self) -> bool:
        """Start Palworld server"""
        success = self.process_manager.start_server()
        
        if not success:
            asyncio.create_task(
                self.monitoring_manager.handle_error("Failed to start Palworld server")
            )
        
        return success
    
    async def stop_server(self, message: str = "Server is shutting down") -> bool:
        """Stop Palworld server gracefully"""
        return await self.process_manager.stop_server(
            message, 
            self.integration_manager.get_api_client()
        )
    
    def get_server_status(self) -> dict:
        """Get detailed server process status"""
        return self.process_manager.get_server_status()
    
    def generate_server_settings(self) -> bool:
        """Generate server settings file"""
        return self.config_manager.generate_server_settings()
    
    def generate_engine_settings(self) -> bool:
        """Generate engine settings file"""
        return self.config_manager.generate_engine_settings()
    
    async def get_server_info_any(self):
        """Get server info using available API"""
        return await self.integration_manager.get_server_info_any()
    
    async def announce_message_any(self, message: str) -> bool:
        """Announce message using available API"""
        return await self.integration_manager.announce_message_any(message)
    
    async def save_world_any(self) -> bool:
        """Save world using available API"""
        return await self.integration_manager.save_world_any()
    
    async def api_get_server_info(self):
        """Get server information via REST API"""
        return await self.integration_manager.api_get_server_info()
    
    async def api_get_players(self):
        """Get online player list via REST API"""
        return await self.integration_manager.api_get_players()
    
    async def api_get_server_settings(self):
        """Get server settings via REST API"""
        return await self.integration_manager.api_get_server_settings()
    
    async def api_get_server_metrics(self):
        """Get server metrics via REST API"""
        return await self.integration_manager.api_get_server_metrics()
    
    async def api_announce_message(self, message: str) -> bool:
        """Announce message to all players via REST API"""
        return await self.integration_manager.api_announce_message(message)
    
    async def api_kick_player(self, player_uid: str, message: str = "") -> bool:
        """Kick player from server via REST API"""
        return await self.integration_manager.api_kick_player(player_uid, message)
    
    async def api_ban_player(self, player_uid: str, message: str = "") -> bool:
        """Ban player from server via REST API"""
        return await self.integration_manager.api_ban_player(player_uid, message)
    
    async def api_unban_player(self, player_uid: str) -> bool:
        """Unban player from server via REST API"""
        return await self.integration_manager.api_unban_player(player_uid)
    
    async def api_save_world(self) -> bool:
        """Save world data via REST API"""
        return await self.integration_manager.api_save_world()
    
    async def api_shutdown_server(self, waittime: int = 1, message: str = "Server shutdown") -> bool:
        """Shutdown server gracefully via REST API"""
        return await self.integration_manager.api_shutdown_server(waittime, message)
    
    def get_api_manager(self) -> IntegrationManager:
        """Get integration manager for direct API access"""
        return self.integration_manager
    
    def get_process_manager(self) -> ProcessManager:
        """Get process manager for direct process control"""
        return self.process_manager
    
    def get_config_manager(self) -> ConfigManager:
        """Get config manager for direct configuration control"""
        return self.config_manager
    
    def get_steamcmd_manager(self) -> SteamCMDManager:
        """Get SteamCMD manager for direct SteamCMD operations"""
        return self.steamcmd_manager
    
    def get_monitoring_manager(self) -> MonitoringManager:
        """Get monitoring manager for direct monitoring control"""
        return self.monitoring_manager
    
    def get_overall_status(self) -> dict:
        """Get comprehensive server status including startup state"""
        server_status = self.get_server_status()
        monitoring_status = self.monitoring_manager.get_monitoring_status()
        
        status = {
            "server": server_status,
            "monitoring": monitoring_status,
            "startup_completed": self._startup_completed,
            "backup_enabled": self.config.backup.enabled,
            "api_enabled": self.config.rest_api.enabled,
            "rcon_enabled": self.config.rcon.enabled,
            "discord_enabled": self.config.discord.enabled,
            "server_name": self.config.server.name,
            "max_players": self.config.server.max_players,
            "language": self.config.language
        }
        
        if self._backup_manager:
            try:
                backup_stats = self._backup_manager.get_backup_statistics()
                status["backup_stats"] = backup_stats
            except Exception as e:
                status["backup_error"] = str(e)
        
        return status
    
    def is_startup_completed(self) -> bool:
        """Check if full server startup process is completed"""
        return self._startup_completed


async def main():
    """Main production server function with API readiness verification"""
    config = get_config()
    setup_logging(
        log_level=config.monitoring.log_level,
        log_format_style=config.monitoring.log_format_style,
        log_dir=config.paths.log_dir,
        enable_console=True,
        enable_file=True
    )
    print("🚀 Starting Palworld Dedicated Server")
    print(f"   Server: {config.server.name}")
    print(f"   Port: {config.server.port}")
    print(f"   Max Players: {config.server.max_players}")
    
    async with PalworldServerManager(config) as manager:
        if config.steamcmd.update_on_start:
            print("📥 Downloading/updating server files...")
            download_success = await manager.download_server_files()
            if not download_success:
                print("❌ Server file download failed")
                return 1
        
        print("⚙️ Generating server settings...")
        manager.generate_server_settings()
        manager.generate_engine_settings()
        
        print("🎮 Starting Palworld server...")
        startup_success = await manager.start_server_with_verification()
        
        if startup_success:
            print("✅ Palworld server started successfully!")
            
            status = manager.get_overall_status()
            print(f"🎯 Monitoring active: {status['monitoring']['monitoring_active']}")
            print(f"✅ Startup completed: {status['startup_completed']}")
            
            try:
                print("🎯 Server operational. Monitoring in progress...")
                
                while manager.is_server_running():
                    await asyncio.sleep(60)
                    
                    monitoring_status = manager.get_monitoring_manager().get_monitoring_status()
                    current_players = monitoring_status.get('player_count', 0)
                    
                    current_time = time.time()
                    if not hasattr(main, '_last_status_time'):
                        main._last_status_time = current_time
                    
                    if (current_time - main._last_status_time) >= 300:
                        print(f"📊 Server operational - Players: {current_players}")
                        main._last_status_time = current_time
                    
            except KeyboardInterrupt:
                print("🛑 Received shutdown signal...")
                await manager.stop_server("Server shutdown requested")
        else:
            print("❌ Failed to start Palworld server")
            return 1
    
    print("👋 Palworld server manager stopped")
    return 0


if __name__ == "__main__":
    import sys
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
