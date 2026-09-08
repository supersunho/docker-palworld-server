"""Tests for RCON client."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.clients.rcon_client import RconClient

pytestmark = pytest.mark.unit


@pytest.fixture
def rcon_config():
    """Minimal RCON config fixture."""
    config = MagicMock()
    config.rcon.enabled = True
    config.rcon.port = 25575
    config.rcon.host = "localhost"
    config.rcon.password = ""
    config.rcon.timeout = 10
    return config


@pytest.fixture
def rcon_client(rcon_config):
    """RconClient fixture with mock logger."""
    logger = MagicMock()
    return RconClient(rcon_config, logger)


class TestRconClient:
    """Tests for RconClient."""

    @pytest.mark.asyncio
    async def test_aenter_disabled_rcon(self, rcon_config):
        """__aenter__ warns and returns self when RCON not enabled."""
        rcon_config.rcon.enabled = False
        logger = MagicMock()
        client = RconClient(rcon_config, logger)
        result = await client.__aenter__()
        assert result is client
        logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_aenter_rcon_cli_not_available(self, rcon_client):
        """__aenter__ logs error when rcon-cli returns non-zero."""
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            process = MagicMock()
            process.communicate = AsyncMock(return_value=(b"", b""))
            process.returncode = 1
            mock_exec.return_value = process
            result = await rcon_client.__aenter__()
            assert result is rcon_client
            assert rcon_client._is_connected is False

    @pytest.mark.asyncio
    async def test_aenter_rcon_cli_not_found(self, rcon_client):
        """__aenter__ handles FileNotFoundError gracefully."""
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.side_effect = FileNotFoundError()
            result = await rcon_client.__aenter__()
            assert result is rcon_client
            assert rcon_client._is_connected is False

    @pytest.mark.asyncio
    async def test_aenter_success(self, rcon_client):
        """__aenter__ sets _is_connected when rcon-cli is available."""
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            process = MagicMock()
            process.communicate = AsyncMock(return_value=(b"", b""))
            process.returncode = 0
            mock_exec.return_value = process
            result = await rcon_client.__aenter__()
            assert result is rcon_client
            assert rcon_client._is_connected is True

    @pytest.mark.asyncio
    async def test_aexit_connected(self, rcon_client):
        """__aexit__ disconnects when previously connected."""
        rcon_client._is_connected = True
        await rcon_client.__aexit__(None, None, None)
        assert rcon_client._is_connected is False

    @pytest.mark.asyncio
    async def test_aexit_not_connected(self, rcon_client):
        """__aexit__ does nothing when not connected."""
        rcon_client._is_connected = False
        await rcon_client.__aexit__(None, None, None)
        assert rcon_client._is_connected is False

    @pytest.mark.asyncio
    async def test_execute_command_success(self, rcon_client):
        """_execute_command_with_retry returns response on success."""
        rcon_client._is_connected = True
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            process = MagicMock()
            process.communicate = AsyncMock(return_value=(b"Info: server is running", b""))
            process.returncode = 0
            mock_exec.return_value = process
            result = await rcon_client._execute_command_with_retry("Info")
            assert result == "Info: server is running"

    @pytest.mark.asyncio
    async def test_execute_command_not_connected(self, rcon_client):
        """_execute_command_with_retry returns None when not connected."""
        rcon_client._is_connected = False
        result = await rcon_client._execute_command_with_retry("Info")
        assert result is None

    @pytest.mark.asyncio
    async def test_execute_command_retry_then_success(self, rcon_client):
        """_execute_command_with_retry retries on non-zero exit."""
        rcon_client._is_connected = True
        rcon_client._retry_delay = 0.01
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            process_fail = MagicMock()
            process_fail.communicate = AsyncMock(return_value=(b"", b"error"))
            process_fail.returncode = 1

            process_ok = MagicMock()
            process_ok.communicate = AsyncMock(return_value=(b"Info: ok", b""))
            process_ok.returncode = 0

            mock_exec.side_effect = [process_fail, process_ok]
            result = await rcon_client._execute_command_with_retry("Info", retry_count=2)
            assert result == "Info: ok"

    @pytest.mark.asyncio
    async def test_execute_command_final_failure(self, rcon_client):
        """_execute_command_with_retry returns None after all retries exhausted."""
        rcon_client._is_connected = True
        rcon_client._retry_delay = 0.01
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            process_fail = MagicMock()
            process_fail.communicate = AsyncMock(return_value=(b"", b"error"))
            process_fail.returncode = 1
            mock_exec.return_value = process_fail

            result = await rcon_client._execute_command_with_retry("Info", retry_count=2)
            assert result is None

    @pytest.mark.asyncio
    async def test_execute_command_exception_retry(self, rcon_client):
        """_execute_command_with_retry retries on exception."""
        rcon_client._is_connected = True
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.side_effect = Exception("conn error")

            result = await rcon_client._execute_command_with_retry("Info", retry_count=0)
            assert result is None
            assert mock_exec.await_count == 1

    @pytest.mark.asyncio
    async def test_get_server_info(self, rcon_client):
        """get_server_info delegates to _execute_command_with_retry."""
        rcon_client._is_connected = True
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            process = MagicMock()
            process.communicate = AsyncMock(return_value=(b"Info: server", b""))
            process.returncode = 0
            mock_exec.return_value = process
            result = await rcon_client.get_server_info()
            assert result == "Info: server"

    @pytest.mark.asyncio
    async def test_get_players(self, rcon_client):
        rcon_client._is_connected = True
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            process = MagicMock()
            process.communicate = AsyncMock(return_value=(b"players: 3", b""))
            process.returncode = 0
            mock_exec.return_value = process
            result = await rcon_client.get_players()
            assert result == "players: 3"

    @pytest.mark.asyncio
    async def test_announce_message(self, rcon_client):
        rcon_client._is_connected = True
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            process = MagicMock()
            process.communicate = AsyncMock(return_value=(b"OK", b""))
            process.returncode = 0
            mock_exec.return_value = process
            result = await rcon_client.announce_message("hello")
            assert result is True

    @pytest.mark.asyncio
    async def test_announce_message_failure(self, rcon_client):
        rcon_client._is_connected = True
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            process = MagicMock()
            process.communicate = AsyncMock(return_value=(b"", b"error"))
            process.returncode = 1
            mock_exec.return_value = process
            result = await rcon_client.announce_message("hello")
            assert result is False

    @pytest.mark.asyncio
    async def test_kick_player(self, rcon_client):
        rcon_client._is_connected = True
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            process = MagicMock()
            process.communicate = AsyncMock(return_value=(b"Kicked", b""))
            process.returncode = 0
            mock_exec.return_value = process
            result = await rcon_client.kick_player("Player1")
            assert result is True

    @pytest.mark.asyncio
    async def test_ban_player(self, rcon_client):
        rcon_client._is_connected = True
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            process = MagicMock()
            process.communicate = AsyncMock(return_value=(b"Banned", b""))
            process.returncode = 0
            mock_exec.return_value = process
            result = await rcon_client.ban_player("Player1")
            assert result is True

    @pytest.mark.asyncio
    async def test_save_world(self, rcon_client):
        rcon_client._is_connected = True
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            process = MagicMock()
            process.communicate = AsyncMock(return_value=(b"Saved", b""))
            process.returncode = 0
            mock_exec.return_value = process
            result = await rcon_client.save_world()
            assert result is True

    @pytest.mark.asyncio
    async def test_shutdown_server(self, rcon_client):
        rcon_client._is_connected = True
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            process = MagicMock()
            process.communicate = AsyncMock(return_value=(b"Shutdown", b""))
            process.returncode = 0
            mock_exec.return_value = process
            result = await rcon_client.shutdown_server(1, "bye")
            assert result is True

    @pytest.mark.asyncio
    async def test_get_server_settings(self, rcon_client):
        rcon_client._is_connected = True
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            process = MagicMock()
            process.communicate = AsyncMock(return_value=(b"settings", b""))
            process.returncode = 0
            mock_exec.return_value = process
            result = await rcon_client.get_server_settings()
            assert result == "settings"

    @pytest.mark.asyncio
    async def test_execute_custom_command(self, rcon_client):
        rcon_client._is_connected = True
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            process = MagicMock()
            process.communicate = AsyncMock(return_value=(b"custom result", b""))
            process.returncode = 0
            mock_exec.return_value = process
            result = await rcon_client.execute_custom_command("my_command")
            assert result == "custom result"


class TestRconReachabilityProbe:
    """FS-rc: Reachability probe tracks whether the RCON server is reachable."""

    @pytest.mark.asyncio
    async def test_probe_reachable_success_updates_state(self, rcon_client):
        rcon_client._is_connected = True
        rcon_client._execute_command_with_retry = AsyncMock(return_value="server info")
        ok = await rcon_client.probe_reachable(force=True)
        assert ok is True
        assert rcon_client.last_probe_success is True
        assert rcon_client._last_probe_at > 0

    @pytest.mark.asyncio
    async def test_probe_reachable_failure_clears_state(self, rcon_client):
        rcon_client._is_connected = True
        rcon_client._execute_command_with_retry = AsyncMock(return_value=None)
        ok = await rcon_client.probe_reachable(force=True)
        assert ok is False
        assert rcon_client.last_probe_success is False
        assert rcon_client._last_probe_at > 0

    @pytest.mark.asyncio
    async def test_probe_reachable_short_circuits_within_window(self, rcon_client):
        rcon_client._is_connected = True
        rcon_client._execute_command_with_retry = AsyncMock(return_value="info")
        await rcon_client.probe_reachable(force=True)
        # Second call without force must NOT issue another command.
        rcon_client._execute_command_with_retry.reset_mock()
        cached_ok = await rcon_client.probe_reachable(force=False)
        assert cached_ok is True
        rcon_client._execute_command_with_retry.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_probe_reachable_force_overrides_cache(self, rcon_client):
        rcon_client._is_connected = True
        rcon_client._execute_command_with_retry = AsyncMock(return_value="info")
        await rcon_client.probe_reachable(force=True)
        rcon_client._execute_command_with_retry.reset_mock()
        await rcon_client.probe_reachable(force=True)
        rcon_client._execute_command_with_retry.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_probe_reachable_returns_false_when_not_connected(self, rcon_client):
        rcon_client._is_connected = False
        rcon_client._execute_command_with_retry = AsyncMock(return_value="info")
        ok = await rcon_client.probe_reachable(force=True)
        assert ok is False
        rcon_client._execute_command_with_retry.assert_not_awaited()


class TestRconBackoff:
    """FS-rc: Exponential backoff is bounded by _MAX_BACKOFF_SECONDS."""

    def test_backoff_grows_then_caps(self, rcon_client):
        rcon_client._retry_delay = 2.0
        rcon_client._MAX_BACKOFF_SECONDS = 10.0
        # Exponential growth up to cap, then plateau.
        assert rcon_client._backoff_for(0) == 2.0   # 2 * 1
        assert rcon_client._backoff_for(1) == 4.0   # 2 * 2
        assert rcon_client._backoff_for(2) == 8.0   # 2 * 4
        assert rcon_client._backoff_for(3) == 10.0  # would be 16, capped
        assert rcon_client._backoff_for(10) == 10.0

    def test_backoff_unaffected_by_very_high_attempt(self, rcon_client):
        """Sanity: extremely high attempts must not overflow or unbounded-grow."""
        rcon_client._MAX_BACKOFF_SECONDS = 30.0
        # Without cap, attempt=20 would be 2*2**20 ≈ 2M seconds.
        assert rcon_client._backoff_for(20) == 30.0
        assert rcon_client._backoff_for(100) == 30.0
