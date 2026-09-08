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


# ---------------------------------------------------------------------------
# Line 91: add_event_callback duplicate callback path
# ---------------------------------------------------------------------------


class TestAddEventCallback:
    """Covers add_event_callback else-branch (duplicate) and system tracking."""

    @pytest.fixture
    def monitor(self, palworld_config, mock_process_manager, mock_api_facade):
        return ServerMonitor(palworld_config, mock_process_manager, mock_api_facade)

    def test_duplicate_callback_not_added_twice(self, monitor):
        """Line 91: adding the same callback twice keeps one copy."""
        cb = AsyncMock()
        monitor.add_event_callback(ServerEventType.STATUS_CHANGED, cb)
        monitor.add_event_callback(ServerEventType.STATUS_CHANGED, cb)
        assert monitor._event_callbacks[ServerEventType.STATUS_CHANGED].count(cb) == 1

    def test_system_callback_tracked(self, monitor):
        """is_system_callback=True records in _system_callbacks."""
        cb = AsyncMock()
        monitor.add_event_callback(ServerEventType.STATUS_CHANGED, cb, is_system_callback=True)
        assert cb in monitor._system_callbacks[ServerEventType.STATUS_CHANGED]


# ---------------------------------------------------------------------------
# Lines 97-107: remove_event_callback
# ---------------------------------------------------------------------------


class TestRemoveEventCallback:
    """Covers all branches of remove_event_callback."""

    @pytest.fixture
    def monitor(self, palworld_config, mock_process_manager, mock_api_facade):
        return ServerMonitor(palworld_config, mock_process_manager, mock_api_facade)

    def test_remove_user_callback(self, monitor):
        """Lines 97-103: successful removal of user callback."""
        cb = AsyncMock()
        monitor.add_event_callback(ServerEventType.STATUS_CHANGED, cb)
        assert monitor.remove_event_callback(ServerEventType.STATUS_CHANGED, cb) is True
        assert cb not in monitor._event_callbacks[ServerEventType.STATUS_CHANGED]

    def test_remove_system_callback_clears_tracking(self, monitor):
        """Lines 100-101: system callback removed from _system_callbacks too."""
        cb = AsyncMock()
        monitor.add_event_callback(ServerEventType.STATUS_CHANGED, cb, is_system_callback=True)
        assert monitor.remove_event_callback(ServerEventType.STATUS_CHANGED, cb) is True
        assert cb not in monitor._system_callbacks[ServerEventType.STATUS_CHANGED]

    def test_remove_nonexistent_callback(self, monitor):
        """Lines 104-106: removing callback not in list returns False."""
        cb = AsyncMock()
        assert monitor.remove_event_callback(ServerEventType.STATUS_CHANGED, cb) is False


# ---------------------------------------------------------------------------
# Lines 119-121: clear_event_callbacks specific-type branch
# ---------------------------------------------------------------------------


class TestClearEventCallbacks:
    """Covers the else-branch (specific event type) of clear_event_callbacks."""

    @pytest.fixture
    def monitor(self, palworld_config, mock_process_manager, mock_api_facade):
        return ServerMonitor(palworld_config, mock_process_manager, mock_api_facade)

    def test_clear_specific_event_type(self, monitor):
        """Lines 119-121: clearing one type leaves others intact."""
        cb_sc = AsyncMock()
        cb_hw = AsyncMock()
        monitor.add_event_callback(ServerEventType.STATUS_CHANGED, cb_sc)
        monitor.add_event_callback(ServerEventType.HEALTH_WARNING, cb_hw)
        monitor.clear_event_callbacks(ServerEventType.STATUS_CHANGED)
        assert len(monitor._event_callbacks[ServerEventType.STATUS_CHANGED]) == 0
        assert cb_hw in monitor._event_callbacks[ServerEventType.HEALTH_WARNING]


# ---------------------------------------------------------------------------
# Line 133: clear_user_callbacks specific-type branch
# ---------------------------------------------------------------------------


class TestClearUserCallbacks:
    """Covers the else-branch (specific event type) of clear_user_callbacks."""

    @pytest.fixture
    def monitor(self, palworld_config, mock_process_manager, mock_api_facade):
        return ServerMonitor(palworld_config, mock_process_manager, mock_api_facade)

    def test_clear_user_callbacks_specific_type(self, monitor):
        """Line 133: user callbacks cleared for one type, system preserved."""
        sys_cb = AsyncMock()
        user_cb = AsyncMock()
        monitor.add_event_callback(ServerEventType.STATUS_CHANGED, sys_cb, is_system_callback=True)
        monitor.add_event_callback(ServerEventType.STATUS_CHANGED, user_cb)
        monitor.clear_user_callbacks(ServerEventType.STATUS_CHANGED)
        assert sys_cb in monitor._event_callbacks[ServerEventType.STATUS_CHANGED]
        assert user_cb not in monitor._event_callbacks[ServerEventType.STATUS_CHANGED]


