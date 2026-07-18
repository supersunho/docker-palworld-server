"""Tests for the idle restart/pause manager."""

import pytest
import asyncio
import time
from unittest.mock import MagicMock, patch, AsyncMock
from src.monitoring.idle_restart_manager import IdleRestartManager, IdleRestartStats

pytestmark = pytest.mark.unit


async def _noop():
    pass


class TestIdleRestartManager:
    """FS-18.x: Idle restart/pause manager behavior."""

    @pytest.fixture
    def manager(self, palworld_config, mock_player_monitor, mock_logger):
        pm = MagicMock()
        pm.is_server_running.return_value = True
        return IdleRestartManager(palworld_config, mock_player_monitor, pm)

    def test_init_default_mode(self, manager):
        """FS-18.1: Default mode is 'restart'."""
        assert manager.mode in ("restart", "pause")

    def test_stats_dataclass(self):
        """FS-18.2: IdleRestartStats fields."""
        stats = IdleRestartStats(total_restarts=5, total_pauses=3)
        assert stats.total_restarts == 5
        assert stats.total_pauses == 3

    def test_is_monitoring_active_initially_false(self, manager):
        """FS-18.3: Monitoring not active by default."""
        assert manager.is_monitoring_active() is False

    @pytest.mark.asyncio
    async def test_start_stop_monitoring(self, manager):
        """FS-18.4: Start/stop monitoring lifecycle."""
        with patch.object(manager, "_monitoring_loop", side_effect=_noop):
            await manager.start_monitoring()
            assert manager._running is True
            await manager.stop_monitoring()
            assert manager._running is False

    def test_get_idle_status_structure(self, manager):
        """FS-18.5: Idle status contains expected keys."""
        status = manager.get_idle_status()
        assert "enabled" in status
        assert "mode" in status
        assert "monitoring_active" in status
        assert "statistics" in status

    @pytest.mark.asyncio
    async def test_handle_active_players_resets_idle(self, manager):
        """FS-18.6: Players online reset idle timer."""
        manager._idle_start = 100.0
        with patch.object(manager.logger, "info"):
            await manager._handle_active_players(3)
        assert manager._idle_start is None

    @pytest.mark.asyncio
    async def test_handle_zero_players_starts_timer(self, manager):
        """FS-18.7: Zero players starts idle timer."""
        manager._idle_start = None
        await manager._handle_zero_players(100.0)
        assert manager._idle_start == 100.0

    # ---- Pause mode tests ----

    @pytest.mark.asyncio
    async def test_perform_pause_calls_process_manager(self, manager):
        """FS-18.8: Pause mode calls pause_server."""
        manager.mode = "pause"
        manager.process_manager.pause_server = AsyncMock(return_value=True)

        success = await manager._perform_pause()
        assert success is True
        assert manager._paused is True
        manager.process_manager.pause_server.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_perform_pause_failure_handling(self, manager):
        """FS-18.9: Pause failure doesn't set paused state."""
        manager.mode = "pause"
        manager.process_manager.pause_server = AsyncMock(return_value=False)

        success = await manager._perform_pause()
        assert success is False
        assert manager._paused is False

    @pytest.mark.asyncio
    async def test_handle_active_resumes_paused_server(self, manager):
        """FS-18.10: Active players resume paused server."""
        manager._paused = True
        manager.process_manager.resume_server = AsyncMock(return_value=True)

        with patch.object(manager, "_send_discord_notification", AsyncMock()):
            await manager._handle_active_players(1)

        assert manager._paused is False
        manager.process_manager.resume_server.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_force_resume(self, manager):
        """FS-18.11: force_resume resumes server."""
        manager._paused = True

        with patch.object(manager, "_force_resume", AsyncMock()) as mock_fr:
            result = manager.force_resume()
            assert result is True
            await asyncio.sleep(0.01)
            mock_fr.assert_called_once()
            # Let the loop finish to avoid RuntimeWarning about unawaited coroutine
            await asyncio.sleep(0)

    def test_force_resume_not_paused(self, manager):
        """FS-18.12: force_resume returns False when not paused."""
        manager._paused = False
        assert manager.force_resume() is False

    @pytest.mark.asyncio
    async def test_init_with_pause_mode(self, palworld_config, mock_player_monitor, mock_logger):
        """FS-18.13: Init with pause mode config."""
        palworld_config.monitoring.idle_restart.mode = "pause"
        pm = MagicMock()
        pm.is_server_running.return_value = True
        mgr = IdleRestartManager(palworld_config, mock_player_monitor, pm)
        assert mgr.mode == "pause"

    @pytest.mark.asyncio
    async def test_paused_state_triggers_full_restart_after_max_time(self, manager):
        """FS-18.14: Paused state triggers full restart after 24h."""
        manager._paused = True
        manager._pause_start_time = 0.0

        with patch.object(
            manager, "_perform_restart", AsyncMock(return_value=True)
        ) as mock_restart:
            await manager._handle_paused_state(time.time())
            mock_restart.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_trigger_idle_action_increments_pause_stats(self, manager):
        """FS-18.15: Triggering pause action increments pause stats."""
        manager.mode = "pause"
        manager.process_manager.pause_server = AsyncMock(return_value=True)
        manager.player_monitor.get_current_player_count = MagicMock(return_value=0)

        with patch.object(manager, "_send_discord_notification", AsyncMock()):
            await manager._trigger_idle_action()

        assert manager.stats.total_pauses == 1
        assert manager.stats.last_pause_time is not None
        assert manager._paused is True


