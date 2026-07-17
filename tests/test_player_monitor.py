"""Tests for the player monitor."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from src.monitoring.player_monitor import (
    PlayerMonitor, PlayerEventType, PlayerEvent
)

pytestmark = pytest.mark.unit


class TestPlayerMonitor:
    """FS-15.x: Player monitor behavior."""

    @pytest.fixture
    def monitor(self, palworld_config, mock_api_facade):
        m = PlayerMonitor(palworld_config, mock_api_facade)
        m._first_check = False
        m._previous_players = {"Player1", "Player2"}
        return m

    def test_add_event_callback(self, monitor):
        """FS-15.3: Callbacks can be registered."""
        cb = AsyncMock()
        monitor.add_event_callback(PlayerEventType.JOINED, cb)
        assert cb in monitor._event_callbacks[PlayerEventType.JOINED]

    def test_add_event_callback_dedup(self, monitor):
        """FS-15.3: Duplicate callbacks are not added."""
        cb = AsyncMock()
        monitor.add_event_callback(PlayerEventType.JOINED, cb)
        monitor.add_event_callback(PlayerEventType.JOINED, cb)
        assert len(monitor._event_callbacks[PlayerEventType.JOINED]) == 1

    def test_remove_event_callback(self, monitor):
        """FS-15.4: Callbacks can be removed."""
        cb = AsyncMock()
        monitor.add_event_callback(PlayerEventType.JOINED, cb)
        assert monitor.remove_event_callback(PlayerEventType.JOINED, cb) is True

    def test_remove_nonexistent_callback(self, monitor):
        """FS-15.4: Removing non-existent returns False."""
        cb = AsyncMock()
        assert monitor.remove_event_callback(PlayerEventType.JOINED, cb) is False

    def test_clear_all_callbacks(self, monitor):
        """FS-15.4: Clear all callbacks."""
        cb1, cb2 = AsyncMock(), AsyncMock()
        monitor.add_event_callback(PlayerEventType.JOINED, cb1)
        monitor.add_event_callback(PlayerEventType.LEFT, cb2)
        monitor.clear_event_callbacks()
        assert len(monitor._event_callbacks[PlayerEventType.JOINED]) == 0
        assert len(monitor._event_callbacks[PlayerEventType.LEFT]) == 0

    def test_clear_specific_callback(self, monitor):
        """FS-15.4: Clear specific event type."""
        monitor.add_event_callback(PlayerEventType.JOINED, AsyncMock())
        monitor.clear_event_callbacks(PlayerEventType.JOINED)
        assert len(monitor._event_callbacks[PlayerEventType.JOINED]) == 0

    def test_clear_user_callbacks(self, monitor):
        """FS-15.4: Only user callbacks cleared."""
        sys_cb = AsyncMock()
        user_cb = AsyncMock()
        monitor.add_event_callback(PlayerEventType.JOINED, sys_cb, is_system_callback=True)
        monitor.add_event_callback(PlayerEventType.JOINED, user_cb)
        monitor.clear_user_callbacks()
        assert sys_cb in monitor._event_callbacks[PlayerEventType.JOINED]
        assert user_cb not in monitor._event_callbacks[PlayerEventType.JOINED]

    def test_get_current_players(self, monitor):
        """FS-15: Player tracking."""
        monitor._previous_players = {"P1", "P2"}
        assert monitor.get_current_players() == {"P1", "P2"}
        assert monitor.get_current_player_count() == 2

    @pytest.mark.asyncio
    async def test_detect_player_join(self, monitor):
        """FS-15.2: Detects player join."""
        result_handler = AsyncMock()
        monitor.add_event_callback(PlayerEventType.JOINED, result_handler)
        current = {"Player1", "Player2", "Player3"}
        await monitor._process_player_changes(current)
        result_handler.assert_called_once()
        event = result_handler.call_args[0][0]
        assert event.event_type == PlayerEventType.JOINED
        assert event.player_name == "Player3"

    @pytest.mark.asyncio
    async def test_detect_player_leave(self, monitor):
        """FS-15.2: Detects player leave."""
        result_handler = AsyncMock()
        monitor.add_event_callback(PlayerEventType.LEFT, result_handler)
        current = {"Player1"}
        await monitor._process_player_changes(current)
        result_handler.assert_called_once()
        event = result_handler.call_args[0][0]
        assert event.event_type == PlayerEventType.LEFT
        assert event.player_name == "Player2"

    @pytest.mark.asyncio
    async def test_no_change_no_events(self, monitor):
        """FS-15.2: No events when players unchanged."""
        cb = AsyncMock()
        monitor.add_event_callback(PlayerEventType.JOINED, cb)
        monitor.add_event_callback(PlayerEventType.LEFT, cb)
        await monitor._process_player_changes({"Player1", "Player2"})
        cb.assert_not_called()

    def test_player_event_dataclass(self):
        """FS-15: PlayerEvent fields."""
        import time


        event = PlayerEvent(
            event_type=PlayerEventType.JOINED,
            player_name="Player1",
            player_count=5,
            timestamp=time.time()
        )
        assert event.event_type == PlayerEventType.JOINED
        assert event.player_name == "Player1"
        assert event.player_count == 5

    def test_get_debug_stats(self, monitor):
        """FS-15.7: Debug stats available."""
        stats = monitor.get_debug_stats()
        assert "monitoring_active" in stats
        assert "current_player_count" in stats
        assert "registered_callbacks" in stats
        assert "retry_configuration" in stats

    @pytest.mark.asyncio
    async def test_stop_monitoring_clears_state(self, monitor):
        """FS-15.6: Stop clears callbacks and player set."""
        monitor.add_event_callback(PlayerEventType.JOINED, AsyncMock())
        monitor._monitoring_active = True
        await monitor.stop_monitoring()
        assert monitor._monitoring_active is False
        assert len(monitor._event_callbacks[PlayerEventType.JOINED]) == 0
        assert len(monitor._previous_players) == 0