# ---------------------------------------------------------------------------
# Lines 142-156: start_monitoring
# ---------------------------------------------------------------------------


class TestStartMonitoring:
    """Covers start_monitoring: early-return, normal flow, and exception."""

    @pytest.fixture
    def monitor(self, palworld_config, mock_process_manager, mock_api_facade):
        return ServerMonitor(palworld_config, mock_process_manager, mock_api_facade)

    @pytest.mark.asyncio
    async def test_already_active_warns(self, monitor):
        """Lines 142-144: early return when already monitoring."""
        monitor._monitoring_active = True
        await monitor.start_monitoring()
        assert monitor._monitoring_active is True

    @pytest.mark.asyncio
    async def test_normal_flow(self, monitor):
        """Lines 146-156: sets active, runs loop, finally clears active."""
        monitor._monitoring_loop = AsyncMock()
        await monitor.start_monitoring()
        assert monitor._monitoring_active is False
        monitor._monitoring_loop.assert_called_once()

    @pytest.mark.asyncio
    async def test_exception_in_loop(self, monitor):
        """Lines 152-153: exception caught, finally still runs."""
        monitor._monitoring_loop = AsyncMock(side_effect=RuntimeError("boom"))
        await monitor.start_monitoring()
        assert monitor._monitoring_active is False


# ---------------------------------------------------------------------------
# Lines 160-167: stop_monitoring
# ---------------------------------------------------------------------------


class TestStopMonitoring:
    """Covers stop_monitoring: early-return and normal stop."""

    @pytest.fixture
    def monitor(self, palworld_config, mock_process_manager, mock_api_facade):
        return ServerMonitor(palworld_config, mock_process_manager, mock_api_facade)

    @pytest.mark.asyncio
    async def test_not_active_returns(self, monitor):
        """Lines 160-161: no-op when not active."""
        await monitor.stop_monitoring()

    @pytest.mark.asyncio
    async def test_sets_shutdown_and_clears_callbacks(self, monitor):
        """Lines 163-167: sets event and clears callbacks."""
        monitor._monitoring_active = True
        monitor.add_event_callback(ServerEventType.STATUS_CHANGED, AsyncMock())
        await monitor.stop_monitoring()
        assert monitor._shutdown_event.is_set()
        assert len(monitor._event_callbacks[ServerEventType.STATUS_CHANGED]) == 0


# ---------------------------------------------------------------------------
# Lines 171-204: _monitoring_loop
# ---------------------------------------------------------------------------


class TestMonitoringLoop:
    """Covers _monitoring_loop: iterations, health-check gate, logging, errors."""

    @pytest.fixture
    def monitor(self, palworld_config, mock_process_manager, mock_api_facade):
        m = ServerMonitor(palworld_config, mock_process_manager, mock_api_facade)
        m._check_interval = 0.01
        m._health_check_interval = 999999
        m._last_health_check = __import__("time").time()
        m._trigger_event_callbacks = AsyncMock()
        return m

    @pytest.mark.asyncio
    async def test_one_iteration(self, monitor):
        """Lines 171-187: one cycle then shutdown."""

        async def finish_after_first():
            monitor._shutdown_event.set()
            return ServerStatus(
                is_running=True, pid=1, uptime=60, player_count=2, last_check=0
            )

        monitor._get_server_status = finish_after_first
        await monitor._monitoring_loop()
        assert monitor._last_status is not None
        assert monitor._last_status.is_running is True

    @pytest.mark.asyncio
    async def test_health_check_runs_when_interval_elapsed(self, monitor):
        """Lines 183-185: health check triggered when interval expired."""
        monitor._health_check_interval = 0
        monitor._last_health_check = 0
        monitor._perform_health_check = AsyncMock()

        async def finish():
            monitor._shutdown_event.set()
            return ServerStatus(
                is_running=True, pid=1, uptime=60, player_count=0, last_check=0
            )

        monitor._get_server_status = finish
        await monitor._monitoring_loop()
        monitor._perform_health_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_status_changes_called_when_last_status_exists(self, monitor):
        """Lines 180-181: _check_status_changes called if _last_status set."""
        monitor._check_status_changes = AsyncMock()
        monitor._last_status = ServerStatus(
            is_running=True, pid=1, uptime=0, player_count=0, last_check=0
        )

        async def finish():
            monitor._shutdown_event.set()
            return ServerStatus(
                is_running=True, pid=1, uptime=60, player_count=0, last_check=0
            )

        monitor._get_server_status = finish
        await monitor._monitoring_loop()
        monitor._check_status_changes.assert_called_once()

    @pytest.mark.asyncio
    async def test_exception_in_cycle_continues(self, monitor):
        """Lines 197-198: error caught, loop retries."""
        call_n = 0

        async def fail_then_ok():
            nonlocal call_n
            call_n += 1
            if call_n == 1:
                raise RuntimeError("transient")
            monitor._shutdown_event.set()
            return ServerStatus(
                is_running=True, pid=1, uptime=60, player_count=0, last_check=0
            )

        monitor._get_server_status = fail_then_ok
        await monitor._monitoring_loop()
        assert call_n == 2

    @pytest.mark.asyncio
    async def test_logs_every_six_cycles(self, monitor):
        """Lines 189-195: status message logged at cycle % 6 == 0."""
        n = 0

        async def count_and_finish():
            nonlocal n
            n += 1
            if n >= 6:
                monitor._shutdown_event.set()
            return ServerStatus(
                is_running=True, pid=1, uptime=60, player_count=0, last_check=0
            )

        monitor._get_server_status = count_and_finish
        with __import__("unittest.mock", fromlist=["patch"]).patch.object(
            monitor.logger, "info"
        ) as mock_info:
            await monitor._monitoring_loop()
            status_logs = [c for c in mock_info.call_args_list if "Server status:" in str(c)]
            assert len(status_logs) >= 1