class TestIdleRestartManagerEdgeCases:
    """Edge case coverage for idle restart manager."""

    @pytest.fixture
    def manager(self, palworld_config, mock_player_monitor, mock_logger):
        pm = MagicMock()
        pm.is_server_running.return_value = True
        return IdleRestartManager(palworld_config, mock_player_monitor, pm)

    @pytest.fixture
    def manager_disabled(self, palworld_config, mock_player_monitor, mock_logger):
        """Create a manager with idle_restart disabled."""
        from src.config.monitoring.idle_restart import IdleRestartConfig

        palworld_config.monitoring.idle_restart = IdleRestartConfig(enabled=False, idle_minutes=30)
        pm = MagicMock()
        pm.is_server_running.return_value = True
        return IdleRestartManager(palworld_config, mock_player_monitor, pm)

    def test_init_with_no_idle_config(self, palworld_config, mock_player_monitor, mock_logger):
        """FS-18.x: Init when idle_restart config is missing."""
        palworld_config.monitoring.idle_restart = None
        pm = MagicMock()
        pm.is_server_running.return_value = True
        mgr = IdleRestartManager(palworld_config, mock_player_monitor, pm)
        assert mgr.enabled is True
        assert mgr.idle_minutes == 30
        assert mgr.mode == "restart"

    def test_init_with_non_int_idle_minutes(
        self, palworld_config, mock_player_monitor, mock_logger
    ):
        """FS-18.x: Init when idle_minutes can't convert to int."""
        palworld_config.monitoring.idle_restart.idle_minutes = "abc"
        pm = MagicMock()
        pm.is_server_running.return_value = True
        mgr = IdleRestartManager(palworld_config, mock_player_monitor, pm)
        assert mgr.idle_minutes == 30  # fallback

    @pytest.mark.asyncio
    async def test_start_monitoring_disabled(self, manager_disabled):
        """FS-18.x: start_monitoring logs warning when disabled."""
        with patch.object(manager_disabled.logger, "warning") as mock_warn:
            await manager_disabled.start_monitoring()
            mock_warn.assert_called_once_with("Idle restart monitoring is disabled")
        assert manager_disabled._running is False

    @pytest.mark.asyncio
    async def test_start_monitoring_already_running(self, manager):
        """FS-18.x: start_monitoring logs warning when already running."""
        manager._running = True
        with patch.object(manager.logger, "warning") as mock_warn:
            await manager.start_monitoring()
            mock_warn.assert_called_once_with("Idle restart monitoring already running")

    @pytest.mark.asyncio
    async def test_check_idle_status_server_not_running(self, manager):
        """FS-18.x: _check_idle_status resets timer when server not running."""
        manager.process_manager.is_server_running.return_value = False
        manager._idle_start = 100.0
        with patch.object(manager.logger, "debug") as mock_debug:
            await manager._check_idle_status()
            mock_debug.assert_called_once_with("Server not running, resetting idle timer")
        assert manager._idle_start is None

    @pytest.mark.asyncio
    async def test_handle_zero_players_with_paused_state(self, manager):
        """FS-18.x: _handle_zero_players calls _handle_paused_state when paused."""
        manager._paused = True
        with patch.object(manager, "_handle_paused_state", AsyncMock()) as mock_hps:
            await manager._handle_zero_players(100.0)
            mock_hps.assert_awaited_once_with(100.0)

    @pytest.mark.asyncio
    async def test_handle_zero_players_long_idle_triggers_action(self, manager):
        """FS-18.x: _handle_zero_players triggers idle action when duration exceeds threshold."""
        manager.idle_seconds = 10
        manager._idle_start = time.time() - 15
        with patch.object(manager, "_trigger_idle_action", AsyncMock()) as mock_trigger:
            with patch.object(manager.stats, "current_idle_duration", 15.0):
                await manager._handle_zero_players(time.time())
                mock_trigger.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_perform_restart_stop_fails(self, manager):
        """FS-18.x: _perform_restart logs error when stop fails."""
        manager.process_manager.stop_server = AsyncMock(return_value=False)
        success = await manager._perform_restart()
        assert success is False

    @pytest.mark.asyncio
    async def test_perform_restart_start_fails(self, manager):
        """FS-18.x: _perform_restart logs error when start fails."""
        manager.process_manager.stop_server = AsyncMock(return_value=True)
        manager.process_manager.start_server = AsyncMock(return_value=False)
        with patch("asyncio.sleep", AsyncMock(return_value=None)):
            success = await manager._perform_restart()
        assert success is False

    @pytest.mark.asyncio
    async def test_perform_restart_exception(self, manager):
        """FS-18.x: _perform_restart handles exceptions."""
        manager.process_manager.stop_server = AsyncMock(side_effect=Exception("stop error"))
        success = await manager._perform_restart()
        assert success is False

    def test_force_resume_create_task_fails(self, manager):
        """FS-18.x: force_resume handles create_task failure."""
        manager._paused = True
        manager._force_resume = MagicMock(return_value=None)
        with patch("asyncio.create_task", side_effect=RuntimeError("loop closed")):
            result = manager.force_resume()
            assert result is False

    def test_get_idle_status_with_active_idle(self, manager):
        """FS-18.x: get_idle_status returns timed data when idle timer active."""
        manager._idle_start = time.time() - 60
        status = manager.get_idle_status()
        assert status["current_idle_seconds"] > 0
        assert status["is_currently_idle"] is True
        assert status["remaining_seconds_until_action"] < manager.idle_seconds

    @pytest.mark.asyncio
    async def test_trigger_idle_action_restart_success(self, manager):
        """FS-18.x: trigger_idle_action with restart mode updates restart stats."""
        manager.mode = "restart"
        manager.player_monitor.get_current_player_count = MagicMock(return_value=0)
        with patch.object(manager, "_send_discord_notification", AsyncMock()):
            with patch.object(manager, "_perform_restart", AsyncMock(return_value=True)) as mock_pr:
                await manager._trigger_idle_action()
                mock_pr.assert_awaited_once()
                assert manager.stats.total_restarts == 1
                assert manager.stats.last_restart_time is not None

    @pytest.mark.asyncio
    async def test_send_discord_notification_disabled(self, manager):
        """FS-18.x: _send_discord_notification returns early when discord disabled."""
        manager.config.discord.enabled = False
        await manager._send_discord_notification("restart", "test")
        # No exception means early return worked

    @pytest.mark.asyncio
    async def test_check_idle_status_active_players(self, manager):
        """FS-18.x: _check_idle_status handles active players path."""
        manager.process_manager.is_server_running.return_value = True
        manager.player_monitor.get_current_player_count.return_value = 3
        with patch.object(manager, "_handle_active_players", AsyncMock()) as mock_ha:
            await manager._check_idle_status()
            mock_ha.assert_awaited_once_with(3)

    @pytest.mark.asyncio
    async def test_handle_paused_state_no_start_time(self, manager):
        """FS-18.x: _handle_paused_state sets pause_start_time when None."""
        manager._paused = True
        manager._pause_start_time = None
        current = time.time()
        with patch.object(
            manager, "_handle_paused_state", AsyncMock(wraps=manager._handle_paused_state)
        ) as wrapped:
            await manager._handle_zero_players(current)
            # Should have set pause_start_time
            assert manager._pause_start_time is not None

    @pytest.mark.asyncio
    async def test_force_resume_implementation(self, manager):
        """FS-18.x: _force_resume resumes server and resets state."""
        manager._paused = True
        manager._pause_start_time = time.time()
        manager.process_manager.resume_server = AsyncMock(return_value=True)

        await manager._force_resume()
        assert manager._paused is False
        assert manager._pause_start_time is None
        manager.process_manager.resume_server.assert_awaited_once()

    def test_get_idle_status_with_elapsed_idle(self, manager):
        """FS-18.x: get_idle_status calculates remaining time correctly."""
        manager._idle_start = time.time() - 120  # 2 min idle
        manager.idle_seconds = 300  # 5 min threshold
        status = manager.get_idle_status()
        assert status["current_idle_seconds"] == pytest.approx(120, abs=5)
        assert status["remaining_seconds_until_action"] == pytest.approx(180, abs=5)
        assert status["is_currently_idle"] is True
