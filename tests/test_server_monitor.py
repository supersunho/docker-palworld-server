"""Tests for the server monitor."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from src.monitoring.server_monitor import ServerMonitor, ServerEventType, ServerEvent, ServerStatus

pytestmark = pytest.mark.unit


class TestServerMonitor:
    """FS-16.x: Server monitor behavior."""

    @pytest.fixture
    def monitor(self, palworld_config, mock_process_manager, mock_api_facade):
        return ServerMonitor(palworld_config, mock_process_manager, mock_api_facade)

    def test_callback_management(self, monitor):
        """FS-16.4: Callback pattern matches PlayerMonitor."""
        cb = AsyncMock()
        monitor.add_event_callback(ServerEventType.STATUS_CHANGED, cb)
        assert cb in monitor._event_callbacks[ServerEventType.STATUS_CHANGED]

    def test_clear_user_callbacks(self, monitor):
        """FS-16.4: Clear user callbacks preserves system."""
        sys_cb = AsyncMock()
        user_cb = AsyncMock()
        monitor.add_event_callback(ServerEventType.STATUS_CHANGED, sys_cb, is_system_callback=True)
        monitor.add_event_callback(ServerEventType.STATUS_CHANGED, user_cb)
        monitor.clear_user_callbacks()
        assert sys_cb in monitor._event_callbacks[ServerEventType.STATUS_CHANGED]
        assert user_cb not in monitor._event_callbacks[ServerEventType.STATUS_CHANGED]

    def test_clear_all_callbacks(self, monitor):
        """FS-16.4: Clear all event types."""
        monitor.add_event_callback(ServerEventType.STATUS_CHANGED, AsyncMock())
        monitor.add_event_callback(ServerEventType.HEALTH_WARNING, AsyncMock())
        monitor.clear_event_callbacks()
        assert len(monitor._event_callbacks[ServerEventType.STATUS_CHANGED]) == 0
        assert len(monitor._event_callbacks[ServerEventType.HEALTH_WARNING]) == 0

    def test_get_last_status_none(self, monitor):
        """FS-16.1: Returns None before any check."""
        assert monitor.get_last_status() is None

    def test_server_status_dataclass(self):
        """FS-16: ServerStatus fields."""
        import time

        status = ServerStatus(
            is_running=True, pid=12345, uptime=3600.0, player_count=3, last_check=time.time()
        )
        assert status.is_running is True
        assert status.pid == 12345
        assert status.player_count == 3

    def test_server_event_dataclass(self):
        import time

        event = ServerEvent(
            event_type=ServerEventType.STATUS_CHANGED,
            message="Server started",
            details={"pid": 12345},
            timestamp=time.time(),
        )
        assert event.event_type == ServerEventType.STATUS_CHANGED
        assert event.message == "Server started"

    def test_is_monitoring_active(self, monitor):
        assert monitor.is_monitoring_active() is False
        monitor._monitoring_active = True
        assert monitor.is_monitoring_active() is True