# ---------------------------------------------------------------------------
# Lines 208-221: _get_server_status
# ---------------------------------------------------------------------------


class TestGetServerStatus:
    """Covers _get_server_status: running, stopped, API failures."""

    @pytest.fixture
    def monitor(self, palworld_config, mock_process_manager, mock_api_facade):
        return ServerMonitor(palworld_config, mock_process_manager, mock_api_facade)

    @pytest.mark.asyncio
    async def test_running_with_players(self, monitor):
        """Lines 208-226: normal status with player list."""
        monitor.process_manager.get_server_status.return_value = {
            "running": True, "pid": 12345, "uptime": 3600,
        }
        monitor.api_manager.api_get_players = AsyncMock(
            return_value=[{"name": "A"}, {"name": "B"}]
        )
        s = await monitor._get_server_status()
        assert s.is_running is True
        assert s.pid == 12345
        assert s.player_count == 2

    @pytest.mark.asyncio
    async def test_not_running(self, monitor):
        """Server stopped — player_count stays 0."""
        monitor.process_manager.get_server_status.return_value = {
            "running": False, "pid": None, "uptime": 0,
        }
        monitor.api_manager.api_get_players = AsyncMock(return_value=[])
        s = await monitor._get_server_status()
        assert s.is_running is False
        assert s.player_count == 0

    @pytest.mark.asyncio
    async def test_player_api_exception(self, monitor):
        """Lines 218-219: player count defaults to 0 on exception."""
        monitor.process_manager.get_server_status.return_value = {
            "running": True, "pid": 1, "uptime": 60,
        }
        monitor.api_manager.api_get_players = AsyncMock(side_effect=Exception("down"))
        s = await monitor._get_server_status()
        assert s.player_count == 0

    @pytest.mark.asyncio
    async def test_player_count_not_list(self, monitor):
        """Lines 216-217: non-list response keeps count at 0."""
        monitor.process_manager.get_server_status.return_value = {
            "running": True, "pid": 1, "uptime": 60,
        }
        monitor.api_manager.api_get_players = AsyncMock(return_value="unexpected")
        s = await monitor._get_server_status()
        assert s.player_count == 0


# ---------------------------------------------------------------------------
# Lines 231-270: _check_status_changes
# ---------------------------------------------------------------------------


