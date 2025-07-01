#!/usr/bin/env python3
"""
Palworld server manager - Main orchestrator with Discord notifications
Simplified main manager that delegates to specialized components
"""

import asyncio
from typing import Optional, Any, Set

from .config_loader import PalworldConfig, get_config
from .logging_setup import get_logger, log_server_event

# Import specialized managers
from .clients import SteamCMDManager
from .managers import ProcessManager, ConfigManager, IntegrationManager

# Import Discord notifications
from .notifications import get_discord_notifier


class PalworldServerManager:
    """Main Palworld server orchestrator with Discord integration"""
    
    def __init__(self, config: Optional[PalworldConfig] = None):
        """
        Initialize server manager with specialized components and Discord notifications
        
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
        
        # Initialize Discord notifier
        self.discord_notifier = get_discord_notifier(self.config)
        
        # Component state
        self._backup_manager: Optional[Any] = None
        self._monitoring_task: Optional[asyncio.Task] = None
        self._player_monitoring_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        # Player tracking for Discord notifications
        self._previous_players: Set[str] = set()
        self._first_player_check = True
    
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
        
        # Start player monitoring task for Discord notifications
        if self.discord_notifier.enabled:
            self._player_monitoring_task = asyncio.create_task(self._monitor_players_for_discord())
            self.logger.info("Discord player monitoring started")
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleanup all components"""
        # Set shutdown event to stop monitoring tasks
        self._shutdown_event.set()
        
        # Stop player monitoring
        if self._player_monitoring_task:
            self._player_monitoring_task.cancel()
            try:
                await self._player_monitoring_task
            except asyncio.CancelledError:
                pass
        
        # Stop monitoring
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        # Stop server with Discord notification
        if self.process_manager.is_server_running():
            await self.stop_server("System shutdown")
        
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
    
    async def _monitor_players_for_discord(self) -> None:
        """Monitor player join/leave events and send Discord notifications"""
        self.logger.info("Starting Discord player monitoring task")
        
        while not self._shutdown_event.is_set():
            try:
                # Get current player list
                players_response = await self.api_get_players()
                current_players = set()
                
                if players_response and 'players' in players_response:
                    current_players = {player.get('name', 'Unknown') for player in players_response['players']}
                
                # Skip first check to avoid false notifications on startup
                if not self._first_player_check:
                    # Detect joined players
                    joined_players = current_players - self._previous_players
                    # Detect left players
                    left_players = self._previous_players - current_players
                    
                    # Send Discord notifications for joined players
                    if joined_players:
                        async with self.discord_notifier as notifier:
                            for player_name in joined_players:
                                await notifier.notify_player_join(
                                    player_name, 
                                    len(current_players)
                                )
                                self.logger.info(f"Discord notification sent: {player_name} joined")
                    
                    # Send Discord notifications for left players
                    if left_players:
                        async with self.discord_notifier as notifier:
                            for player_name in left_players:
                                await notifier.notify_player_leave(
                                    player_name, 
                                    len(current_players)
                                )
                                self.logger.info(f"Discord notification sent: {player_name} left")
                
                # Update player tracking
                self._previous_players = current_players
                self._first_player_check = False
                
            except Exception as e:
                self.logger.error(f"Player monitoring error: {e}")
                # Send Discord error notification if this is a recurring issue
                try:
                    async with self.discord_notifier as notifier:
                        await notifier.notify_error(f"Player monitoring error: {str(e)}")
                except Exception as discord_error:
                    self.logger.error(f"Failed to send Discord error notification: {discord_error}")
            
            # Wait before next check
            await asyncio.sleep(10)  # Check every 10 seconds
    
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
            # Send Discord error notification
            try:
                async with self.discord_notifier as notifier:
                    await notifier.notify_error("Server file download failed")
            except Exception as e:
                self.logger.error(f"Failed to send Discord notification: {e}")
        
        return success
    
    # Server process operations (delegation to ProcessManager)
    def is_server_running(self) -> bool:
        """Check if server is currently running"""
        return self.process_manager.is_server_running()
    
    def start_server(self) -> bool:
        """Start Palworld server with Discord notification"""
        success = self.process_manager.start_server()
        
        if success:
            # Send Discord notification for server start
            try:
                asyncio.create_task(self._notify_server_start())
            except Exception as e:
                self.logger.error(f"Failed to schedule Discord notification: {e}")
        else:
            # Send Discord notification for server start failure
            try:
                asyncio.create_task(self._notify_server_start_failed())
            except Exception as e:
                self.logger.error(f"Failed to schedule Discord notification: {e}")
        
        return success
    
    async def _notify_server_start(self) -> None:
        """Send Discord notification for server start"""
        try:
            async with self.discord_notifier as notifier:
                await notifier.notify_server_start()
                self.logger.info("Discord notification sent: server started")
        except Exception as e:
            self.logger.error(f"Failed to send Discord server start notification: {e}")
    
    async def _notify_server_start_failed(self) -> None:
        """Send Discord notification for server start failure"""
        try:
            async with self.discord_notifier as notifier:
                await notifier.notify_error("Failed to start Palworld server")
                self.logger.info("Discord notification sent: server start failed")
        except Exception as e:
            self.logger.error(f"Failed to send Discord error notification: {e}")
    
    async def stop_server(self, message: str = "Server is shutting down") -> bool:
        """Stop Palworld server gracefully with Discord notification"""
        # Send Discord notification before stopping
        try:
            async with self.discord_notifier as notifier:
                await notifier.notify_server_stop(message)
                self.logger.info("Discord notification sent: server stopping")
        except Exception as e:
            self.logger.error(f"Failed to send Discord stop notification: {e}")
        
        # Stop the server
        result = await self.process_manager.stop_server(
            message, 
            self.integration_manager.get_api_client()
        )
        
        return result
    
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
    
    # Backup integration with Discord notifications
    async def _handle_backup_completion(self) -> None:
        """Handle backup completion with Discord notification"""
        try:
            async with self.discord_notifier as notifier:
                await notifier.notify_backup_complete()
                self.logger.info("Discord notification sent: backup completed")
        except Exception as e:
            self.logger.error(f"Failed to send Discord backup notification: {e}")
    
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
    
    def get_discord_notifier(self):
        """Get Discord notifier for direct notification control"""
        return self.discord_notifier
    
    # Monitoring and status methods
    def get_overall_status(self) -> dict:
        """Get comprehensive server status"""
        server_status = self.get_server_status()
        
        status = {
            "server": server_status,
            "backup_enabled": self.config.backup.enabled,
            "api_enabled": self.config.rest_api.enabled,
            "rcon_enabled": self.config.rcon.enabled,
            "discord_enabled": self.discord_notifier.enabled,
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
        
        # Add Discord status
        if self.discord_notifier.enabled:
            status["discord_status"] = self.discord_notifier.get_event_status()
        
        return status


async def main():
    """Main production server function with Discord integration"""
    config = get_config()
    
    print("🚀 Starting Palworld Dedicated Server with Discord Integration")
    print(f"   Server: {config.server.name}")
    print(f"   Port: {config.server.port}")
    print(f"   Max Players: {config.server.max_players}")
    print(f"   Discord: {'Enabled' if config.discord.enabled else 'Disabled'}")
    print(f"   Language: {config.language}")
    
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
            print(f"💬 Discord enabled: {status['discord_enabled']}")
            
            if status['discord_enabled']:
                print("🎊 Discord notifications are active!")
                print("   - Server start/stop notifications")
                print("   - Player join/leave notifications")
                print("   - Backup completion notifications")
                print("   - Error notifications")
             
            try:
                # Main server monitoring loop
                while manager.is_server_running():
                    await asyncio.sleep(30)   
                    current_status = manager.get_server_status()
                    print(f"📊 Server status: Running (PID: {current_status.get('pid', 'N/A')})")
                    
                    # Check for backup completion and send Discord notification
                    if manager._backup_manager:
                        try:
                            # This would be triggered by the backup manager
                            # For now, we just ensure the backup system is running
                            pass
                        except Exception as e:
                            print(f"Backup system error: {e}")
                            try:
                                async with manager.discord_notifier as notifier:
                                    await notifier.notify_error(f"Backup system error: {str(e)}")
                            except Exception as discord_error:
                                print(f"Failed to send Discord error notification: {discord_error}")
                                
            except KeyboardInterrupt:
                print("🛑 Received shutdown signal...")
                await manager.stop_server("Server shutdown requested")
        else:
            print("❌ Failed to start Palworld server")
            # Send Discord notification for startup failure
            try:
                async with manager.discord_notifier as notifier:
                    await notifier.notify_error("Failed to start Palworld server")
            except Exception as e:
                print(f"Failed to send Discord notification: {e}")
            return 1
    
    print("👋 Palworld server manager stopped")
    return 0


if __name__ == "__main__":
    import sys
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
