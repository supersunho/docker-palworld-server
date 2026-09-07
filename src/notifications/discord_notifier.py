#!/usr/bin/env python3
"""
Discord notification system for Palworld server
Event-based notifications with webhook integration and multi-language support
"""

import aiohttp
from datetime import datetime, UTC
from typing import Dict, Optional
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


def _mask_webhook_url(url: str) -> str:
    """Return a redacted form of a Discord webhook URL.

    Discord webhook URLs look like ``https://discord.com/api/webhooks/<id>/<token>``.
    The trailing token is a secret — never log it. Returns the URL with only
    the webhook id (and a length hint) so operators can still identify which
    webhook failed without the credential leaking.
    """
    if not url:
        return ""
    parts = url.rstrip("/").split("/")
    if len(parts) < 2:
        # Not the expected shape — return a coarse redacted form anyway.
        return url.split("?")[0][:24] + "...(redacted)"
    token = parts[-1]
    webhook_id = parts[-2]
    return f"{('/'.join(parts[:-2]))}/{webhook_id}/***({len(token)} chars)"


class DiscordNotifier:
    """Discord webhook notification manager with multi-language support"""

    def __init__(self, config: PalworldConfig):
        """Initialize Discord notifier with configuration"""
        self.config = config
        self.logger = get_logger("palworld.discord")
        self.message_loader = get_message_loader()

        self.webhook_url = config.discord.webhook_url
        self.enabled = config.discord.enabled and bool(self.webhook_url)
        self.mention_role = config.discord.mention_role
        self.events = config.discord.events
        self.default_language = config.language

        self.session: Optional[aiohttp.ClientSession] = None

        self.level_colors = {
            NotificationLevel.INFO: 0x00FF7F,
            NotificationLevel.WARNING: 0xFFD700,
            NotificationLevel.ERROR: 0xFF6B6B,
            NotificationLevel.CRITICAL: 0x8B0000,
        }

        if self.enabled:
            self.logger.info(
                "Discord notifier initialized",
                webhook_configured=bool(self.webhook_url),
                events_enabled=self.events,
                language=self.default_language,
            )
        else:
            self.logger.info(
                "Discord notifications disabled",
                enabled=self.enabled,
                webhook_url_provided=bool(self.webhook_url),
            )

    async def __aenter__(self):
        """Initialize HTTP session"""
        if self.enabled:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close HTTP session"""
        if self.session:
            await self.session.close()

    def _detect_language(self) -> str:
        """Get language from configuration"""
        return self.default_language

    async def _send_webhook(
        self,
        description: str,
        level: NotificationLevel = NotificationLevel.INFO,
        mention_on_error: bool = False,
    ) -> bool:
        """Send webhook request to Discord"""
        if not self.session:
            self.logger.error("Discord session not initialized")
            return False

        try:
            embed = {
                "description": description,
                "color": self.level_colors[level],
                "timestamp": datetime.now(UTC).isoformat(),
            }

            payload = {"embeds": [embed]}

            if (
                mention_on_error
                and self.mention_role
                and level in [NotificationLevel.ERROR, NotificationLevel.CRITICAL]
            ):
                payload["content"] = f"<@&{self.mention_role}>"

            async with self.session.post(
                self.webhook_url, json=payload, headers={"Content-Type": "application/json"}
            ) as response:

                if response.status == 204:
                    log_server_event(
                        self.logger,
                        "discord_send",
                        "Discord notification sent successfully",
                        level=level.value,
                        language=self.default_language,
                    )
                    return True
                else:
                    error_text = await response.text()
                    # Defense-in-depth: strip any webhook URL that Discord may
                    # have echoed back inside its error body.
                    sanitized = error_text.replace(self.webhook_url, _mask_webhook_url(self.webhook_url))
                    self.logger.error(
                        "Discord webhook failed",
                        status_code=response.status,
                        webhook=_mask_webhook_url(self.webhook_url),
                        error=sanitized,
                    )
                    return False

        except Exception as e:
            # The exception message can contain the request URL on some aiohttp
            # failure modes. Redact defensively before logging.
            sanitized = str(e).replace(self.webhook_url, _mask_webhook_url(self.webhook_url))
            self.logger.error(
                "Discord notification error",
                webhook=_mask_webhook_url(self.webhook_url),
                error=sanitized,
            )
            return False

    async def _send_notification(
        self,
        event_type: str,
        message_path: str,
        level: NotificationLevel = NotificationLevel.INFO,
        language: Optional[str] = None,
        **message_kwargs,
    ) -> bool:
        """Send localized notification with event filtering"""
        if not self.enabled:
            return False

        if event_type not in self.events or not self.events[event_type]:
            self.logger.debug("Event type disabled in configuration", event_type=event_type)
            return False

        lang = language or self._detect_language()
        description = self.message_loader.get_message(message_path, lang, **message_kwargs)

        return await self._send_webhook(
            description,
            level,
            mention_on_error=(level in [NotificationLevel.ERROR, NotificationLevel.CRITICAL]),
        )

    async def notify_server_start(self, language: Optional[str] = None) -> bool:
        """Send server start notification"""
        return await self._send_notification(
            "server_start", "server.start", NotificationLevel.INFO, language
        )

    async def notify_server_stop(self, reason: str = "", language: Optional[str] = None) -> bool:
        """Send server stop notification"""
        return await self._send_notification(
            "server_stop", "server.stop", NotificationLevel.WARNING, language, reason=reason
        )

    async def notify_player_join(
        self, player_name: str, player_count: int, language: Optional[str] = None
    ) -> bool:
        """Send player join notification"""
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
            greeting=greeting,
        )

    async def notify_player_leave(
        self, player_name: str, player_count: int, language: Optional[str] = None
    ) -> bool:
        """Send player leave notification"""
        return await self._send_notification(
            "player_leave",
            "player.leave",
            NotificationLevel.INFO,
            language,
            player=player_name,
            count=player_count,
        )

    async def notify_backup_complete(self, language: Optional[str] = None) -> bool:
        """Send backup completion notification"""
        return await self._send_notification(
            "backup_complete", "backup.complete", NotificationLevel.INFO, language
        )

    async def notify_error(self, error_message: str = "", language: Optional[str] = None) -> bool:
        """Send error notification"""
        return await self._send_notification(
            "errors", "error.general", NotificationLevel.ERROR, language, error=error_message
        )

    async def notify_update_available(
        self, current_version: str = "", new_version: str = "", language: Optional[str] = None
    ) -> bool:
        """Send update available notification"""
        return await self._send_notification(
            "update",
            "update.available",
            NotificationLevel.INFO,
            language,
            current=current_version,
            new=new_version,
        )

    def get_event_status(self) -> Dict[str, bool]:
        """Get current event configuration status"""
        return {
            "discord_enabled": self.enabled,
            "webhook_configured": bool(self.webhook_url),
            "mention_role_configured": bool(self.mention_role),
            "language": self.default_language,
            "events": self.events.copy(),
        }


_discord_notifier: Optional[DiscordNotifier] = None


def get_discord_notifier(config: Optional[PalworldConfig] = None) -> DiscordNotifier:
    """Get global Discord notifier instance"""
    global _discord_notifier

    if _discord_notifier is None:
        from ..config_loader import get_config

        _discord_notifier = DiscordNotifier(config or get_config())

    return _discord_notifier
