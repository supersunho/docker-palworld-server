"""Tests for the lifecycle manager."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.managers.lifecycle_manager import (


    ServerLifecycleManager, verify_server_startup
)

pytestmark = pytest.mark.unit



class TestLifecycleManager:
    """FS-9.x: Lifecycle manager behavior."""

    @pytest.fixture
    def manager(self, palworld_config, mock_logger):
        pm = MagicMock()
        pm.start_server = AsyncMock(return_value=True)
        pm.stop_server = AsyncMock(return_value=True)
        pm.is_server_running = MagicMock(return_value=True)
        pm.get_server_status = MagicMock(return_value={
            'running': True, 'pid': 12345, 'uptime': 3600
        })
        pm.server_process = MagicMock()
        pm.server_process.pid = 12345
        return ServerLifecycleManager(palworld_config, mock_logger, process_manager=pm)

    @pytest.mark.asyncio
    async def test_start_success(self, manager):
        """FS-9.1: Start delegates to process manager."""
        result = await manager.start()
        assert result is True
        manager.process_manager.start_server.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_failure(self, manager):
        """FS-9.1: Start failure returns False."""
        manager.process_manager.start_server = AsyncMock(return_value=False)
        result = await manager.start()
        assert result is False

    @pytest.mark.asyncio
    async def test_stop_graceful(self, manager):
        """FS-9.2: Graceful stop delegates."""
        result = await manager.stop(graceful=True)
        assert result is True
        manager.process_manager.stop_server.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_restart_success(self, manager):
        """FS-9.4: Successful restart."""
        result = await manager.restart()
        assert result is True
        manager.process_manager.stop_server.assert_awaited()
        assert manager.process_manager.start_server.await_count >= 1

    @pytest.mark.asyncio
    async def test_restart_stop_fails(self, manager):
        """FS-9.4: Restart fails if stop fails."""
        manager.process_manager.stop_server = AsyncMock(return_value=False)
        result = await manager.restart()
        assert result is False

    @pytest.mark.asyncio
    async def test_verify_startup(self, manager):
        """FS-9.5: Verify delegates to helper."""
        result = await manager.verify_startup()
        assert result is True

    def test_get_server_status(self, manager):
        """FS-9: Status delegation."""
        status = manager.get_server_status()
        assert status["running"] is True



    @pytest.mark.asyncio
    async def test_stop_already_stopped(self, manager):
        """FS-9.3: Stop returns True when already stopped."""
        manager.process_manager.is_server_running = MagicMock(return_value=False)
        result = await manager.stop(graceful=True)
        assert result is True

    @pytest.mark.asyncio
    async def test_restart_start_fails(self, manager):
        """FS-9.4: Restart fails if start fails after stop."""
        manager.process_manager.stop_server = AsyncMock(return_value=True)
        manager.process_manager.start_server = AsyncMock(return_value=False)
        result = await manager.restart()
        assert result is False

class TestVerifyServerStartup:
    """FS-9.5: verify_server_startup function."""

    @pytest.mark.asyncio
    async def test_not_running(self):
        pm = MagicMock()
        pm.is_server_running = MagicMock(return_value=False)
        result = await verify_server_startup(pm, max_wait_time=5)
        assert result is False

    @pytest.mark.asyncio
    async def test_running_and_stable(self):
        pm = MagicMock()
        pm.is_server_running = MagicMock(return_value=True)
        result = await verify_server_startup(pm, max_wait_time=5)
        assert result is True

    @pytest.mark.asyncio
    async def test_crashes_during_check(self):
        pm = MagicMock()
        pm.is_server_running = MagicMock(side_effect=[True, True, False])
        result = await verify_server_startup(pm, max_wait_time=5)
        assert result is False
