#!/usr/bin/env python3
"""
Event dispatcher for Palworld server monitoring
Handles Discord notifications and other event-based actions
"""

import asyncio
from typing import Optional

from ..config_loader import PalworldConfig
from ..logging_setup import get_logger
from ..notifications import get_discord_notifier
from .player_monitor import PlayerEvent, PlayerEventType
from .server_monitor import ServerEvent, ServerEventType


class EventDispatcher:
    """Dispatch monitoring events to appropriate handlers (Discord, logging, etc.)"""
    
    def __init__(self, config: PalworldConfig):
        """
        Initialize event dispatcher
        
        Args:
            config: Server configuration
        """
        self.config = config
        self.logger = get_logger("palworld.monitoring.events")
        self.discord_notifier = get_discord_notifier(config)
        
        # Event handling configuration
        self._discord_enabled = config.discord.enabled
        self._language = config.language
    
    async def handle_player_event(self, event: PlayerEvent) -> None:
        """
        Handle player join/leave events
        
        Args:
            event: Player event to handle
        """
        try:
            if not self._discord_enabled:
                return
            
            async with self.discord_notifier as notifier:
                if event.event_type == PlayerEventType.JOINED:
                    await notifier.notify_player_join(
                        event.player_name,
                        event.player_count,
                        language=self._language
                    )
                    self.logger.info(f"Discord notification sent: {event.player_name} joined")
                    
                elif event.event_type == PlayerEventType.LEFT:
                    await notifier.notify_player_leave(
                        event.player_name, 
                        event.player_count,
                        language=self._language
                    )
                    self.logger.info(f"Discord notification sent: {event.player_name} left")
                    
        except Exception as e:
            self.logger.error(f"Failed to handle player event: {e}")
    
    async def handle_server_event(self, event: ServerEvent) -> None:
        """
        Handle server status events
        
        Args:
            event: Server event to handle
        """
        try:
            if not self._discord_enabled:
                return
            
            async with self.discord_notifier as notifier:
                if event.event_type == ServerEventType.STATUS_CHANGED:
                    if "started" in event.message.lower():
                        await notifier.notify_server_start(language=self._language)
                        self.logger.info("Discord notification sent: server started")
                    elif "stopped" in event.message.lower():
                        await notifier.notify_server_stop(
                            event.message, 
                            language=self._language
                        )
                        self.logger.info("Discord notification sent: server stopped")
                    elif "restarted" in event.message.lower():
                        await notifier.notify_error(
                            f"Server unexpectedly restarted: {event.details}",
                            language=self._language
                        )
                        self.logger.info("Discord notification sent: unexpected restart")
                        
                elif event.event_type == ServerEventType.HEALTH_WARNING:
                    await notifier.notify_error(
                        f"Server health warning: {event.details.get('issues', [])}",
                        language=self._language
                    )
                    self.logger.info("Discord notification sent: health warning")
                    
                elif event.event_type == ServerEventType.PERFORMANCE_ISSUE:
                    await notifier.notify_error(
                        f"Server performance issue: {event.message}",
                        language=self._language
                    )
                    self.logger.info("Discord notification sent: performance issue")
                    
        except Exception as e:
            self.logger.error(f"Failed to handle server event: {e}")
    
    async def handle_backup_completion(self, backup_info: dict) -> None:
        """
        Handle backup completion events
        
        Args:
            backup_info: Backup completion information
        """
        try:
            if not self._discord_enabled:
                return
            
            async with self.discord_notifier as notifier:
                await notifier.notify_backup_complete(language=self._language)
                self.logger.info("Discord notification sent: backup completed")
                
        except Exception as e:
            self.logger.error(f"Failed to handle backup completion: {e}")
    
    async def handle_error_event(self, error_message: str, error_details: Optional[dict] = None) -> None:
        """
        Handle general error events
        
        Args:
            error_message: Error message to send
            error_details: Additional error details
        """
        try:
            if not self._discord_enabled:
                return
            
            async with self.discord_notifier as notifier:
                await notifier.notify_error(error_message, language=self._language)
                self.logger.info(f"Discord error notification sent: {error_message}")
                
        except Exception as e:
            self.logger.error(f"Failed to handle error event: {e}")
