"""Tests for the player monitor."""

import asyncio
import time
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from src.monitoring.player_monitor import (
    PlayerMonitor,
    PlayerEventType,
    PlayerEvent,
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

    # ── callback registration ────────────────────────────────────────────

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

    def test_add_system_callback(self, monitor):
        """FS-15.3: System callbacks are tracked separately."""
        cb = AsyncMock()
        monitor.add_event_callback(
            PlayerEventType.JOINED, cb, is_system_callback=True
        )
        assert cb in monitor._system_callbacks[PlayerEventType.JOINED]

    def test_remove_event_callback(self, monitor):
        """FS-15.4: Callbacks can be removed."""
        cb = AsyncMock()
        monitor.add_event_callback(PlayerEventType.JOINED, cb)
        assert monitor.remove_event_callback(PlayerEventType.JOINED, cb) is True

    def test_remove_system_callback(self, monitor):
        """FS-15.4: Removing a system callback clears both lists."""
        cb = AsyncMock()
        monitor.add_event_callback(
            PlayerEventType.JOINED, cb, is_system_callback=True
        )
        monitor.remove_event_callback(PlayerEventType.JOINED, cb)
        assert cb not in monitor._event_callbacks[PlayerEventType.JOINED]
        assert cb not in monitor._system_callbacks[PlayerEventType.JOINED]

    def test_remove_nonexistent_callback(self, monitor):
        """FS-15.4: Removing non-existent returns False."""
        cb = AsyncMock()
        assert monitor.remove_event_callback(PlayerEventType.JOINED, cb) is False

    def test_remove_callback_unknown_event_type(self, monitor):
        """FS-15.4: Removing from event type not in _event_callbacks returns False."""
        cb = AsyncMock()
        # Temporarily remove the key to trigger the else branch
        original = monitor._event_callbacks
        monitor._event_callbacks = {}
        try:
            assert monitor.remove_event_callback(PlayerEventType.LEFT, cb) is False
        finally:
            monitor._event_callbacks = original

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

    def test_clear_user_callbacks_all(self, monitor):
        """FS-15.4: Only user callbacks cleared."""
        sys_cb = AsyncMock()
        user_cb = AsyncMock()
        monitor.add_event_callback(
            PlayerEventType.JOINED, sys_cb, is_system_callback=True
        )
        monitor.add_event_callback(PlayerEventType.JOINED, user_cb)
        monitor.clear_user_callbacks()
        assert sys_cb in monitor._event_callbacks[PlayerEventType.JOINED]
        assert user_cb not in monitor._event_callbacks[PlayerEventType.JOINED]

    def test_clear_user_callbacks_specific_event(self, monitor):
        """FS-15.4: clear_user_callbacks with explicit event_type."""
        sys_cb = AsyncMock()
        user_cb = AsyncMock()
        monitor.add_event_callback(
            PlayerEventType.LEFT, sys_cb, is_system_callback=True
        )
        monitor.add_event_callback(PlayerEventType.LEFT, user_cb)
        monitor.clear_user_callbacks(PlayerEventType.LEFT)
        assert sys_cb in monitor._event_callbacks[PlayerEventType.LEFT]
        assert user_cb not in monitor._event_callbacks[PlayerEventType.LEFT]

    # ── player tracking ──────────────────────────────────────────────────

    def test_get_current_players(self, monitor):
        """FS-15: Player tracking."""
        monitor._previous_players = {"P1", "P2"}
        assert monitor.get_current_players() == {"P1", "P2"}
        assert monitor.get_current_player_count() == 2

    def test_is_player_count_known(self, monitor):
        """FS-15: player_count_known getter."""
        monitor._player_count_known = True
        assert monitor.is_player_count_known() is True
        monitor._player_count_known = False
        assert monitor.is_player_count_known() is False

    def test_is_monitoring_active(self, monitor):
        """FS-15: monitoring_active getter."""
        assert monitor.is_monitoring_active() is False
        monitor._monitoring_active = True
        assert monitor.is_monitoring_active() is True

    # ── event detection ──────────────────────────────────────────────────

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

    @pytest.mark.asyncio
    async def test_multiple_joins_and_leaves(self, monitor):
        """FS-15.2: Multiple simultaneous joins and leaves."""
        join_cb = AsyncMock()
        leave_cb = AsyncMock()
        monitor.add_event_callback(PlayerEventType.JOINED, join_cb)
        monitor.add_event_callback(PlayerEventType.LEFT, leave_cb)
        # Player3 joins, Player2 leaves
        await monitor._process_player_changes({"Player1", "Player3"})
        assert join_cb.call_count == 1
        assert leave_cb.call_count == 1

    def test_player_event_dataclass(self):
        """FS-15: PlayerEvent fields."""
        event = PlayerEvent(
            event_type=PlayerEventType.JOINED,
            player_name="Player1",
            player_count=5,
            timestamp=time.time(),
        )
        assert event.event_type == PlayerEventType.JOINED
        assert event.player_name == "Player1"
        assert event.player_count == 5

    # ── debug stats ──────────────────────────────────────────────────────

    def test_get_debug_stats(self, monitor):
        """FS-15.7: Debug stats available."""
        stats = monitor.get_debug_stats()
        assert "monitoring_active" in stats
        assert "current_player_count" in stats
        assert "registered_callbacks" in stats
        assert "retry_configuration" in stats

    def test_get_debug_stats_with_api_calls(self, monitor):
        """FS-15.7: Debug stats reflect API call counts."""
        monitor._successful_api_calls = 10
        monitor._failed_api_calls = 2
        stats = monitor.get_debug_stats()
        assert stats["api_success_rate"] == "10/12"
        assert stats["successful_api_calls"] == 10
        assert stats["failed_api_calls"] == 2

    def test_get_debug_stats_zero_calls(self, monitor):
        """FS-15.7: Debug stats with zero API calls."""
        stats = monitor.get_debug_stats()
        assert stats["api_success_rate"] == "0/0"

    # ── trigger_event_callbacks ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_trigger_callbacks_empty(self, monitor):
        """FS-15: No callbacks → warning + early return."""
        event = PlayerEvent(
            event_type=PlayerEventType.JOINED,
            player_name="X",
            player_count=1,
            timestamp=time.time(),
        )
        # Ensure no callbacks registered
        monitor._event_callbacks[PlayerEventType.JOINED] = []
        await monitor._trigger_event_callbacks(event)

    @pytest.mark.asyncio
    async def test_trigger_callbacks_exception_in_callback(self, monitor):
        """FS-15: Exception in callback is caught, doesn't propagate."""
        good_cb = AsyncMock()
        bad_cb = AsyncMock(side_effect=RuntimeError("boom"))
        monitor.add_event_callback(PlayerEventType.JOINED, bad_cb)
        monitor.add_event_callback(PlayerEventType.JOINED, good_cb)
        event = PlayerEvent(
            event_type=PlayerEventType.JOINED,
            player_name="X",
            player_count=1,
            timestamp=time.time(),
        )
        # Should not raise
        await monitor._trigger_event_callbacks(event)
        bad_cb.assert_called_once()
        good_cb.assert_called_once()

    # ── start/stop monitoring ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_start_monitoring_already_active(self, monitor):
        """FS-15.6: start_monitoring returns early if already active."""
        monitor._monitoring_active = True
        await monitor.start_monitoring()
        # Should return without error; _monitoring_active still True
        assert monitor._monitoring_active is True

    @pytest.mark.asyncio
    async def test_start_monitoring_runs_loop(self, monitor):
        """FS-15.6: start_monitoring runs the loop and cleans up on exit."""
        monitor.api_manager.get_players = AsyncMock(return_value=[{"name": "A"}])
        monitor._check_interval = 0.01

        async def _loop_side_effect():
            # Simulate one cycle then shutdown
            monitor._shutdown_event.set()

        with patch.object(
            monitor, "_monitoring_loop", side_effect=_loop_side_effect
        ):
            await monitor.start_monitoring()
        assert monitor._monitoring_active is False

    @pytest.mark.asyncio
    async def test_start_monitoring_exception_in_loop(self, monitor):
        """FS-15.6: start_monitoring catches exception from loop."""
        async def _loop_that_raises():
            raise RuntimeError("loop exploded")

        with patch.object(
            monitor, "_monitoring_loop", side_effect=_loop_that_raises
        ):
            await monitor.start_monitoring()
        assert monitor._monitoring_active is False

    @pytest.mark.asyncio
    async def test_stop_monitoring_clears_state(self, monitor):
        """FS-15.6: Stop clears callbacks and player set."""
        monitor.add_event_callback(PlayerEventType.JOINED, AsyncMock())
        monitor._monitoring_active = True
        await monitor.stop_monitoring()
        assert monitor._monitoring_active is False
        assert len(monitor._event_callbacks[PlayerEventType.JOINED]) == 0
        assert len(monitor._previous_players) == 0

    @pytest.mark.asyncio
    async def test_stop_monitoring_already_inactive(self, monitor):
        """FS-15.6: stop_monitoring returns early if not active."""
        monitor._monitoring_active = False
        await monitor.stop_monitoring()
        assert monitor._monitoring_active is False

    # ── monitoring loop ──────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_monitoring_loop_single_cycle(self, monitor):
        """FS-15.6: _monitoring_loop runs one cycle then shuts down."""
        monitor.api_manager.get_players = AsyncMock(
            return_value=[{"name": "P1"}, {"name": "P2"}]
        )
        monitor._check_interval = 0.01

        # Shutdown after first cycle
        async def fake_wait(**kwargs):
            monitor._shutdown_event.set()
            raise asyncio.TimeoutError()

        monitor._shutdown_event.wait = fake_wait

        await monitor._monitoring_loop()
        assert monitor._debug_cycle_count >= 1

    @pytest.mark.asyncio
    async def test_monitoring_loop_first_check(self, monitor):
        """FS-15.6: _monitoring_loop handles first check path."""
        monitor._first_check = True
        monitor.api_manager.get_players = AsyncMock(
            return_value=[{"name": "X"}]
        )
        monitor._check_interval = 0.01

        async def fake_wait(**kwargs):
            monitor._shutdown_event.set()
            raise asyncio.TimeoutError()

        monitor._shutdown_event.wait = fake_wait

        await monitor._monitoring_loop()
        assert monitor._first_check is False
        assert "X" in monitor._previous_players

    @pytest.mark.asyncio
    async def test_monitoring_loop_api_returns_none(self, monitor):
        """FS-15.6: _monitoring_loop handles None API response."""
        monitor.api_manager.get_players = AsyncMock(return_value=None)
        monitor._check_interval = 0.01

        async def fake_wait(**kwargs):
            monitor._shutdown_event.set()
            raise asyncio.TimeoutError()

        monitor._shutdown_event.wait = fake_wait

        await monitor._monitoring_loop()
        assert monitor._player_count_known is False

    @pytest.mark.asyncio
    async def test_monitoring_loop_cycle_exception(self, monitor):
        """FS-15.6: _monitoring_loop handles cycle exceptions in the main body."""
        call_count = 0

        async def flaky_get_players():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [{"name": "X"}]
            raise RuntimeError("transient")

        monitor.api_manager.get_players = flaky_get_players
        monitor._check_interval = 0.01

        # Patch wait_for: first call raises TimeoutError (continue),
        # second call returns (break)
        wf_count = 0

        async def fake_wait_for(coro, timeout=None):
            nonlocal wf_count
            wf_count += 1
            if wf_count >= 2:
                monitor._shutdown_event.set()
                return None
            raise asyncio.TimeoutError()

        with patch("src.monitoring.player_monitor.asyncio.wait_for", side_effect=fake_wait_for):
            await monitor._monitoring_loop()

        assert monitor._debug_cycle_count >= 2

    @pytest.mark.asyncio
    async def test_monitoring_loop_process_changes_raises(self, monitor):
        """FS-15.6: _monitoring_loop catches exception from _process_player_changes."""
        monitor.api_manager.get_players = AsyncMock(
            return_value=[{"name": "P1"}, {"name": "P2"}]
        )
        monitor._check_interval = 0.01

        wf_count = 0

        async def fake_wait_for(coro, timeout=None):
            nonlocal wf_count
            wf_count += 1
            if wf_count >= 2:
                monitor._shutdown_event.set()
                return None
            raise asyncio.TimeoutError()

        # Make _process_player_changes raise on subsequent calls (not first_check)
        pp_count = 0
        original_pp = monitor._process_player_changes

        async def flaky_pp(players):
            nonlocal pp_count
            pp_count += 1
            if pp_count >= 1:
                raise RuntimeError("process exploded")
            return await original_pp(players)

        monitor._process_player_changes = flaky_pp

        with patch("src.monitoring.player_monitor.asyncio.wait_for", side_effect=fake_wait_for):
            await monitor._monitoring_loop()

        # Loop survived the exception
        assert monitor._debug_cycle_count >= 2

    @pytest.mark.asyncio
    async def test_monitoring_loop_mod5_debug_log(self, monitor):
        """FS-15.6: cycle count 5 triggers debug log."""
        monitor.api_manager.get_players = AsyncMock(return_value=[])
        monitor._check_interval = 0.01
        # Set cycle count so next increment hits 5
        monitor._debug_cycle_count = 4

        cycle = 0

        async def fake_wait(**kwargs):
            nonlocal cycle
            cycle += 1
            if cycle >= 1:
                monitor._shutdown_event.set()
            raise asyncio.TimeoutError()

        monitor._shutdown_event.wait = fake_wait

        await monitor._monitoring_loop()
        assert monitor._debug_cycle_count == 5

    @pytest.mark.asyncio
    async def test_monitoring_loop_mod6_debug_log(self, monitor):
        """FS-15.6: cycle count 6 triggers success-rate debug log."""
        monitor.api_manager.get_players = AsyncMock(return_value=[])
        monitor._check_interval = 0.01
        monitor._debug_cycle_count = 5
        monitor._successful_api_calls = 5
        monitor._failed_api_calls = 1

        cycle = 0

        async def fake_wait(**kwargs):
            nonlocal cycle
            cycle += 1
            if cycle >= 1:
                monitor._shutdown_event.set()
            raise asyncio.TimeoutError()

        monitor._shutdown_event.wait = fake_wait

        await monitor._monitoring_loop()
        assert monitor._debug_cycle_count == 6

    @pytest.mark.asyncio
    async def test_monitoring_loop_slow_cycle_warning(self, monitor):
        """FS-15.6: Slow cycle (>1s) triggers warning."""
        monitor._check_interval = 0.01

        async def slow_get_players():
            await asyncio.sleep(1.05)
            return []

        monitor.api_manager.get_players = slow_get_players

        cycle = 0

        async def fake_wait(**kwargs):
            nonlocal cycle
            cycle += 1
            if cycle >= 1:
                monitor._shutdown_event.set()
            raise asyncio.TimeoutError()

        monitor._shutdown_event.wait = fake_wait

        await monitor._monitoring_loop()
        assert monitor._debug_cycle_count >= 1

    @pytest.mark.asyncio
    async def test_monitoring_loop_break_on_shutdown(self, monitor):
        """FS-15.6: _monitoring_loop breaks when shutdown_event fires during wait."""
        monitor.api_manager.get_players = AsyncMock(return_value=[])
        monitor._check_interval = 0.01

        # Patch wait_for to simulate: first call raises TimeoutError (continue),
        # second call returns normally (break path)
        original_wait_for = asyncio.wait_for
        call_count = 0

        async def fake_wait_for(coro, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise asyncio.TimeoutError()
            # On second call, set the event and return (simulating event firing)
            monitor._shutdown_event.set()
            return None

        with patch("src.monitoring.player_monitor.asyncio.wait_for", side_effect=fake_wait_for):
            await monitor._monitoring_loop()

        assert monitor._debug_cycle_count >= 2

    # ── _get_current_players ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_players_list_response(self, monitor):
        """FS-15.2: Parses list of player dicts."""
        monitor.api_manager.get_players = AsyncMock(
            return_value=[
                {"name": "Alice"},
                {"name": "Bob"},
            ]
        )
        result = await monitor._get_current_players()
        assert result == {"Alice", "Bob"}

    @pytest.mark.asyncio
    async def test_get_players_dict_with_players_key(self, monitor):
        """FS-15.2: Parses dict with 'players' key."""
        monitor.api_manager.get_players = AsyncMock(
            return_value={"players": [{"name": "X"}, {"name": "Y"}]}
        )
        result = await monitor._get_current_players()
        assert result == {"X", "Y"}

    @pytest.mark.asyncio
    async def test_get_players_dict_with_data_key(self, monitor):
        """FS-15.2: Parses dict with 'data' key."""
        monitor.api_manager.get_players = AsyncMock(
            return_value={"data": [{"name": "A"}]}
        )
        result = await monitor._get_current_players()
        assert result == {"A"}

    @pytest.mark.asyncio
    async def test_get_players_dict_unexpected_structure(self, monitor):
        """FS-15.2: Dict with unexpected keys returns empty set."""
        monitor.api_manager.get_players = AsyncMock(
            return_value={"unexpected": [{"name": "X"}]}
        )
        result = await monitor._get_current_players()
        assert result == set()

    @pytest.mark.asyncio
    async def test_get_players_none_response(self, monitor):
        """FS-15.2: None response returns None."""
        monitor.api_manager.get_players = AsyncMock(return_value=None)
        result = await monitor._get_current_players()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_players_none_retries(self, monitor):
        """FS-15.2: None response triggers retries."""
        monitor.api_manager.get_players = AsyncMock(
            side_effect=[None, None, None]
        )
        with patch("src.monitoring.player_monitor.asyncio.sleep", new_callable=AsyncMock):
            result = await monitor._get_current_players()
        assert result is None
        assert monitor._failed_api_calls >= 3

    @pytest.mark.asyncio
    async def test_get_players_unexpected_type(self, monitor):
        """FS-15.2: Non-dict/non-list response returns None."""
        monitor.api_manager.get_players = AsyncMock(return_value="unexpected")
        with patch("src.monitoring.player_monitor.asyncio.sleep", new_callable=AsyncMock):
            result = await monitor._get_current_players()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_players_exception_retries(self, monitor):
        """FS-15.2: API exception triggers retries."""
        monitor.api_manager.get_players = AsyncMock(
            side_effect=[RuntimeError("net"), RuntimeError("net"), RuntimeError("net")]
        )
        with patch("src.monitoring.player_monitor.asyncio.sleep", new_callable=AsyncMock):
            result = await monitor._get_current_players()
        assert result is None
        assert monitor._failed_api_calls == 3

    @pytest.mark.asyncio
    async def test_get_players_exception_recovers(self, monitor):
        """FS-15.2: API exception on first attempt, success on retry."""
        monitor.api_manager.get_players = AsyncMock(
            side_effect=[RuntimeError("net"), [{"name": "Recovered"}]]
        )
        with patch("src.monitoring.player_monitor.asyncio.sleep", new_callable=AsyncMock):
            result = await monitor._get_current_players()
        assert result == {"Recovered"}

    @pytest.mark.asyncio
    async def test_get_players_invalid_name_fields(self, monitor):
        """FS-15.2: Players with missing/blank/whitespace names skipped."""
        monitor.api_manager.get_players = AsyncMock(
            return_value=[
                {"name": "Valid"},
                {"name": ""},           # empty
                {"name": "   "},        # whitespace only
                {"playerName": "Alt"},  # alternate field
                {},                     # no name field at all
            ]
        )
        result = await monitor._get_current_players()
        assert result == {"Valid", "Alt"}

    @pytest.mark.asyncio
    async def test_get_players_non_dict_in_list(self, monitor):
        """FS-15.2: Non-dict entries in list are skipped."""
        monitor.api_manager.get_players = AsyncMock(
            return_value=[{"name": "A"}, "not_a_dict", 42]
        )
        result = await monitor._get_current_players()
        assert result == {"A"}

    @pytest.mark.asyncio
    async def test_get_players_alternate_name_fields(self, monitor):
        """FS-15.2: playerName, player_name, username fields parsed."""
        monitor.api_manager.get_players = AsyncMock(
            return_value=[
                {"playerName": "ViaPlayerName"},
                {"player_name": "ViaPlayerName2"},
                {"username": "ViaUsername"},
            ]
        )
        result = await monitor._get_current_players()
        assert result == {"ViaPlayerName", "ViaPlayerName2", "ViaUsername"}

    @pytest.mark.asyncio
    async def test_get_players_empty_list(self, monitor):
        """FS-15.2: Empty list returns empty set."""
        monitor.api_manager.get_players = AsyncMock(return_value=[])
        result = await monitor._get_current_players()
        assert result == set()
        assert monitor._successful_api_calls >= 1
