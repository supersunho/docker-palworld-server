#!/usr/bin/env python3
"""
Discord notification system for Palworld server
Event-based notifications with webhook integration and multi-language support
Uses config_loader.py for consistent configuration management
"""

import asyncio
import aiohttp
from datetime import datetime
from typing import Dict, Any, Optional
from enum import Enum

from ..config_loader import PalworldConfig
from ..logging_setup import get_logger, log_server_event
from .message_loader import get_message_loader


class NotificationLevel(Enum):
    """Notification priority levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class DiscordNotifier:
    """Discord webhook notification manager using config_loader.py consistently"""
    
    def __init__(self, config: PalworldConfig):
        """Initialize Discord notifier with configuration from config_loader"""
        self.config = config
        self.logger = get_logger("palworld.discord")
        
        # Load message loader for multi-language support
        self.message_loader = get_message_loader()
        
        # Discord settings from config_loader (NO os.getenv usage)
        self.webhook_url = config.discord.webhook_url
        self.enabled = config.discord.enabled and bool(self.webhook_url)
        self.mention_role = config.discord.mention_role
        self.events = config.discord.events
        
        # Language settings from config_loader
        self.default_language = config.language
        
        # HTTP session for webhook calls
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Community-friendly color mapping
        self.level_colors = {
            NotificationLevel.INFO: 0x00FF7F,      # Bright Green
            NotificationLevel.WARNING: 0xFFD700,   # Gold
            NotificationLevel.ERROR: 0xFF6B6B,     # Soft Red
            NotificationLevel.CRITICAL: 0x8B0000   # Dark Red
        }
        
        # Log configuration for debugging
        if self.enabled:
            self.logger.info(
                "Discord notifier initialized via config_loader",
                webhook_configured=bool(self.webhook_url),
                events_enabled=self.events,
                language=self.default_language
            )
        else:
            self.logger.info(
                "Discord notifications disabled",
                enabled=self.enabled,
                webhook_url_provided=bool(self.webhook_url)
            )
    
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
    
    def _detect_language(self) -> str:
        """Get language from config_loader (consistent approach)"""
        return self.default_language
    
    async def _send_webhook(
        self, 
        description: str, 
        level: NotificationLevel = NotificationLevel.INFO,
        mention_on_error: bool = False
    ) -> bool:
        """Send webhook request to Discord"""
        if not self.session:
            self.logger.error("Discord session not initialized")
            return False
        
        try:
            # Build clean, community-friendly embed
            embed = {
                "description": description,
                "color": self.level_colors[level],
                "timestamp": datetime.utcnow().isoformat()
            }
            
            payload = {"embeds": [embed]}
            
            # Add role mention for critical notifications (using config value)
            if (mention_on_error and 
                self.mention_role and 
                level in [NotificationLevel.ERROR, NotificationLevel.CRITICAL]):
                payload["content"] = f"<@&{self.mention_role}>"
            
            # Send webhook request
            async with self.session.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                
                if response.status == 204:
                    log_server_event(
                        self.logger, "discord_send",
                        "Discord notification sent successfully",
                        level=level.value,
                        language=self.default_language
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
    
    async def _send_notification(
        self, 
        event_type: str, 
        message_path: str,
        level: NotificationLevel = NotificationLevel.INFO,
        language: Optional[str] = None,
        **message_kwargs
    ) -> bool:
        """
        Send localized notification with event filtering using config_loader values
        
        Args:
            event_type: Discord event type for filtering (from config.discord.events)
            message_path: Path to message in locale files
            level: Notification level
            language: Language override (uses config.language if None)
            **message_kwargs: Message formatting arguments
        """
        if not self.enabled:
            self.logger.debug("Discord notifications disabled in config")
            return False
        
        # Check if specific event type is enabled (using config.discord.events)
        if event_type not in self.events or not self.events[event_type]:
            self.logger.debug(
                "Event type disabled in configuration",
                event_type=event_type,
                config_source="config.discord.events"
            )
            return False
        
        # Get localized message (using config.language as default)
        lang = language or self._detect_language()
        description = self.message_loader.get_message(message_path, lang, **message_kwargs)
        
        # Send webhook
        return await self._send_webhook(
            description, 
            level, 
            mention_on_error=(level in [NotificationLevel.ERROR, NotificationLevel.CRITICAL])
        )
    
    # Clean convenience methods with config_loader integration
    async def notify_server_start(self, language: str = None) -> bool:
        """Send server start notification (controlled by config.discord.events.server_start)"""
        return await self._send_notification(
            "server_start",
            "server.start",
            NotificationLevel.INFO,
            language
        )
    
    async def notify_server_stop(self, reason: str = "", language: str = None) -> bool:
        """Send server stop notification (controlled by config.discord.events.server_stop)"""
        return await self._send_notification(
            "server_stop",
            "server.stop", 
            NotificationLevel.WARNING,
            language,
            reason=reason
        )
    
    async def notify_player_join(
        self, 
        player_name: str, 
        player_count: int, 
        language: str = None
    ) -> bool:
        """Send player join notification (controlled by config.discord.events.player_join)"""
        # Get additional context messages using config.language
        lang = language or self._detect_language()
        status_msg = self.message_loader.get_status_message(player_count, lang)
        greeting = self.message_loader.get_greeting(lang)
        
        return await self._send_notification(
            "player_join",
            "player.join",
            NotificationLevel.INFO,
            language,
            player=player_name,
            status=status_msg,
            greeting=greeting
        )
    
    async def notify_player_leave(
        self, 
        player_name: str, 
        player_count: int, 
        language: str = None
    ) -> bool:
        """Send player leave notification (controlled by config.discord.events.player_leave)"""
        return await self._send_notification(
            "player_leave",
            "player.leave",
            NotificationLevel.INFO,
            language,
            player=player_name,
            count=player_count
        )
    
    async def notify_backup_complete(self, language: str = None) -> bool:
        """Send backup completion notification (controlled by config.discord.events.backup_complete)"""
        return await self._send_notification(
            "backup_complete",
            "backup.complete",
            NotificationLevel.INFO,
            language
        )
    
    async def notify_error(self, error_message: str = "", language: str = None) -> bool:
        """Send error notification (controlled by config.discord.events.errors)"""
        return await self._send_notification(
            "errors",
            "error.general",
            NotificationLevel.ERROR,
            language,
            error=error_message
        )
    
    def get_event_status(self) -> Dict[str, bool]:
        """Get current event configuration status for debugging (using config values)"""
        return {
            "discord_enabled": self.enabled,
            "webhook_configured": bool(self.webhook_url),
            "mention_role_configured": bool(self.mention_role),
            "language": self.default_language,
            "events": self.events.copy()
        }


# Global instance
_discord_notifier: Optional[DiscordNotifier] = None


def get_discord_notifier(config: Optional[PalworldConfig] = None) -> DiscordNotifier:
    """Get global Discord notifier instance"""
    global _discord_notifier
    
    if _discord_notifier is None:
        from ..config_loader import get_config
        _discord_notifier = DiscordNotifier(config or get_config())
    
    return _discord_notifier


async def main():
    """Test multi-language notifications with config_loader values"""
    from ..config_loader import get_config
    
    config = get_config()
    
    async with DiscordNotifier(config) as notifier:
        print("🌍 Config-loader based Discord notifier test")
        
        # Show current configuration from config_loader
        status = notifier.get_event_status()
        print(f"Configuration from config_loader: {status}")
        
        if not notifier.enabled:
            print("❌ Discord not configured or disabled in config")
            print("Check config.discord.enabled and config.discord.webhook_url")
            return
        
        # Test different events (all controlled by config.discord.events)
        await notifier.notify_server_start(language=config.language)
        await asyncio.sleep(1)
        
        await notifier.notify_player_join("TestPlayer", 1, language="en")
        await asyncio.sleep(1)
        
        await notifier.notify_backup_complete(language="ja")
        
        print("✅ Config-loader integration test complete!")


if __name__ == "__main__":
    asyncio.run(main())
