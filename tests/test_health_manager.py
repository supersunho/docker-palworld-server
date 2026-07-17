"""Tests for the health manager."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
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
