#!/usr/bin/env python3
"""
Palworld server manager - Main orchestrator
Simplified main manager that delegates to specialized components
"""

import asyncio
from typing import Optional, Any

from .config_loader import PalworldConfig, get_config
from .logging_setup import get_logger, log_server_event

# Import specialized managers
from .clients import SteamCMDManager
from .managers import ProcessManager, ConfigManager, IntegrationManager


class PalworldServerManager:
    """Main Palworld server orchestrator - delegates to specialized managers"""
    
    def __init__(self, config: Optional[PalworldConfig] = None):
        """
        Initialize server manager with specialized components
        
        Args:
            config: Server configuration (loads default if None)
        """
        self.config = config or get_config()
        self.logger = get_logger("palworld.server")
        
        # Initialize specialized managers
        self.steamcmd_manager = SteamCMDManager(
            self.config.paths.steamcmd_dir, 
            self.logger
        )
        self.process_manager = ProcessManager(self.config, self.logger)
        self.config_manager = ConfigManager(self.config, self.logger)
        self.integration_manager = IntegrationManager(self.config, self.logger)
        
        # Component state
        self._backup_manager: Optional[Any] = None
        self._monitoring_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
    
    async def __aenter__(self):
        """Async context manager enter - initialize all components"""
        # Initialize API clients
        await self.integration_manager.initialize_clients()
        
        # Create necessary directories
        self._ensure_directories()
        
        # Initialize backup manager if enabled
        if self.config.backup.enabled:
            from .backup.backup_manager import get_backup_manager
            self._backup_manager = get_backup_manager(self.config)
            await self._backup_manager.start_backup_scheduler()
            self.logger.info(f"Backup system started with {self.config.backup.interval_seconds}s interval")
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleanup all components"""
        # Stop monitoring
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        # Stop server
        if self.process_manager.is_server_running():
            await self.process_manager.stop_server(
                "System shutdown", 
                self.integration_manager.get_api_client()
            )
        
        # Stop backup manager
        if self._backup_manager:
            await self._backup_manager.stop_backup_scheduler()
        
        # Cleanup API clients
        await self.integration_manager.cleanup_clients()
    
    def _ensure_directories(self) -> None:
        """Create necessary directories"""
        directories = [
            self.config.paths.server_dir,
            self.config.paths.backup_dir,
            self.config.paths.log_dir,
            self.config.paths.server_dir / "Pal" / "Saved" / "Config" / "LinuxServer"
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            self.logger.debug("Directory check/create", path=str(directory))
    
    # SteamCMD operations (direct delegation)
    async def download_server_files(self) -> bool:
        """Download/update Palworld server files"""
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
        
        return success
    
    # Server process operations (delegation to ProcessManager)
    def is_server_running(self) -> bool:
        """Check if server is currently running"""
        return self.process_manager.is_server_running()
    
    def start_server(self) -> bool:
        """Start Palworld server"""
        return self.process_manager.start_server()
    
    async def stop_server(self, message: str = "Server is shutting down") -> bool:
        """Stop Palworld server gracefully"""
        return await self.process_manager.stop_server(
            message, 
            self.integration_manager.get_api_client()
        )
    
    def get_server_status(self) -> dict:
        """Get detailed server process status"""
        return self.process_manager.get_server_status()
    
    # Configuration operations (delegation to ConfigManager)
    def generate_server_settings(self) -> bool:
        """Generate server settings file"""
        return self.config_manager.generate_server_settings()
    
    def generate_engine_settings(self) -> bool:
        """Generate engine settings file"""
        return self.config_manager.generate_engine_settings()
    
    # API operations (delegation to IntegrationManager)
    async def get_server_info_any(self):
        """Get server info using available API"""
        return await self.integration_manager.get_server_info_any()
    
    async def announce_message_any(self, message: str) -> bool:
        """Announce message using available API"""
        return await self.integration_manager.announce_message_any(message)
    
    async def save_world_any(self) -> bool:
        """Save world using available API"""
        return await self.integration_manager.save_world_any()
    
    # REST API wrapper methods (for backward compatibility)
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
    
    # RCON wrapper methods (for backward compatibility)
    async def rcon_get_server_info(self):
        """Get server information via RCON"""
        return await self.integration_manager.rcon_get_server_info()
    
    async def rcon_get_players(self):
        """Get online player list via RCON"""
        return await self.integration_manager.rcon_get_players()
    
    async def rcon_announce_message(self, message: str) -> bool:
        """Announce message to all players via RCON"""
        return await self.integration_manager.rcon_announce_message(message)
    
    async def rcon_kick_player(self, player_name: str) -> bool:
        """Kick player from server via RCON"""
        return await self.integration_manager.rcon_kick_player(player_name)
    
    async def rcon_ban_player(self, player_name: str) -> bool:
        """Ban player from server via RCON"""
        return await self.integration_manager.rcon_ban_player(player_name)
    
    async def rcon_save_world(self) -> bool:
        """Save world data via RCON"""
        return await self.integration_manager.rcon_save_world()
    
    async def rcon_shutdown_server(self, waittime: int = 1, message: str = "Server shutdown") -> bool:
        """Shutdown server gracefully via RCON"""
        return await self.integration_manager.rcon_shutdown_server(waittime, message)
    
    async def rcon_execute_command(self, command: str, *args: str):
        """Execute custom RCON command"""
        return await self.integration_manager.rcon_execute_command(command, *args)
    
    # Advanced access methods for direct manager control
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
    
    # Monitoring and status methods
    def get_overall_status(self) -> dict:
        """Get comprehensive server status"""
        server_status = self.get_server_status()
        
        status = {
            "server": server_status,
            "backup_enabled": self.config.backup.enabled,
            "api_enabled": self.config.rest_api.enabled,
            "rcon_enabled": self.config.rcon.enabled,
            "server_name": self.config.server.name,
            "max_players": self.config.server.max_players
        }
        
        if self._backup_manager:
            try:
                backup_stats = self._backup_manager.get_backup_statistics()
                status["backup_stats"] = backup_stats
            except Exception as e:
                status["backup_error"] = str(e)
        
        return status


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
            
            # Display overall status
            status = manager.get_overall_status()
            print(f"📊 Backup enabled: {status['backup_enabled']}")
            print(f"🔌 API enabled: {status['api_enabled']}")
            print(f"⚡ RCON enabled: {status['rcon_enabled']}")
             
            try:
                while manager.is_server_running():
                    await asyncio.sleep(30)   
                    print(f"📊 Server status: Running (PID: {status['server'].get('pid', 'N/A')})")
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