class TestCheckStatusChanges:
    """Covers _check_status_changes: start, stop, restart, no-change."""

    @pytest.fixture
    def monitor(self, palworld_config, mock_process_manager, mock_api_facade):
        return ServerMonitor(palworld_config, mock_process_manager, mock_api_facade)

    @pytest.mark.asyncio
    async def test_no_last_status(self, monitor):
        """Lines 231-232: early return when _last_status is None."""
        monitor._last_status = None
        monitor._trigger_event_callbacks = AsyncMock()
        await monitor._check_status_changes(
            ServerStatus(is_running=True, pid=1, uptime=0, player_count=0, last_check=0)
        )
        monitor._trigger_event_callbacks.assert_not_called()

    @pytest.mark.asyncio
    async def test_server_started(self, monitor):
        """Lines 235-241,253: stopped → running."""
        monitor._last_status = ServerStatus(
            is_running=False, pid=None, uptime=0, player_count=0, last_check=0
        )
        monitor._trigger_event_callbacks = AsyncMock()
        cur = ServerStatus(is_running=True, pid=99, uptime=0, player_count=0, last_check=0)
        await monitor._check_status_changes(cur)
        ev = monitor._trigger_event_callbacks.call_args[0][0]
        assert ev.message == "Server started"
        assert ev.details["pid"] == 99

    @pytest.mark.asyncio
    async def test_server_stopped(self, monitor):
        """Lines 242-251,253: running → stopped."""
        monitor._last_status = ServerStatus(
            is_running=True, pid=99, uptime=3600, player_count=3, last_check=0
        )
        monitor._trigger_event_callbacks = AsyncMock()
        cur = ServerStatus(is_running=False, pid=None, uptime=3600, player_count=0, last_check=0)
        await monitor._check_status_changes(cur)
        ev = monitor._trigger_event_callbacks.call_args[0][0]
        assert ev.message == "Server stopped"
        assert ev.details["previous_pid"] == 99

    @pytest.mark.asyncio
    async def test_pid_restart(self, monitor):
        """Lines 255-270: same running state, different PID."""
        monitor._last_status = ServerStatus(
            is_running=True, pid=111, uptime=60, player_count=0, last_check=0
        )
        monitor._trigger_event_callbacks = AsyncMock()
        cur = ServerStatus(is_running=True, pid=222, uptime=60, player_count=0, last_check=0)
        await monitor._check_status_changes(cur)
        ev = monitor._trigger_event_callbacks.call_args[0][0]
        assert ev.message == "Server process restarted"
        assert ev.details["old_pid"] == 111
        assert ev.details["new_pid"] == 222

    @pytest.mark.asyncio
    async def test_no_change(self, monitor):
        """Identical status → no event."""
        monitor._last_status = ServerStatus(
            is_running=True, pid=1, uptime=60, player_count=2, last_check=0
        )
        monitor._trigger_event_callbacks = AsyncMock()
        cur = ServerStatus(is_running=True, pid=1, uptime=120, player_count=2, last_check=0)
        await monitor._check_status_changes(cur)
        monitor._trigger_event_callbacks.assert_not_called()


# ---------------------------------------------------------------------------
# Lines 274-305: _perform_health_check
# ---------------------------------------------------------------------------


