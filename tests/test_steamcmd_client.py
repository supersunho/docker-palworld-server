"""Tests for SteamCMD client."""

import asyncio
import pytest
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from src.clients.steamcmd_client import SteamCMDManager

pytestmark = pytest.mark.unit


@pytest.fixture
def steamcmd_path(tmp_path):
    """Create a steamcmd directory with steamcmd.sh."""
    d = tmp_path / "steamcmd"
    d.mkdir()
    script = d / "steamcmd.sh"
    script.write_text("#!/bin/bash\necho 'steamcmd'")
    script.chmod(0o755)
    return d


@pytest.fixture
def steamcmd_manager(steamcmd_path):
    """SteamCMDManager fixture with existing steamcmd.sh."""
    logger = MagicMock()
    return SteamCMDManager(steamcmd_path, logger)


class TestSteamCMDManager:
    """Tests for SteamCMDManager."""

    def test_init(self, steamcmd_manager, steamcmd_path):
        assert steamcmd_manager.steamcmd_path == steamcmd_path
        assert steamcmd_manager.steamcmd_script == steamcmd_path / "steamcmd.sh"

    def test_validate_steamcmd_success(self, steamcmd_manager):
        assert steamcmd_manager.validate_steamcmd() is True

    def test_validate_steamcmd_not_exists(self, steamcmd_manager):
        with patch.object(Path, "exists", return_value=False):
            assert steamcmd_manager.validate_steamcmd() is False

    def test_validate_steamcmd_not_file(self, steamcmd_manager):
        with patch.object(Path, "is_file", return_value=False):
            assert steamcmd_manager.validate_steamcmd() is False

    async def test_run_and_stream_timeout(self, steamcmd_manager):
        """_run_and_stream raises on timeout."""
        with patch("asyncio.create_subprocess_exec") as mock_create:
            process = AsyncMock()
            process.wait.side_effect = subprocess.TimeoutExpired("cmd", 1)
            process.stdout.readline = AsyncMock(return_value=b"")
            process.stderr.readline = AsyncMock(return_value=b"")
            mock_create.return_value = process
            with pytest.raises((subprocess.TimeoutExpired, asyncio.TimeoutError)):
                await steamcmd_manager._run_and_stream(
                    ["test"], {}, str(steamcmd_manager.steamcmd_path), 1
                )

    async def test_ensure_updated_no_steamcmd(self, steamcmd_manager):
        with patch.object(steamcmd_manager, "validate_steamcmd", return_value=False):
            assert await steamcmd_manager._ensure_updated() is False

    async def test_ensure_updated_timeout(self, steamcmd_manager):
        with (
            patch.object(steamcmd_manager, "validate_steamcmd", return_value=True),
            patch.object(steamcmd_manager, "_run_and_stream") as mock_ras,
        ):
            mock_ras.side_effect = subprocess.TimeoutExpired("cmd", 1)
            assert await steamcmd_manager._ensure_updated() is True

    async def test_run_command_no_steamcmd(self, steamcmd_manager):
        with patch.object(steamcmd_manager, "validate_steamcmd", return_value=False):
            assert await steamcmd_manager.run_command(["+quit"]) == (False, [])

    async def test_run_command_success(self, steamcmd_manager):
        with (
            patch.object(steamcmd_manager, "validate_steamcmd", return_value=True),
            patch.object(steamcmd_manager, "_ensure_updated", AsyncMock(return_value=True)),
            patch.object(steamcmd_manager, "_run_and_stream", AsyncMock(return_value=(0, []))),
        ):
            assert await steamcmd_manager.run_command(["+quit"]) == (True, [])

    async def test_run_command_failure(self, steamcmd_manager):
        with (
            patch.object(steamcmd_manager, "validate_steamcmd", return_value=True),
            patch.object(steamcmd_manager, "_ensure_updated", AsyncMock(return_value=True)),
            patch.object(steamcmd_manager, "_run_and_stream", AsyncMock(return_value=(1, ["error"]))),
        ):
            assert await steamcmd_manager.run_command(["+quit"]) == (False, ["error"])

    async def test_run_command_timeout(self, steamcmd_manager):
        with (
            patch.object(steamcmd_manager, "validate_steamcmd", return_value=True),
            patch.object(steamcmd_manager, "_ensure_updated", AsyncMock(return_value=True)),
            patch.object(steamcmd_manager, "_run_and_stream") as mock_ras,
        ):
            mock_ras.side_effect = subprocess.TimeoutExpired("cmd", 1)
            assert await steamcmd_manager.run_command(["+quit"]) == (False, [])

    async def test_run_command_exception(self, steamcmd_manager):
        with (
            patch.object(steamcmd_manager, "validate_steamcmd", return_value=True),
            patch.object(steamcmd_manager, "_ensure_updated", AsyncMock(return_value=True)),
            patch.object(steamcmd_manager, "_run_and_stream") as mock_ras,
        ):
            mock_ras.side_effect = Exception("Unexpected error")
            assert await steamcmd_manager.run_command(["+quit"]) == (False, [])
