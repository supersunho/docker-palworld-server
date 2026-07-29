"""Tests for the health manager."""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

import src.utils.health_manager as health_manager_module
from src.utils.health_manager import HealthManager, HealthThresholds

pytestmark = pytest.mark.unit


class TestHealthManager:
    """FS-21.1.x: Health manager behavior."""

    @pytest.fixture
    def manager(self, palworld_config):
        return HealthManager(palworld_config)

    def test_health_thresholds_defaults(self):
        """FS-21.1: Default threshold values."""
        t = HealthThresholds()
        assert t.cpu_warning == 80.0
        assert t.cpu_critical == 90.0
        assert t.memory_warning == 85.0
        assert t.memory_critical == 95.0
        assert t.check_interval == 30

    def test_initial_state(self, manager):
        """FS-21.1: Initial health state."""
        assert manager.consecutive_failures == 0
        assert manager.last_check_time is None
        assert len(manager.health_history) == 0
        assert manager.recovery_enabled is True

    def test_register_recovery_callback(self, manager):
        """FS-21.1.2: Callback registration."""
        cb = lambda x: None
        manager.register_recovery_callback(cb)
        assert cb in manager.recovery_callbacks

    def test_get_health_summary_empty(self, manager):
        """FS-21.1.3: Empty history returns unknown."""
        summary = manager.get_health_summary()
        assert summary["status"] == "unknown"

    def test_update_health_history(self, manager):
        """FS-21.1.3: History tracking."""
        manager._update_health_history({"overall_status": "healthy", "check_success": True})
        assert len(manager.health_history) == 1
        manager._update_health_history({"overall_status": "healthy", "check_success": True})
        assert len(manager.health_history) == 2

    def test_history_max_size(self, manager):
        """FS-21.1.3: History capped at 100."""
        for i in range(110):
            manager._update_health_history({"overall_status": "healthy", "check_success": True})
        assert len(manager.health_history) <= 100

    @pytest.mark.asyncio
    async def test_consecutive_failures_tracking(self, manager):
        """FS-21.1.1: Tracks consecutive failures."""
        await manager._handle_health_result({"overall_status": "unhealthy", "check_success": False})
        assert manager.consecutive_failures == 1
        await manager._handle_health_result({"overall_status": "unhealthy", "check_success": False})
        assert manager.consecutive_failures == 2

    @pytest.mark.asyncio
    async def test_consecutive_failures_reset(self, manager):
        """FS-21.1.1: Resets on success."""
        await manager._handle_health_result({"overall_status": "unhealthy", "check_success": False})
        await manager._handle_health_result({"overall_status": "healthy", "check_success": True})
        assert manager.consecutive_failures == 0

    def test_get_health_summary_after_checks(self, manager):
        """FS-21.1.3: Summary with data."""
        manager._update_health_history({"overall_status": "healthy", "check_success": True})
        manager._update_health_history({"overall_status": "healthy", "check_success": True})
        summary = manager.get_health_summary()
        assert summary["current_status"] == "healthy"
        assert summary["health_percentage"] == 100.0
        assert summary["total_checks"] == 2

    def test_supervisor_loop_notifies_each_result(self, palworld_config):
        """F-04: Supervisor checks notify through the existing helper."""
        palworld_config.monitoring.metrics_interval = 7
        result = {"overall_status": "healthy", "check_success": True}
        manager = MagicMock()
        manager.perform_health_check = AsyncMock(side_effect=[result, asyncio.CancelledError()])
        manager._handle_health_result = AsyncMock()
        manager._notify_health_status = AsyncMock()

        with (
            patch("src.config_loader.get_config", return_value=palworld_config),
            patch.object(health_manager_module, "get_health_manager", return_value=manager),
            patch.object(health_manager_module, "get_logger", return_value=MagicMock()),
            patch.object(health_manager_module.asyncio, "sleep", new_callable=AsyncMock) as sleep,
        ):
            health_manager_module.main()

        manager._notify_health_status.assert_awaited_once_with(result)
        sleep.assert_awaited_once_with(7)

    def test_supervisor_loop_backs_off_after_exception(self, palworld_config):
        """F-04: Supervisor loop waits before retrying after an exception."""
        error = RuntimeError("health check failed")
        manager = MagicMock()
        manager.perform_health_check = AsyncMock(side_effect=[error, asyncio.CancelledError()])
        logger = MagicMock()

        with (
            patch("src.config_loader.get_config", return_value=palworld_config),
            patch.object(health_manager_module, "get_health_manager", return_value=manager),
            patch.object(health_manager_module, "get_logger", return_value=logger),
            patch.object(health_manager_module.asyncio, "sleep", new_callable=AsyncMock) as sleep,
        ):
            health_manager_module.main()

        logger.error.assert_called_once_with("Health check error: %s", error)
        sleep.assert_awaited_once_with(10)