class TestPerformHealthCheck:
    """Covers _perform_health_check: all issue paths and the happy path."""

    @pytest.fixture
    def monitor(self, palworld_config, mock_process_manager, mock_api_facade):
        return ServerMonitor(palworld_config, mock_process_manager, mock_api_facade)

    @pytest.mark.asyncio
    async def test_not_running_early_return(self, monitor):
        """Lines 274-275: no check when server is stopped."""
        monitor._trigger_event_callbacks = AsyncMock()
        await monitor._perform_health_check(
            ServerStatus(is_running=False, pid=None, uptime=0, player_count=0, last_check=0)
        )
        monitor._trigger_event_callbacks.assert_not_called()

    @pytest.mark.asyncio
    async def test_slow_api_response(self, monitor):
        """Lines 284-285: response > 5000 ms flagged."""
        monitor.api_manager.api_get_server_info = AsyncMock(return_value={"ok": True})
        monitor._trigger_event_callbacks = AsyncMock()
        import time as _t
        import unittest.mock as _m

        with _m.patch("time.time", side_effect=[1000.0, 6001.0, 7000.0]):
            await monitor._perform_health_check(
                ServerStatus(is_running=True, pid=1, uptime=60, player_count=1, last_check=0)
            )
        ev = monitor._trigger_event_callbacks.call_args[0][0]
        assert any("Slow API" in i for i in ev.details["issues"])

    @pytest.mark.asyncio
    async def test_api_returns_none(self, monitor):
        """Lines 286-287: API not responding."""
        monitor.api_manager.api_get_server_info = AsyncMock(return_value=None)
        monitor._trigger_event_callbacks = AsyncMock()
        import unittest.mock as _m

        with _m.patch("time.time", side_effect=[1000.0, 1000.1, 1000.2]):
            await monitor._perform_health_check(
                ServerStatus(is_running=True, pid=1, uptime=60, player_count=1, last_check=0)
            )
        ev = monitor._trigger_event_callbacks.call_args[0][0]
        assert "API not responding" in ev.details["issues"]

    @pytest.mark.asyncio
    async def test_api_exception(self, monitor):
        """Lines 288-289: API health check failed."""
        monitor.api_manager.api_get_server_info = AsyncMock(side_effect=Exception("refused"))
        monitor._trigger_event_callbacks = AsyncMock()
        import unittest.mock as _m

        with _m.patch("time.time", side_effect=[1000.0, 1000.1]):
            await monitor._perform_health_check(
                ServerStatus(is_running=True, pid=1, uptime=60, player_count=1, last_check=0)
            )
        ev = monitor._trigger_event_callbacks.call_args[0][0]
        assert any("API health check failed" in i for i in ev.details["issues"])

    @pytest.mark.asyncio
    async def test_idle_server(self, monitor):
        """Lines 291-292: uptime > 3600 with 0 players."""
        monitor.api_manager.api_get_server_info = AsyncMock(return_value={"ok": True})
        monitor._trigger_event_callbacks = AsyncMock()
        import unittest.mock as _m

        with _m.patch("time.time", side_effect=[1000.0, 1000.1, 1000.2]):
            await monitor._perform_health_check(
                ServerStatus(is_running=True, pid=1, uptime=7200, player_count=0, last_check=0)
            )
        ev = monitor._trigger_event_callbacks.call_args[0][0]
        assert any("without players" in i for i in ev.details["issues"])

    @pytest.mark.asyncio
    async def test_all_healthy_no_event(self, monitor):
        """No issues → no callback."""
        monitor.api_manager.api_get_server_info = AsyncMock(return_value={"ok": True})
        monitor._trigger_event_callbacks = AsyncMock()
        import unittest.mock as _m

        with _m.patch("time.time", side_effect=[1000.0, 1000.1]):
            await monitor._perform_health_check(
                ServerStatus(is_running=True, pid=1, uptime=60, player_count=2, last_check=0)
            )
        monitor._trigger_event_callbacks.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_issues(self, monitor):
        """API None + idle server → two issues in one event."""
        monitor.api_manager.api_get_server_info = AsyncMock(return_value=None)
        monitor._trigger_event_callbacks = AsyncMock()
        import unittest.mock as _m

        with _m.patch("time.time", side_effect=[1000.0, 1000.1, 1000.2]):
            await monitor._perform_health_check(
                ServerStatus(is_running=True, pid=1, uptime=7200, player_count=0, last_check=0)
            )
        ev = monitor._trigger_event_callbacks.call_args[0][0]
        assert len(ev.details["issues"]) >= 2


# ---------------------------------------------------------------------------
# Lines 309-315: _trigger_event_callbacks
# ---------------------------------------------------------------------------


class TestTriggerEventCallbacks:
    """Covers _trigger_event_callbacks: normal dispatch and exception handling."""

    @pytest.fixture
    def monitor(self, palworld_config, mock_process_manager, mock_api_facade):
        return ServerMonitor(palworld_config, mock_process_manager, mock_api_facade)

    @pytest.mark.asyncio
    async def test_calls_all_callbacks(self, monitor):
        """Lines 309-313: every registered callback is awaited."""
        import time as _t

        cb1, cb2 = AsyncMock(), AsyncMock()
        monitor.add_event_callback(ServerEventType.STATUS_CHANGED, cb1)
        monitor.add_event_callback(ServerEventType.STATUS_CHANGED, cb2)
        ev = ServerEvent(
            event_type=ServerEventType.STATUS_CHANGED,
            message="x", details={}, timestamp=_t.time(),
        )
        await monitor._trigger_event_callbacks(ev)
        cb1.assert_awaited_once_with(ev)
        cb2.assert_awaited_once_with(ev)

    @pytest.mark.asyncio
    async def test_exception_in_callback_does_not_propagate(self, monitor):
        """Lines 314-315: bad callback logged, others still called."""
        import time as _t

        bad = AsyncMock(side_effect=RuntimeError("oops"))
        good = AsyncMock()
        monitor.add_event_callback(ServerEventType.STATUS_CHANGED, bad)
        monitor.add_event_callback(ServerEventType.STATUS_CHANGED, good)
        ev = ServerEvent(
            event_type=ServerEventType.STATUS_CHANGED,
            message="x", details={}, timestamp=_t.time(),
        )
        await monitor._trigger_event_callbacks(ev)
        good.assert_awaited_once_with(ev)

    @pytest.mark.asyncio
    async def test_no_callbacks_registered(self, monitor):
        """No callbacks → no error."""
        import time as _t

        ev = ServerEvent(
            event_type=ServerEventType.STATUS_CHANGED,
            message="x", details={}, timestamp=_t.time(),
        )
        await monitor._trigger_event_callbacks(ev)
