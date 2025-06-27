#!/usr/bin/env python3
"""
Discord notification system for Palworld server
Event-based notifications with webhook integration
"""

import asyncio
import aiohttp
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum

from ..config_loader import PalworldConfig
from ..logging_setup import get_logger, log_server_event


class NotificationLevel(Enum):
    """Notification priority levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class DiscordNotifier:
    """Discord webhook notification manager"""
    
    def __init__(self, config: PalworldConfig):
        self.config = config
        self.logger = get_logger("palworld.discord")
        
        # Discord settings
        self.webhook_url = config.discord.webhook_url
        self.enabled = config.discord.enabled and bool(self.webhook_url)
        self.mention_role = config.discord.mention_role
        self.events = config.discord.events
        
        # HTTP session for webhook calls
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Color mapping for different notification levels
        self.level_colors = {
            NotificationLevel.INFO: 0x00FF00,      # Green
            NotificationLevel.WARNING: 0xFFFF00,   # Yellow
            NotificationLevel.ERROR: 0xFF0000,     # Red
            NotificationLevel.CRITICAL: 0x8B0000   # Dark Red
        }
        
        # Emoji mapping for events
        self.event_emojis = {
            "server_start": "🚀",
            "server_stop": "🛑",
            "server_restart": "🔄",
            "server_crash": "💥",
            "player_join": "👤",
            "player_leave": "👋",
            "player_kick": "🦵",
            "player_ban": "🚫",
            "backup_complete": "📦",
            "backup_fail": "💔",
            "error": "❌",
            "warning": "⚠️",
            "info": "ℹ️"
        }
    
    async def __aenter__(self):
        """Async context manager enter"""
        if self.enabled:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def send_notification(
        self, 
        event_type: str, 
        title: str, 
        description: str,
        level: NotificationLevel = NotificationLevel.INFO,
        fields: Optional[List[Dict[str, Any]]] = None,
        thumbnail_url: Optional[str] = None
    ) -> bool:
        """
        Send Discord notification
        
        Args:
            event_type: Type of event (server_start, player_join, etc.)
            title: Notification title
            description: Notification description
            level: Notification priority level
            fields: Additional fields for embed
            thumbnail_url: Thumbnail image URL
            
        Returns:
            Success status
        """
        if not self.enabled:
            self.logger.debug("Discord notifications disabled")
            return False
        
        # Check if this event type is enabled
        if event_type not in self.events or not self.events[event_type]:
            self.logger.debug(
                "Event type disabled in configuration", 
                event_type=event_type
            )
            return False
        
        if not self.session:
            self.logger.error("Discord session not initialized")
            return False
        
        try:
            # Build Discord embed
            embed = self._build_embed(
                event_type, title, description, level, fields, thumbnail_url
            )
            
            # Build webhook payload
            payload = {
                "embeds": [embed]
            }
            
            # Add role mention if configured
            if self.mention_role:
                payload["content"] = f"<@&{self.mention_role}>"
            
            # Send webhook request
            async with self.session.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                
                if response.status == 204:  # Discord webhook success
                    log_server_event(
                        self.logger, "discord_send",
                        f"Discord notification sent: {title}",
                        event_type=event_type,
                        level=level.value
                    )
                    return True
                else:
                    error_text = await response.text()
                    self.logger.error(
                        "Discord webhook failed",
                        status_code=response.status,
                        error=error_text
                    )
                    return False
                    
        except Exception as e:
            self.logger.error("Discord notification error", error=str(e))
            return False
    
    def _build_embed(
        self,
        event_type: str,
        title: str,
        description: str,
        level: NotificationLevel,
        fields: Optional[List[Dict[str, Any]]],
        thumbnail_url: Optional[str]
    ) -> Dict[str, Any]:
        """Build Discord embed object"""
        
        # Get emoji for event type
        emoji = self.event_emojis.get(event_type, "📝")
        
        # Build embed
        embed = {
            "title": f"{emoji} {title}",
            "description": description,
            "color": self.level_colors[level],
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": f"Palworld Server: {self.config.server.name}",
                "icon_url": "https://cdn.steamgriddb.com/icon/6c0c19b75286333084e25b4db6c8de22.ico"
            }
        }
        
        # Add thumbnail if provided
        if thumbnail_url:
            embed["thumbnail"] = {"url": thumbnail_url}
        
        # Add fields if provided
        if fields:
            embed["fields"] = fields
        
        return embed
    
    # Convenience methods for common events
    async def notify_server_start(
        self, 
        server_name: str, 
        port: int, 
        max_players: int
    ) -> bool:
        """Notify server start"""
        fields = [
            {"name": "Port", "value": str(port), "inline": True},
            {"name": "Max Players", "value": str(max_players), "inline": True},
            {"name": "Status", "value": "🟢 Online", "inline": True}
        ]
        
        return await self.send_notification(
            "server_start",
            "Server Started",
            f"Palworld server **{server_name}** is now online and ready for players!",
            NotificationLevel.INFO,
            fields
        )
    
    async def notify_server_stop(self, server_name: str, reason: str = "") -> bool:
        """Notify server stop"""
        description = f"Palworld server **{server_name}** has been stopped."
        if reason:
            description += f"\n\n**Reason:** {reason}"
        
        fields = [
            {"name": "Status", "value": "🔴 Offline", "inline": True}
        ]
        
        return await self.send_notification(
            "server_stop",
            "Server Stopped",
            description,
            NotificationLevel.WARNING,
            fields
        )
    
    async def notify_player_join(self, player_name: str, player_count: int) -> bool:
        """Notify player join"""
        fields = [
            {"name": "Player", "value": player_name, "inline": True},
            {"name": "Online Players", "value": str(player_count), "inline": True}
        ]
        
        return await self.send_notification(
            "player_join",
            "Player Joined",
            f"**{player_name}** joined the server!",
            NotificationLevel.INFO,
            fields
        )
    
    async def notify_player_leave(self, player_name: str, player_count: int) -> bool:
        """Notify player leave"""
        fields = [
            {"name": "Player", "value": player_name, "inline": True},
            {"name": "Online Players", "value": str(player_count), "inline": True}
        ]
        
        return await self.send_notification(
            "player_leave",
            "Player Left",
            f"**{player_name}** left the server.",
            NotificationLevel.INFO,
            fields
        )
    
    async def notify_backup_complete(
        self, 
        backup_filename: str, 
        size_mb: float, 
        duration: float
    ) -> bool:
        """Notify backup completion"""
        fields = [
            {"name": "File", "value": backup_filename, "inline": False},
            {"name": "Size", "value": f"{size_mb:.2f} MB", "inline": True},
            {"name": "Duration", "value": f"{duration:.1f}s", "inline": True}
        ]
        
        return await self.send_notification(
            "backup_complete",
            "Backup Completed",
            "Server backup has been created successfully!",
            NotificationLevel.INFO,
            fields
        )
    
    async def notify_backup_failed(self, error: str) -> bool:
        """Notify backup failure"""
        return await self.send_notification(
            "backup_fail",
            "Backup Failed",
            f"Server backup failed with error:\n\n``````",
            NotificationLevel.ERROR
        )
    
    async def notify_error(self, title: str, error_message: str) -> bool:
        """Notify general error"""
        return await self.send_notification(
            "error",
            title,
            f"``````",
            NotificationLevel.ERROR
        )
    
    async def notify_warning(self, title: str, warning_message: str) -> bool:
        """Notify general warning"""
        return await self.send_notification(
            "warning",
            title,
            warning_message,
            NotificationLevel.WARNING
        )


# Global Discord notifier instance
_discord_notifier: Optional[DiscordNotifier] = None


def get_discord_notifier(config: Optional[PalworldConfig] = None) -> DiscordNotifier:
    """Return global Discord notifier instance"""
    global _discord_notifier
    
    if _discord_notifier is None:
        from ..config_loader import get_config
        _discord_notifier = DiscordNotifier(config or get_config())
    
    return _discord_notifier


async def main():
    """Test run"""
    from ..config_loader import get_config
    
    config = get_config()
    
    async with DiscordNotifier(config) as notifier:
        print("🚀 Discord notifier test start")
        
        if not notifier.enabled:
            print("❌ Discord notifications not configured")
            return
        
        # Test notifications
        await notifier.notify_server_start("Test Server", 8211, 32)
        await asyncio.sleep(1)
        
        await notifier.notify_player_join("TestPlayer", 1)
        await asyncio.sleep(1)
        
        await notifier.notify_backup_complete("test_backup.tar.gz", 15.5, 2.3)
        
        print("✅ Discord notifier test complete!")


if __name__ == "__main__":
    asyncio.run(main())
