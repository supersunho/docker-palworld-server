#!/usr/bin/env python3
"""
Idle-based server auto-restart manager
Restarts the server if no players are online for a configurable duration
"""

import asyncio
import time
from typing import Optional
from dataclasses import dataclass

from ..config_loader import PalworldConfig
from ..logging_setup import get_logger, log_server_event
from ..notifications import get_discord_notifier


@dataclass
class IdleRestartStats:
    """Idle restart statistics"""
    total_restarts: int = 0
    last_restart_time: Optional[float] = None
    current_idle_duration: float = 0.0
    longest_idle_duration: float = 0.0


class IdleRestartManager:
    """
    Monitors player activity and automatically restarts server when idle
    Integrates with Discord notifications and multi-language support
    """
    
    def __init__(self, config: PalworldConfig, player_monitor, process_manager):
        """Initialize idle restart manager with configuration"""
        self.config = config
        self.player_monitor = player_monitor
        self.process_manager = process_manager
        self.logger = get_logger("palworld.idle_restart")
        
        idle_config = getattr(config.monitoring, 'idle_restart', None)
        if idle_config:
            self.enabled = idle_config.enabled
            self.idle_minutes = idle_config.idle_minutes
        else:
            self.enabled = True
            self.idle_minutes = 30
        
        self.discord_notify = config.discord.events.get('idle_restart', True)
        self.idle_seconds = self.idle_minutes * 60
        self.check_interval = 30
        
        self._idle_start: Optional[float] = None
        self._running = False
        self._monitoring_task: Optional[asyncio.Task] = None
        self.stats = IdleRestartStats()
        
        if self.enabled:
            log_server_event(
                self.logger, "idle_restart_init",
                f"Idle restart manager initialized",
                idle_minutes=self.idle_minutes,
                discord_enabled=self.discord_notify
            )
        else:
            self.logger.info("🚫 Idle restart manager disabled by configuration")
    
    async def start_monitoring(self) -> None:
        """Start idle monitoring loop"""
        if not self.enabled:
            self.logger.warning("⚠️ Idle restart monitoring is disabled")
            return
        
        if self._running:
            self.logger.warning("⚠️ Idle restart monitoring already running")
            return
        
        self._running = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        log_server_event(
            self.logger, "idle_monitoring_start",
            f"🟢 Idle restart monitoring started (threshold: {self.idle_minutes} minutes)"
        )
    
    async def stop_monitoring(self) -> None:
        """Stop idle monitoring loop"""
        if not self._running:
            return
        
        self._running = False
        
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        log_server_event(
            self.logger, "idle_monitoring_stop",
            "🛑 Idle restart monitoring stopped"
        )
    
    async def _monitoring_loop(self) -> None:
        """Main monitoring loop for idle detection"""
        while self._running:
            try:
                await self._check_idle_status()
                await asyncio.sleep(self.check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("🔥 Idle monitoring loop error", error=str(e))
                await asyncio.sleep(10)
    
    async def _check_idle_status(self) -> None:
        """Check current idle status and trigger restart if needed"""
        if not self.process_manager.is_server_running():
            if self._idle_start is not None:
                self.logger.debug("🔄 Server not running, resetting idle timer")
                self._idle_start = None
            return
        
        current_player_count = self.player_monitor.get_current_player_count()
        current_time = time.time()
        
        if current_player_count == 0:
            await self._handle_zero_players(current_time)
        else:
            await self._handle_active_players(current_player_count)
    
    async def _handle_zero_players(self, current_time: float) -> None:
        """Handle server state when no players are online"""
        if self._idle_start is None:
            self._idle_start = current_time
            self.logger.info("⏳ No players online - idle timer started")
            return
        
        idle_duration = current_time - self._idle_start
        self.stats.current_idle_duration = idle_duration
        
        if idle_duration > self.stats.longest_idle_duration:
            self.stats.longest_idle_duration = idle_duration
        
        minutes_elapsed = int(idle_duration // 60)
        
        if minutes_elapsed > 0 and minutes_elapsed % 5 == 0:
            remaining_minutes = self.idle_minutes - minutes_elapsed
            if remaining_minutes > 0:
                self.logger.debug(
                    f"⏱️ Server idle for {minutes_elapsed} minutes "
                    f"({remaining_minutes} minutes until restart)"
                )
        
        if idle_duration >= self.idle_seconds:
            await self._trigger_idle_restart()
    
    async def _handle_active_players(self, player_count: int) -> None:
        """Handle server state when players are online"""
        if self._idle_start is not None:
            idle_duration = time.time() - self._idle_start
            minutes_idle = int(idle_duration // 60)
            
            self.logger.info(
                f"👥 Players online ({player_count}) - idle timer reset "
                f"(was idle for {minutes_idle} minutes)"
            )
            
            self._idle_start = None
            self.stats.current_idle_duration = 0.0
    
    async def _trigger_idle_restart(self) -> None:
        """Trigger server restart due to idle timeout"""
        self.logger.warning(
            f"🔄 Server idle for {self.idle_minutes} minutes - triggering restart"
        )
        
        await self._send_discord_notification()
        
        try:
            restart_success = await self._perform_restart()
            
            if restart_success:
                self.stats.total_restarts += 1
                self.stats.last_restart_time = time.time()
                
                log_server_event(
                    self.logger, "idle_restart_success",
                    "✅ Server successfully restarted due to idle timeout",
                    total_restarts=self.stats.total_restarts,
                    idle_minutes=self.idle_minutes
                )
            else:
                log_server_event(
                    self.logger, "idle_restart_fail",
                    "❌ Failed to restart server due to idle timeout"
                )
            
        except Exception as e:
            self.logger.error("🔥 Idle restart failed", error=str(e))
        finally:
            self._idle_start = None
            self.stats.current_idle_duration = 0.0
    
    async def _send_discord_notification(self) -> None:
        """Send Discord notification about idle restart"""
        if not self.discord_notify or not self.config.discord.enabled:
            self.logger.debug("📝 Discord notification skipped (disabled)")
            return
        
        try:
            notifier = get_discord_notifier(self.config)
            async with notifier:
                await notifier._send_notification(
                    "idle_restart",
                    "idle.restart",
                    level=notifier.NotificationLevel.WARNING,
                    language=self.config.language,
                    minutes=self.idle_minutes,
                    server=self.config.server.name
                )
                
                self.logger.info("📣 Discord notification sent for idle restart")
                
        except Exception as e:
            self.logger.error("📧 Failed to send Discord notification", error=str(e))
    
    async def _perform_restart(self) -> bool:
        """Perform the actual server restart"""
        try:
            stop_success = await self.process_manager.stop_server(
                f"Automatic restart after {self.idle_minutes} minutes of inactivity"
            )
            
            if not stop_success:
                self.logger.error("❌ Failed to stop server gracefully")
                return False
            
            await asyncio.sleep(5)
            
            start_success = self.process_manager.start_server()
            
            if not start_success:
                self.logger.error("❌ Failed to start server after idle restart")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error("🔥 Error during server restart", error=str(e))
            return False
    
    def get_idle_status(self) -> dict:
        """Get current idle status information"""
        current_time = time.time()
        
        if self._idle_start is None:
            idle_duration = 0.0
            remaining_time = self.idle_seconds
        else:
            idle_duration = current_time - self._idle_start
            remaining_time = max(0, self.idle_seconds - idle_duration)
        
        return {
            "enabled": self.enabled,
            "monitoring_active": self._running,
            "idle_threshold_minutes": self.idle_minutes,
            "current_idle_seconds": idle_duration,
            "remaining_seconds_until_restart": remaining_time,
            "is_currently_idle": self._idle_start is not None,
            "discord_notifications": self.discord_notify,
            "statistics": {
                "total_restarts": self.stats.total_restarts,
                "last_restart_time": self.stats.last_restart_time,
                "longest_idle_duration": self.stats.longest_idle_duration
            }
        }
    
    def is_monitoring_active(self) -> bool:
        """Check if idle monitoring is currently active"""
        return self._running
