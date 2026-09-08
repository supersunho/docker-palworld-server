"""Tests for the Discord notifier."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.notifications.discord_notifier import DiscordNotifier, NotificationLevel, _mask_webhook_url

pytestmark = pytest.mark.unit


class TestDiscordNotifier:
    """FS-19.x: Discord notifier behavior."""

    @pytest.fixture
    def notifier(self, palworld_config):
        n = DiscordNotifier(palworld_config)
        n.session = MagicMock()
        n.enabled = True
        n.webhook_url = "https://discord.com/api/webhooks/test"
        return n

    def test_init_disabled_without_url(self, palworld_config):
        """FS-19.1: Disabled when no webhook URL."""
        palworld_config.discord.webhook_url = ""
        n = DiscordNotifier(palworld_config)
        assert n.enabled is False

    def test_notification_level_colors(self, palworld_config):
        """FS-19.1: Level colors defined."""
        n = DiscordNotifier(palworld_config)
        colors = n.level_colors
        assert colors[NotificationLevel.INFO] == 0x00FF7F
        assert colors[NotificationLevel.WARNING] == 0xFFD700
        assert colors[NotificationLevel.ERROR] == 0xFF6B6B
        assert colors[NotificationLevel.CRITICAL] == 0x8B0000

    def _make_async_context_manager(self, mock_response):
        """Create an async context manager mock from a response mock."""
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=None)
        return cm

    @pytest.mark.asyncio
    async def test_send_webhook_success(self, notifier):
        """FS-19.1: Successful webhook send."""
        mock_response = MagicMock()
        mock_response.status = 204

        cm = self._make_async_context_manager(mock_response)
        notifier.session.post = MagicMock(return_value=cm)

        result = await notifier._send_webhook("Test notification", NotificationLevel.INFO)
        assert result is True

    @pytest.mark.asyncio
    async def test_send_webhook_failure(self, notifier):
        """FS-19.1: Failed webhook returns False."""
        mock_response = MagicMock()
        mock_response.status = 400
        mock_response.text = AsyncMock(return_value="Bad Request")

        cm = self._make_async_context_manager(mock_response)
        notifier.session.post = MagicMock(return_value=cm)

        result = await notifier._send_webhook("Test", NotificationLevel.INFO)
        assert result is False

    def test_init_enabled(self, palworld_config):
        """FS-19.1: Enabled when webhook URL provided."""
        palworld_config.discord.webhook_url = "https://discord.com/api/webhooks/test"
        palworld_config.discord.enabled = True
        n = DiscordNotifier(palworld_config)
        assert n.enabled is True

    def test_mention_role_config(self, palworld_config):
        palworld_config.discord.mention_role = "123456"
        n = DiscordNotifier(palworld_config)
        assert n.mention_role == "123456"

    @pytest.mark.asyncio
    async def test_send_notification_disabled(self, notifier):
        """FS-19.1: _send_notification returns False when disabled."""
        notifier.enabled = False
        result = await notifier._send_notification("server_start", "server.start")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_notification_event_disabled(self, notifier):
        """FS-19.1: _send_notification returns False when event type disabled."""
        notifier.events = {"server_start": False}
        result = await notifier._send_notification("server_start", "server.start")
        assert result is False

    def test_get_event_status(self, notifier):
        """FS-19.1: get_event_status returns expected structure."""
        status = notifier.get_event_status()
        assert "discord_enabled" in status
        assert "webhook_configured" in status
        assert "events" in status
        assert status["discord_enabled"] is True

    @pytest.mark.asyncio
    async def test_notify_server_start_disabled_event(self, notifier):
        """FS-19.1: notify_server_start returns False when event disabled."""
        notifier.events = {"server_start": False}
        result = await notifier.notify_server_start()
        assert result is False

    @pytest.mark.asyncio
    async def test_notify_server_stop(self, notifier):
        """FS-19.1: notify_server_stop dispatches."""
        mock_response = MagicMock()
        mock_response.status = 204
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=None)
        notifier.session.post = MagicMock(return_value=cm)
        result = await notifier.notify_server_stop(reason="Maintenance")
        assert result is True

    @pytest.mark.asyncio
    async def test_notify_player_join(self, notifier):
        """FS-19.1: notify_player_join dispatches."""
        mock_response = MagicMock()
        mock_response.status = 204
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=None)
        notifier.session.post = MagicMock(return_value=cm)
        result = await notifier.notify_player_join("Player1", 5)
        assert result is True

    @pytest.mark.asyncio
    async def test_notify_player_leave(self, notifier):
        """FS-19.1: notify_player_leave dispatches."""
        mock_response = MagicMock()
        mock_response.status = 204
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=None)
        notifier.session.post = MagicMock(return_value=cm)
        result = await notifier.notify_player_leave("Player1", 4)
        assert result is True

    @pytest.mark.asyncio
    async def test_notify_backup_complete(self, notifier):
        """FS-19.1: notify_backup_complete dispatches."""
        mock_response = MagicMock()
        mock_response.status = 204
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=None)
        notifier.session.post = MagicMock(return_value=cm)
        result = await notifier.notify_backup_complete()
        assert result is True

    @pytest.mark.asyncio
    async def test_notify_error(self, notifier):
        """FS-19.1: notify_error dispatches."""
        mock_response = MagicMock()
        mock_response.status = 204
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=None)
        notifier.session.post = MagicMock(return_value=cm)
        result = await notifier.notify_error("Server error")
        assert result is True

    @pytest.mark.asyncio
    async def test_webhook_no_session(self, notifier):
        """FS-19.1: _send_webhook returns False when session is None."""
        notifier.session = None
        result = await notifier._send_webhook("Test", NotificationLevel.INFO)
        assert result is False

    @pytest.mark.asyncio
    async def test_webhook_exception(self, notifier):
        """FS-19.1: _send_webhook exception is caught."""
        notifier.session.post = MagicMock(side_effect=RuntimeError("Network error"))
        result = await notifier._send_webhook("Test", NotificationLevel.INFO)
        assert result is False

    @pytest.mark.asyncio
    async def test_webhook_with_mention_role_error(self, notifier):
        """FS-19.1: Mention role included for error level."""
        notifier.mention_role = "123456"
        mock_response = MagicMock()
        mock_response.status = 204
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=None)
        notifier.session.post = MagicMock(return_value=cm)
        result = await notifier._send_webhook("Critical error", NotificationLevel.CRITICAL)
        assert result is True


class TestWebhookRedaction:
    """FS-19.x: Webhook URLs must never appear in logs or error messages."""

    @pytest.fixture
    def notifier(self, palworld_config):
        n = DiscordNotifier(palworld_config)
        n.session = MagicMock()
        n.enabled = True
        n.webhook_url = "https://discord.com/api/webhooks/test"
        return n

    def test_mask_webhook_url_redacts_token(self):
        """Standard Discord webhook shape is redacted; token is not exposed."""
        url = "https://discord.com/api/webhooks/1234567890/abcdefSECRET_TOKEN_xyz"
        masked = _mask_webhook_url(url)
        assert "SECRET_TOKEN" not in masked
        assert "abcdef" not in masked
        assert "1234567890" in masked  # webhook id retained for debug context
        assert "***" in masked

    def test_mask_webhook_url_handles_unexpected_shapes(self):
        """Unrecognized URLs still get a redacted form."""
        masked = _mask_webhook_url("https://example.com/short")
        assert "secret" not in masked.lower()
        # Should not raise
        masked_empty = _mask_webhook_url("")
        assert masked_empty == ""

    @pytest.mark.asyncio
    async def test_webhook_failure_redacts_url_in_error_log(self, notifier):
        """When Discord echoes back the webhook URL in its error body, the
        token must not appear in any value passed to logger.error."""
        secret = "https://discord.com/api/webhooks/9999/SECRET_TOKEN_VALUE"
        notifier.webhook_url = secret

        # Simulate Discord's response containing the URL inside the error.
        mock_response = MagicMock()
        mock_response.status = 400
        mock_response.text = AsyncMock(
            return_value=f"Webhook {secret} returned 400: invalid"
        )

        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=None)
        notifier.session.post = MagicMock(return_value=cm)

        error_logger = MagicMock()
        notifier.logger.error = error_logger
        result = await notifier._send_webhook("desc", NotificationLevel.ERROR)

        assert result is False
        error_logger.assert_called_once()
        call_kwargs = error_logger.call_args.kwargs
        # webhook + error fields must be redacted
        for key in ("webhook", "error"):
            assert key in call_kwargs, f"missing field {key}"
            assert "SECRET_TOKEN_VALUE" not in str(call_kwargs[key]), (
                f"webhook token leaked via {key}: {call_kwargs[key]}"
            )
            assert "***" in str(call_kwargs[key])

    @pytest.mark.asyncio
    async def test_webhook_exception_redacts_url(self, notifier):
        """If an exception carries the URL inside its message, the redacted
        webhook id replaces the token before logging."""
        secret = "https://discord.com/api/webhooks/7777/ANOTHER_SECRET_TOKEN"
        notifier.webhook_url = secret
        notifier.session.post = MagicMock(
            side_effect=RuntimeError(f"POST to {secret} failed: timeout")
        )

        error_logger = MagicMock()
        notifier.logger.error = error_logger
        result = await notifier._send_webhook("desc")

        assert result is False
        error_logger.assert_called_once()
        call_kwargs = error_logger.call_args.kwargs
        assert "ANOTHER_SECRET_TOKEN" not in str(call_kwargs.get("error", ""))
        assert "7777" in str(call_kwargs.get("webhook", ""))  # webhook id retained
        assert "***" in str(call_kwargs.get("webhook", ""))
