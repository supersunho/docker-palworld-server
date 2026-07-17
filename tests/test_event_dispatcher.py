"""Tests for the event dispatcher."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.monitoring.event_dispatcher import EventDispatcher
from src.monitoring.player_monitor import PlayerEvent, PlayerEventType
from src.monitoring.server_monitor import ServerEvent, ServerEventType

pytestmark = pytest.mark.unit


class TestEventDispatcher:
    """FS-13.2.5: Event dispatcher behavior."""

    @pytest.fixture
    def dispatcher(self, palworld_config):
        d = EventDispatcher(palworld_config)
        d.discord_notifier = MagicMock()
        d.discord_notifier.__aenter__ = AsyncMock(return_value=d.discord_notifier)
        d.discord_notifier.__aexit__ = AsyncMock(return_value=None)
        d.discord_notifier.notify_player_join = AsyncMock()
        d.discord_notifier.notify_player_leave = AsyncMock()
        d.discord_notifier.notify_server_start = AsyncMock()
        d.discord_notifier.notify_server_stop = AsyncMock()
        d.discord_notifier.notify_error = AsyncMock()
        d.discord_notifier.notify_backup_complete = AsyncMock()
        d._discord_enabled = True
        return d

    @pytest.mark.asyncio
    async def test_player_join_discord(self, dispatcher):
        """FS-13.2.5: Player join dispatches to Discord."""
        event = PlayerEvent(
            event_type=PlayerEventType.JOINED,
            player_name="Player1",
            player_count=5,
            timestamp=100.0,
        )
        await dispatcher.handle_player_event(event)
        dispatcher.discord_notifier.notify_player_join.assert_awaited_with(
            "Player1", 5, language=dispatcher._language
        )

    @pytest.mark.asyncio
    async def test_player_leave_discord(self, dispatcher):
        """FS-13.2.5: Player leave dispatches to Discord."""
        event = PlayerEvent(
            event_type=PlayerEventType.LEFT, player_name="Player1", player_count=4, timestamp=100.0
        )
        await dispatcher.handle_player_event(event)
        dispatcher.discord_notifier.notify_player_leave.assert_awaited_with(
            "Player1", 4, language=dispatcher._language
        )

    @pytest.mark.asyncio
    async def test_server_start_discord(self, dispatcher):
        """FS-13.2.5: Server start dispatched."""
        event = ServerEvent(
            event_type=ServerEventType.STATUS_CHANGED,
            message="Server started successfully",
            details={},
            timestamp=100.0,
        )
        await dispatcher.handle_server_event(event)
        dispatcher.discord_notifier.notify_server_start.assert_awaited_with(
            language=dispatcher._language
        )

    @pytest.mark.asyncio
    async def test_server_stop_discord(self, dispatcher):
        """FS-13.2.5: Server stop dispatched."""
        event = ServerEvent(
            event_type=ServerEventType.STATUS_CHANGED,
            message="Server stopped",
            details={},
            timestamp=100.0,
        )
        await dispatcher.handle_server_event(event)
        dispatcher.discord_notifier.notify_server_stop.assert_awaited()
        dispatcher.discord_notifier.notify_error.assert_not_called()

    @pytest.mark.asyncio
    async def test_health_warning_discord(self, dispatcher):
        """FS-13.2.5: Health warning dispatched."""
        event = ServerEvent(
            event_type=ServerEventType.HEALTH_WARNING,
            message="High memory",
            details={"issues": ["High memory"]},
            timestamp=100.0,
        )
        await dispatcher.handle_server_event(event)
        dispatcher.discord_notifier.notify_error.assert_awaited()

    @pytest.mark.asyncio
    async def test_backup_complete_discord(self, dispatcher):
        """FS-13.2.5: Backup completion dispatched."""
        await dispatcher.handle_backup_completion({"file": "backup.tar.gz"})
        dispatcher.discord_notifier.notify_backup_complete.assert_awaited_with(
            language=dispatcher._language
        )

    @pytest.mark.asyncio
    async def test_discord_disabled_skips(self, dispatcher):
        """FS-13.2.5: No dispatch when Discord disabled."""
        dispatcher._discord_enabled = False
        event = PlayerEvent(
            event_type=PlayerEventType.JOINED,
            player_name="Player1",
            player_count=1,
            timestamp=100.0,
        )
        await dispatcher.handle_player_event(event)
        dispatcher.discord_notifier.notify_player_join.assert_not_called()

    @pytest.mark.asyncio
    async def test_server_restart_discord(self, dispatcher):
        """FS-13.2.5: Unexpected restart dispatched as error."""
        from src.monitoring.server_monitor import ServerEventType

        event = ServerEvent(
            event_type=ServerEventType.STATUS_CHANGED,
            message="Server restarted unexpectedly",
            details={"reason": "crash"},
            timestamp=100.0,
        )
        await dispatcher.handle_server_event(event)
        dispatcher.discord_notifier.notify_error.assert_awaited()

    @pytest.mark.asyncio
    async def test_performance_issue_discord(self, dispatcher):
        """FS-13.2.5: Performance issue dispatched."""
        from src.monitoring.server_monitor import ServerEventType

        event = ServerEvent(
            event_type=ServerEventType.PERFORMANCE_ISSUE,
            message="High CPU usage",
            details={},
            timestamp=100.0,
        )
        await dispatcher.handle_server_event(event)
        dispatcher.discord_notifier.notify_error.assert_awaited()

    @pytest.mark.asyncio
    async def test_error_event_discord(self, dispatcher):
        """FS-13.2.5: Error event dispatched."""
        await dispatcher.handle_error_event("Test error", {"code": 500})
        dispatcher.discord_notifier.notify_error.assert_awaited_with(
            "Test error", language=dispatcher._language
        )

    @pytest.mark.asyncio
    async def test_error_event_discord_disabled(self, dispatcher):
        """FS-13.2.5: Error event skipped when Discord disabled."""
        dispatcher._discord_enabled = False
        await dispatcher.handle_error_event("Test error")
        dispatcher.discord_notifier.notify_error.assert_not_called()

    @pytest.mark.asyncio
    async def test_backup_discord_disabled(self, dispatcher):
        """FS-13.2.5: Backup event skipped when Discord disabled."""
        dispatcher._discord_enabled = False
        await dispatcher.handle_backup_completion({"file": "backup.tar.gz"})
        dispatcher.discord_notifier.notify_backup_complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_player_event_exception_logged(self, dispatcher):
        """FS-13.2.5: Exception in player event is logged, not propagated."""
        dispatcher.discord_notifier.__aenter__ = AsyncMock(
            side_effect=RuntimeError("Discord failure")
        )
        event = PlayerEvent(
            event_type=PlayerEventType.JOINED,
            player_name="Player1",
            player_count=1,
            timestamp=100.0,
        )
        # Should not raise
        await dispatcher.handle_player_event(event)

    @pytest.mark.asyncio
    async def test_server_event_exception_logged(self, dispatcher):
        """FS-13.2.5: Exception in server event is logged, not propagated."""
        dispatcher.discord_notifier.__aenter__ = AsyncMock(
            side_effect=RuntimeError("Discord failure")
        )
        event = ServerEvent(
            event_type=ServerEventType.STATUS_CHANGED,
            message="Server started",
            details={},
            timestamp=100.0,
        )
        await dispatcher.handle_server_event(event)

    @pytest.mark.asyncio
    async def test_server_event_not_restart_different_message(self, dispatcher):
        """FS-13.2.5: Non-start/stop/restart message is not dispatched."""
        event = ServerEvent(
            event_type=ServerEventType.STATUS_CHANGED,
            message="Server status update - running",
            details={},
            timestamp=100.0,
        )
        await dispatcher.handle_server_event(event)
        # No notification methods should be called
        dispatcher.discord_notifier.notify_server_start.assert_not_called()
        dispatcher.discord_notifier.notify_server_stop.assert_not_called()
        dispatcher.discord_notifier.notify_error.assert_not_called()
