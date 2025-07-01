#!/usr/bin/env python3
"""
Monitoring manager for Palworld server
Orchestrates all monitoring components and handles their lifecycle
"""

import asyncio
from typing import Set, Optional

from ..config_loader import PalworldConfig
from ..logging_setup import get_logger
from .player_monitor import PlayerMonitor, PlayerEventType
from .server_monitor import ServerMonitor, ServerEventType
from .event_dispatcher import EventDispatcher
from .idle_restart_manager import IdleRestartManager


class MonitoringManager:
    """Central manager for all monitoring components"""
    
    def __init__(self, config: PalworldConfig, process_manager, api_manager):
        """Initialize monitoring manager"""
        self.config = config
        self.logger = get_logger("palworld.monitoring.manager")
        
        self.player_monitor = PlayerMonitor(config, api_manager)
        self.server_monitor = ServerMonitor(config, process_manager, api_manager)
        self.event_dispatcher = EventDispatcher(config)
        self.idle_restart_manager = IdleRestartManager(config, self.player_monitor, process_manager)
        
        self._background_tasks: Set[asyncio.Task] = set()
        self._monitoring_active = False
        self._shutdown_event = asyncio.Event()
        
        self._setup_event_callbacks()
    
    def _setup_event_callbacks(self) -> None:
        """Setup event callbacks for monitoring components"""
        self.player_monitor.add_event_callback(
            PlayerEventType.JOINED,
            self.event_dispatcher.handle_player_event
        )
        self.player_monitor.add_event_callback(
            PlayerEventType.LEFT,
            self.event_dispatcher.handle_player_event
        )
        
        self.server_monitor.add_event_callback(
            ServerEventType.STATUS_CHANGED,
            self.event_dispatcher.handle_server_event
        )
        self.server_monitor.add_event_callback(
            ServerEventType.HEALTH_WARNING,
            self.event_dispatcher.handle_server_event
        )
        self.server_monitor.add_event_callback(
            ServerEventType.PERFORMANCE_ISSUE,
            self.event_dispatcher.handle_server_event
        )
    
    async def start_monitoring(self) -> None:
        """Start all monitoring components"""
        if self._monitoring_active:
            self.logger.warning("Monitoring already active")
            return
        
        self._monitoring_active = True
        self._shutdown_event.clear()
        self.logger.info("🚀 Starting comprehensive monitoring system")
        
        try:
            if self.config.discord.enabled:
                player_task = asyncio.create_task(self.player_monitor.start_monitoring())
                self._background_tasks.add(player_task)
                player_task.add_done_callback(self._background_tasks.discard)
                self.logger.info("👥 Player monitoring started")
            
            server_task = asyncio.create_task(self.server_monitor.start_monitoring())
            self._background_tasks.add(server_task)
            server_task.add_done_callback(self._background_tasks.discard)
            self.logger.info("🖥️ Server monitoring started")
            
            # Start idle restart monitoring
            idle_restart_task = asyncio.create_task(self.idle_restart_manager.start_monitoring())
            self._background_tasks.add(idle_restart_task)
            idle_restart_task.add_done_callback(self._background_tasks.discard)
            self.logger.info("⏰ Idle restart monitoring started")
            
        except Exception as e:
            self.logger.error(f"Failed to start monitoring: {e}")
            await self.stop_monitoring()
            raise
    
    async def stop_monitoring(self) -> None:
        """Stop all monitoring components"""
        if not self._monitoring_active:
            return
        
        self.logger.info("🛑 Stopping monitoring system")
        self._shutdown_event.set()
        
        await self.player_monitor.stop_monitoring()
        await self.server_monitor.stop_monitoring()
        await self.idle_restart_manager.stop_monitoring()
        
        if self._background_tasks:
            self.logger.info(f"Cancelling {len(self._background_tasks)} background tasks")
            for task in self._background_tasks:
                task.cancel()
            
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
            self._background_tasks.clear()
        
        self._monitoring_active = False
        self.logger.info("✅ Monitoring system stopped")
    
    async def handle_backup_completion(self, backup_info: dict) -> None:
        """Handle backup completion events"""
        await self.event_dispatcher.handle_backup_completion(backup_info)
    
    async def handle_error(self, error_message: str, error_details: Optional[dict] = None) -> None:
        """Handle general error events"""
        await self.event_dispatcher.handle_error_event(error_message, error_details)
    
    def get_monitoring_status(self) -> dict:
        """Get comprehensive monitoring status"""
        return {
            "monitoring_active": self._monitoring_active,
            "player_monitoring": self.player_monitor.is_monitoring_active(),
            "server_monitoring": self.server_monitor.is_monitoring_active(),
            "idle_restart_monitoring": self.idle_restart_manager.is_monitoring_active(),
            "discord_enabled": self.config.discord.enabled,
            "current_players": list(self.player_monitor.get_current_players()),
            "player_count": self.player_monitor.get_current_player_count(),
            "last_server_status": self.server_monitor.get_last_status(),
            "idle_restart_status": self.idle_restart_manager.get_idle_status(),
            "background_tasks": len(self._background_tasks)
        }
    
    def is_monitoring_active(self) -> bool:
        """Check if monitoring system is active"""
        return self._monitoring_active
