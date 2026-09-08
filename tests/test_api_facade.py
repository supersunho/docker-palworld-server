"""Tests for the API facade."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.managers.api_facade import ServerAPIFacade, ServerInfo
from src.protocols import IServerAPI

pytestmark = pytest.mark.unit


class TestServerAPIFacade:
    """FS-10.x: API facade behavior."""

    @pytest.fixture
    def facade(self, palworld_config, mock_logger, mock_rest_client, mock_rcon_client):
        f = ServerAPIFacade(palworld_config, mock_logger)
        f._rest = mock_rest_client
        f._rcon = mock_rcon_client
        f._rest_available = True
        f._rcon_available = True
        return f

    @pytest.mark.asyncio
    async def test_get_server_info_rest_first(self, facade):
        """FS-10.2+10.4: REST API used first, returns ServerInfo."""
        result = await facade.get_server_info()
        assert isinstance(result, ServerInfo)
        assert result.name == "Test Server"
        assert result.players == 3
        facade._rest.get_server_info.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_server_info_rcon_fallback(self, facade):
        """FS-10.2+10.4: Fallback to RCON when REST fails."""
        facade._rest.get_server_info = AsyncMock(return_value=None)
        result = await facade.get_server_info()
        assert isinstance(result, ServerInfo)
        assert result.info == "SERVER INFO: Test Server, Players: 3/16"
        facade._rcon.get_server_info.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_server_info_both_fail(self, facade):
        """FS-10.2: Returns None when both fail."""
        facade._rest.get_server_info = AsyncMock(return_value=None)
        facade._rcon.get_server_info = AsyncMock(return_value=None)
        result = await facade.get_server_info()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_players_rest_first(self, facade):
        """FS-10.5: REST API players used first."""
        result = await facade.get_players()
        assert result is not None
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_players_rcon_csv_fallback(self, facade):
        """FS-10.5: RCON CSV parsed as fallback."""
        facade._rest.get_players = AsyncMock(return_value=None)
        result = await facade.get_players()
        assert result is not None
        assert len(result) == 2
        assert result[0]["name"] == "Player1"

    @pytest.mark.asyncio
    async def test_announce_rest_first(self, facade):
        """FS-10.2: announce uses REST first."""
        result = await facade.announce("Hello")
        assert result is True
        facade._rest.announce_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_announce_rcon_fallback(self, facade):
        """FS-10.2: announce falls back to RCON."""
        facade._rest.announce_message = AsyncMock(return_value=False)
        result = await facade.announce("Hello")
        assert result is True
        facade._rcon.announce_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_save_world_rest_first(self, facade):
        result = await facade.save_world()
        assert result is True
        facade._rest.save_world.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_kick_player(self, facade):
        result = await facade.kick_player("uid1")
        assert result is True

    @pytest.mark.asyncio
    async def test_ban_player(self, facade):
        result = await facade.ban_player("uid1")
        assert result is True

    @pytest.mark.asyncio
    async def test_unban_player(self, facade):
        result = await facade.unban_player("uid1")
        assert result is True

    @pytest.mark.asyncio
    async def test_shutdown_server(self, facade):
        result = await facade.shutdown_server(1, "bye")
        assert result is True

    @pytest.mark.asyncio
    async def test_direct_rest_methods(self, facade):
        """FS-10.3: Direct REST accessor methods."""
        assert await facade.api_get_server_info() is not None
        assert await facade.api_get_players() is not None
        assert await facade.api_get_server_settings() is not None
        assert await facade.api_get_server_metrics() is not None
        assert await facade.api_announce_message("Hello") is True

    @pytest.mark.asyncio
    async def test_direct_rcon_methods(self, facade):
        """FS-10.3: Direct RCON accessor methods."""
        assert await facade.rcon_get_server_info() is not None
        assert await facade.rcon_get_players() is not None
        assert await facade.rcon_announce_message("Hi") is True
        assert await facade.rcon_kick_player("Player1") is True
        assert await facade.rcon_ban_player("Player1") is True

    @pytest.mark.asyncio
    async def test_fallback_any_methods(self, facade):
        """FS-10.3: _any fallback methods."""
        info = await facade.get_server_info_any()
        # get_server_info_any must return the same normalized dataclass
        # as get_server_info, NOT a raw dict with a "source" key.
        assert isinstance(info, ServerInfo)
        assert not isinstance(info, dict)

        assert await facade.announce_message_any("Hello") is True
        assert await facade.save_world_any() is True

    @pytest.mark.asyncio
    async def test_get_server_info_any_matches_normalized_get_server_info(self, facade):
        """FS-10.3: get_server_info_any and get_server_info return identical
        normalized ServerInfo objects (REST path)."""
        normal = await facade.get_server_info()
        any_info = await facade.get_server_info_any()
        assert isinstance(normal, ServerInfo)
        assert isinstance(any_info, ServerInfo)
        assert normal.name == any_info.name
        assert normal.players == any_info.players
        assert normal.max_players == any_info.max_players

    @pytest.mark.asyncio
    async def test_get_server_info_any_rcon_fallback_returns_server_info(self, facade):
        """FS-10.3: get_server_info_any with REST failure still produces a
        normalized ServerInfo from the RCON string (no raw {"source": ...}
        dict leaking through)."""
        facade._rest.get_server_info = AsyncMock(return_value=None)
        any_info = await facade.get_server_info_any()
        assert isinstance(any_info, ServerInfo)
        assert any_info.info == "SERVER INFO: Test Server, Players: 3/16"

    def test_is_rcon_available_with_no_probe_assumes_available(self, facade):
        """FS-rc: When no probe has run yet (initial state), the facade
        falls back to the legacy ``_rcon_available`` flag so the first
        command attempt can populate the probe result."""
        # Default fixture has _last_probe_at == 0.0
        assert facade._is_rcon_available() is True

    def test_is_rcon_available_respects_failed_probe(self, facade):
        """FS-rc: A recent failed probe must mark RCON as unavailable
        even if ``_rcon_available`` is still True."""
        facade._rcon._last_probe_at = 1.0  # any non-zero timestamp
        facade._rcon.last_probe_success = False
        assert facade._is_rcon_available() is False

    def test_is_rcon_available_respects_successful_probe(self, facade):
        """FS-rc: A recent successful probe keeps RCON marked available."""
        facade._rcon._last_probe_at = 1.0
        facade._rcon.last_probe_success = True
        assert facade._is_rcon_available() is True

    def test_is_rcon_available_false_when_client_missing(self, facade):
        """FS-rc: No RCON client at all -> unavailable."""
        facade._rcon = None
        assert facade._is_rcon_available() is False

    def test_client_accessors(self, facade):
        """FS-10.3: Direct client access."""
        assert facade.get_api_client() is not None
        assert facade.get_rcon_client() is not None

    def test_get_client_status(self, facade):
        """FS-10.7: Client status dict."""
        status = facade.get_client_status()
        assert status["rest_available"] is True
        assert status["rcon_available"] is True

    @pytest.mark.asyncio
    async def test_rcon_not_available_returns_none(self, facade):
        """FS-10.3: RCON methods return None/False when unavailable."""
        facade._rcon_available = False
        facade._rcon = None
        assert await facade.rcon_get_server_info() is None
        assert await facade.rcon_announce_message("Hi") is False
        assert facade.get_rcon_client() is None

    @pytest.mark.asyncio
    async def test_rest_not_available_returns_none(self, facade):
        """FS-10.3: REST methods return None/False when unavailable."""
        facade._rest_available = False
        facade._rest = None
        assert await facade.api_get_server_info() is None
        assert await facade.api_announce_message("Hi") is False
        assert facade.get_api_client() is None

    def test_implements_iserverapi(self, facade):
        """FS-10.1+4.3: Facade implements IServerAPI protocol."""
        assert isinstance(facade, IServerAPI)

    @pytest.mark.asyncio
    async def test_get_players_rcon_header_only_returns_empty_list(self, facade):
        """R2-P2-01: Header-only RCON response (0 players) returns [] not None."""
        facade._rest_available = False
        facade._rcon_available = True
        facade._rcon.get_players = AsyncMock(return_value="name,playeruid,steamid")
        result = await facade.get_players()
        assert result is not None
        assert result == []


class TestServerAPIFacadeInitialization:
    """FS-10.6: Facade initialization/cleanup."""

    @pytest.mark.asyncio
    async def test_initialize_clients_rest_enabled(self, palworld_config, mock_logger):
        """FS-10.6: Initialize REST client when enabled."""
        facade = ServerAPIFacade(palworld_config, mock_logger)
        with patch("src.managers.api_facade.RestAPIClient") as mock_rest_cls:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock()
            mock_instance.session = MagicMock()
            mock_instance.session.closed = False
            mock_rest_cls.return_value = mock_instance

            await facade.initialize_clients()
            assert facade._rest is not None
            assert facade._rest_available is True

    @pytest.mark.asyncio
    async def test_cleanup_clients(self, palworld_config, mock_logger):
        """FS-10.6: Cleanup closes clients."""
        facade = ServerAPIFacade(palworld_config, mock_logger)
        rest_mock = MagicMock()
        facade._rest = rest_mock
        rest_mock.__aexit__ = AsyncMock()
        rest_mock.session = MagicMock()
        rest_mock.session.closed = False
        facade._rest_available = True

        await facade.cleanup_clients()
        rest_mock.__aexit__.assert_awaited_once()
        assert facade._rest is None
        assert facade._rest_available is False


# ── Coverage expansion tests ────────────────────────────────────────────
# Root cause: existing tests only exercise the happy-path branches.
# Missing: exception handlers, RCON-fallback paths in all facade methods,
# initialization failures, cleanup errors, and direct api_*/rcon_* unavailable states.


def _facade(palworld_config, mock_logger, rest=True, rcon=True):
    """Build a ServerAPIFacade with mock clients."""
    facade = ServerAPIFacade(palworld_config, mock_logger)
    if rest:
        r = MagicMock()
        r.session = MagicMock()
        r.session.closed = False
        facade._rest = r
        facade._rest_available = True
    if rcon:
        rc = MagicMock()
        rc._last_probe_at = 0.0  # no probe yet → available
        # Make all async methods awaitable with sensible defaults
        rc.get_server_info = AsyncMock(return_value="SERVER INFO: Test Server, Players: 3/16")
        rc.get_players = AsyncMock(
            return_value="name,playeruid,steamid\nPlayer1,uid1,steam1\nPlayer2,uid2,steam2"
        )
        rc.get_server_settings = AsyncMock(return_value="Difficulty=None")
        rc.announce_message = AsyncMock(return_value=True)
        rc.kick_player = AsyncMock(return_value=True)
        rc.ban_player = AsyncMock(return_value=True)
        rc.save_world = AsyncMock(return_value=True)
        rc.shutdown_server = AsyncMock(return_value=True)
        rc.execute_custom_command = AsyncMock(return_value="OK")
        facade._rcon = rc
        facade._rcon_available = True
    return facade


class TestInitializeAndCleanupExceptions:
    """Lines 41-44, 52-55, 63-64, 70-77: exception handlers in init/cleanup."""

    @pytest.mark.asyncio
    async def test_initialize_rest_exception(self, palworld_config, mock_logger):
        """Lines 41-44: REST init failure handled, client set to None."""
        facade = ServerAPIFacade(palworld_config, mock_logger)
        with patch("src.managers.api_facade.RestAPIClient") as cls:
            cls.return_value.__aenter__ = AsyncMock(
                side_effect=RuntimeError("REST init failed")
            )
            await facade.initialize_clients()
        assert facade._rest is None
        assert facade._rest_available is False

    @pytest.mark.asyncio
    async def test_initialize_rcon_exception(self, palworld_config, mock_logger):
        """Lines 52-55: RCON init failure handled, client set to None."""
        facade = ServerAPIFacade(palworld_config, mock_logger)
        with patch("src.managers.api_facade.RconClient") as cls:
            cls.return_value.__aenter__ = AsyncMock(
                side_effect=RuntimeError("RCON init failed")
            )
            await facade.initialize_clients()
        assert facade._rcon is None
        assert facade._rcon_available is False

    @pytest.mark.asyncio
    async def test_cleanup_rest_exception(self, palworld_config, mock_logger):
        """Lines 63-64: REST cleanup exception logged, client still cleaned up."""
        facade = ServerAPIFacade(palworld_config, mock_logger)
        r = MagicMock()
        r.__aexit__ = AsyncMock(side_effect=RuntimeError("REST cleanup err"))
        r.session = MagicMock()
        r.session.closed = False
        facade._rest = r
        facade._rest_available = True
        await facade.cleanup_clients()
        assert facade._rest is None
        assert facade._rest_available is False

    @pytest.mark.asyncio
    async def test_cleanup_rcon_exception(self, palworld_config, mock_logger):
        """Lines 70-77: RCON cleanup exception logged, finally block runs."""
        facade = ServerAPIFacade(palworld_config, mock_logger)
        rc = MagicMock()
        rc.__aexit__ = AsyncMock(side_effect=RuntimeError("RCON cleanup err"))
        facade._rcon = rc
        facade._rcon_available = True
        await facade.cleanup_clients()
        assert facade._rcon is None
        assert facade._rcon_available is False


class TestDirectApiUnavailable:
    """Lines 127-129, 134, 137-139, 144, 147-149, 154, 157-159, 167-169,
    173-179, 183-189, 193-199, 203-209, 215-221:
    api_* methods return None/False when REST unavailable, exception paths."""

    @pytest.mark.asyncio
    async def test_api_get_server_info_unavailable(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger, rest=False)
        assert await facade.api_get_server_info() is None

    @pytest.mark.asyncio
    async def test_api_get_server_info_exception(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger)
        facade._rest.get_server_info = AsyncMock(side_effect=RuntimeError("err"))
        assert await facade.api_get_server_info() is None

    @pytest.mark.asyncio
    async def test_api_get_players_unavailable(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger, rest=False)
        assert await facade.api_get_players() is None

    @pytest.mark.asyncio
    async def test_api_get_players_exception(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger)
        facade._rest.get_players = AsyncMock(side_effect=RuntimeError("err"))
        assert await facade.api_get_players() is None

    @pytest.mark.asyncio
    async def test_api_get_server_settings_unavailable(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger, rest=False)
        assert await facade.api_get_server_settings() is None

    @pytest.mark.asyncio
    async def test_api_get_server_settings_exception(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger)
        facade._rest.get_server_settings = AsyncMock(side_effect=RuntimeError("err"))
        assert await facade.api_get_server_settings() is None

    @pytest.mark.asyncio
    async def test_api_get_server_metrics_unavailable(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger, rest=False)
        assert await facade.api_get_server_metrics() is None

    @pytest.mark.asyncio
    async def test_api_get_server_metrics_exception(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger)
        facade._rest.get_server_metrics = AsyncMock(side_effect=RuntimeError("err"))
        assert await facade.api_get_server_metrics() is None

    @pytest.mark.asyncio
    async def test_api_announce_message_unavailable(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger, rest=False)
        assert await facade.api_announce_message("hi") is False

    @pytest.mark.asyncio
    async def test_api_announce_message_exception(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger)
        facade._rest.announce_message = AsyncMock(side_effect=RuntimeError("err"))
        assert await facade.api_announce_message("hi") is False

    @pytest.mark.asyncio
    async def test_api_kick_player_unavailable(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger, rest=False)
        assert await facade.api_kick_player("uid") is False

    @pytest.mark.asyncio
    async def test_api_kick_player_exception(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger)
        facade._rest.kick_player = AsyncMock(side_effect=RuntimeError("err"))
        assert await facade.api_kick_player("uid") is False

    @pytest.mark.asyncio
    async def test_api_ban_player_unavailable(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger, rest=False)
        assert await facade.api_ban_player("uid") is False

    @pytest.mark.asyncio
    async def test_api_ban_player_exception(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger)
        facade._rest.ban_player = AsyncMock(side_effect=RuntimeError("err"))
        assert await facade.api_ban_player("uid") is False

    @pytest.mark.asyncio
    async def test_api_unban_player_unavailable(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger, rest=False)
        assert await facade.api_unban_player("uid") is False

    @pytest.mark.asyncio
    async def test_api_unban_player_exception(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger)
        facade._rest.unban_player = AsyncMock(side_effect=RuntimeError("err"))
        assert await facade.api_unban_player("uid") is False

    @pytest.mark.asyncio
    async def test_api_save_world_unavailable(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger, rest=False)
        assert await facade.api_save_world() is False

    @pytest.mark.asyncio
    async def test_api_save_world_exception(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger)
        facade._rest.save_world = AsyncMock(side_effect=RuntimeError("err"))
        assert await facade.api_save_world() is False

    @pytest.mark.asyncio
    async def test_api_shutdown_server_unavailable(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger, rest=False)
        assert await facade.api_shutdown_server() is False

    @pytest.mark.asyncio
    async def test_api_shutdown_server_exception(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger)
        facade._rest.shutdown_server = AsyncMock(side_effect=RuntimeError("err"))
        assert await facade.api_shutdown_server() is False


class TestDirectRconUnavailable:
    """Lines 231-233, 238, 241-243, 251-253, 258, 261-263, 268,
    271-273, 277-283, 289-295, 299-305:
    rcon_* methods return None/False when RCON unavailable, exception paths."""

    @pytest.mark.asyncio
    async def test_rcon_get_server_info_unavailable(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger, rcon=False)
        assert await facade.rcon_get_server_info() is None

    @pytest.mark.asyncio
    async def test_rcon_get_server_info_exception(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger)
        facade._rcon.get_server_info = AsyncMock(side_effect=RuntimeError("err"))
        assert await facade.rcon_get_server_info() is None

    @pytest.mark.asyncio
    async def test_rcon_get_players_unavailable(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger, rcon=False)
        assert await facade.rcon_get_players() is None

    @pytest.mark.asyncio
    async def test_rcon_get_players_exception(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger)
        facade._rcon.get_players = AsyncMock(side_effect=RuntimeError("err"))
        assert await facade.rcon_get_players() is None

    @pytest.mark.asyncio
    async def test_rcon_announce_message_unavailable(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger, rcon=False)
        assert await facade.rcon_announce_message("hi") is False

    @pytest.mark.asyncio
    async def test_rcon_announce_message_exception(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger)
        facade._rcon.announce_message = AsyncMock(side_effect=RuntimeError("err"))
        assert await facade.rcon_announce_message("hi") is False

    @pytest.mark.asyncio
    async def test_rcon_kick_player_unavailable(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger, rcon=False)
        assert await facade.rcon_kick_player("name") is False

    @pytest.mark.asyncio
    async def test_rcon_kick_player_exception(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger)
        facade._rcon.kick_player = AsyncMock(side_effect=RuntimeError("err"))
        assert await facade.rcon_kick_player("name") is False

    @pytest.mark.asyncio
    async def test_rcon_ban_player_unavailable(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger, rcon=False)
        assert await facade.rcon_ban_player("name") is False

    @pytest.mark.asyncio
    async def test_rcon_ban_player_exception(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger)
        facade._rcon.ban_player = AsyncMock(side_effect=RuntimeError("err"))
        assert await facade.rcon_ban_player("name") is False

    @pytest.mark.asyncio
    async def test_rcon_save_world_unavailable(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger, rcon=False)
        assert await facade.rcon_save_world() is False

    @pytest.mark.asyncio
    async def test_rcon_save_world_exception(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger)
        facade._rcon.save_world = AsyncMock(side_effect=RuntimeError("err"))
        assert await facade.rcon_save_world() is False

    @pytest.mark.asyncio
    async def test_rcon_shutdown_server_unavailable(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger, rcon=False)
        assert await facade.rcon_shutdown_server() is False

    @pytest.mark.asyncio
    async def test_rcon_shutdown_server_exception(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger)
        facade._rcon.shutdown_server = AsyncMock(side_effect=RuntimeError("err"))
        assert await facade.rcon_shutdown_server() is False

    @pytest.mark.asyncio
    async def test_rcon_execute_command_unavailable(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger, rcon=False)
        assert await facade.rcon_execute_command("cmd") is None

    @pytest.mark.asyncio
    async def test_rcon_execute_command_exception(self, palworld_config, mock_logger):
        facade = _facade(palworld_config, mock_logger)
        facade._rcon.execute_custom_command = AsyncMock(side_effect=RuntimeError("err"))
        assert await facade.rcon_execute_command("cmd") is None


class TestFallbackRconPaths:
    """Lines 324-325, 332-333, 344-345, 367-370, 388-389, 394-397,
    409-418, 426-442, 450-459, 467-476, 483-485, 493-502:
    REST-fail → RCON fallback paths, RCON exception paths, and
    REST exception paths in fallback methods."""

    # -- get_server_info fallback (324-325, 332-333) --

    @pytest.mark.asyncio
    async def test_get_server_info_rest_exception_rcon_fallback(self, palworld_config, mock_logger):
        """Lines 324-325: REST exception → RCON fallback."""
        facade = _facade(palworld_config, mock_logger)
        facade._rest.get_server_info = AsyncMock(side_effect=RuntimeError("REST err"))
        result = await facade.get_server_info()
        assert isinstance(result, ServerInfo)
        assert result.info == "SERVER INFO: Test Server, Players: 3/16"

    @pytest.mark.asyncio
    async def test_get_server_info_rcon_exception(self, palworld_config, mock_logger):
        """Lines 332-333: RCON exception in fallback."""
        facade = _facade(palworld_config, mock_logger, rest=False)
        facade._rcon.get_server_info = AsyncMock(side_effect=RuntimeError("RCON err"))
        assert await facade.get_server_info() is None

    # -- get_players fallback (344-345, 367-370) --

    @pytest.mark.asyncio
    async def test_get_players_rest_exception_rcon_fallback(self, palworld_config, mock_logger):
        """Lines 344-345: REST exception → RCON fallback."""
        facade = _facade(palworld_config, mock_logger)
        facade._rest.get_players = AsyncMock(side_effect=RuntimeError("REST err"))
        result = await facade.get_players()
        assert result is not None
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_players_rcon_exception(self, palworld_config, mock_logger):
        """Lines 367-370: RCON exception in fallback."""
        facade = _facade(palworld_config, mock_logger, rest=False)
        facade._rcon.get_players = AsyncMock(side_effect=RuntimeError("RCON err"))
        assert await facade.get_players() is None

    # -- announce fallback (388-389, 394-397) --

    @pytest.mark.asyncio
    async def test_announce_rest_exception_rcon_fallback(self, palworld_config, mock_logger):
        """Lines 388-389: REST exception → RCON fallback."""
        facade = _facade(palworld_config, mock_logger)
        facade._rest.announce_message = AsyncMock(side_effect=RuntimeError("REST err"))
        assert await facade.announce("hi") is True

    @pytest.mark.asyncio
    async def test_announce_rcon_exception(self, palworld_config, mock_logger):
        """Lines 394-397: RCON exception in fallback."""
        facade = _facade(palworld_config, mock_logger, rest=False)
        facade._rcon.announce_message = AsyncMock(side_effect=RuntimeError("RCON err"))
        assert await facade.announce("hi") is False

    # -- save_world fallback (409-418) --

    @pytest.mark.asyncio
    async def test_save_world_rest_exception_rcon_success(self, palworld_config, mock_logger):
        """Lines 409-418: REST exception → RCON fallback."""
        facade = _facade(palworld_config, mock_logger)
        facade._rest.save_world = AsyncMock(side_effect=RuntimeError("REST err"))
        assert await facade.save_world() is True

    @pytest.mark.asyncio
    async def test_save_world_rcon_exception(self, palworld_config, mock_logger):
        """Lines 409-418: RCON exception in save_world fallback."""
        facade = _facade(palworld_config, mock_logger, rest=False)
        facade._rcon.save_world = AsyncMock(side_effect=RuntimeError("RCON err"))
        assert await facade.save_world() is False

    # -- get_server_settings fallback (426-442) --

    @pytest.mark.asyncio
    async def test_get_server_settings_rest_exception_rcon_fallback(self, palworld_config, mock_logger):
        """Lines 426-442: REST exception → RCON fallback."""
        facade = _facade(palworld_config, mock_logger)
        facade._rest.get_server_settings = AsyncMock(side_effect=RuntimeError("REST err"))
        result = await facade.get_server_settings()
        assert result == {"raw_settings": "Difficulty=None"}

    @pytest.mark.asyncio
    async def test_get_server_settings_rcon_exception(self, palworld_config, mock_logger):
        """Lines 426-442: RCON exception in settings fallback."""
        facade = _facade(palworld_config, mock_logger, rest=False)
        facade._rcon.get_server_settings = AsyncMock(side_effect=RuntimeError("RCON err"))
        assert await facade.get_server_settings() is None

    @pytest.mark.asyncio
    async def test_get_server_settings_both_fail(self, palworld_config, mock_logger):
        """Lines 426-442: Both REST and RCON return falsy → None."""
        facade = _facade(palworld_config, mock_logger)
        facade._rest.get_server_settings = AsyncMock(return_value=None)
        facade._rcon.get_server_settings = AsyncMock(return_value=None)
        assert await facade.get_server_settings() is None

    # -- kick_player fallback (450-459) --

    @pytest.mark.asyncio
    async def test_kick_player_rest_exception_rcon_fallback(self, palworld_config, mock_logger):
        """Lines 450-459: REST exception → RCON fallback."""
        facade = _facade(palworld_config, mock_logger)
        facade._rest.kick_player = AsyncMock(side_effect=RuntimeError("REST err"))
        assert await facade.kick_player("uid") is True

    @pytest.mark.asyncio
    async def test_kick_player_rcon_exception(self, palworld_config, mock_logger):
        """Lines 450-459: RCON exception in kick fallback."""
        facade = _facade(palworld_config, mock_logger, rest=False)
        facade._rcon.kick_player = AsyncMock(side_effect=RuntimeError("RCON err"))
        assert await facade.kick_player("uid") is False

    # -- ban_player fallback (467-476) --

    @pytest.mark.asyncio
    async def test_ban_player_rest_exception_rcon_fallback(self, palworld_config, mock_logger):
        """Lines 467-476: REST exception → RCON fallback."""
        facade = _facade(palworld_config, mock_logger)
        facade._rest.ban_player = AsyncMock(side_effect=RuntimeError("REST err"))
        assert await facade.ban_player("uid") is True

    @pytest.mark.asyncio
    async def test_ban_player_rcon_exception(self, palworld_config, mock_logger):
        """Lines 467-476: RCON exception in ban fallback."""
        facade = _facade(palworld_config, mock_logger, rest=False)
        facade._rcon.ban_player = AsyncMock(side_effect=RuntimeError("RCON err"))
        assert await facade.ban_player("uid") is False

    # -- unban_player REST exception (483-485) --

    @pytest.mark.asyncio
    async def test_unban_player_rest_exception(self, palworld_config, mock_logger):
        """Lines 483-485: REST exception in unban."""
        facade = _facade(palworld_config, mock_logger)
        facade._rest.unban_player = AsyncMock(side_effect=RuntimeError("REST err"))
        assert await facade.unban_player("uid") is False

    # -- shutdown_server fallback (493-502) --

    @pytest.mark.asyncio
    async def test_shutdown_server_rest_exception_rcon_fallback(self, palworld_config, mock_logger):
        """Lines 493-502: REST exception → RCON fallback."""
        facade = _facade(palworld_config, mock_logger)
        facade._rest.shutdown_server = AsyncMock(side_effect=RuntimeError("REST err"))
        assert await facade.shutdown_server(1, "bye") is True

    @pytest.mark.asyncio
    async def test_shutdown_server_rcon_exception(self, palworld_config, mock_logger):
        """Lines 493-502: RCON exception in shutdown fallback."""
        facade = _facade(palworld_config, mock_logger, rest=False)
        facade._rcon.shutdown_server = AsyncMock(side_effect=RuntimeError("RCON err"))
        assert await facade.shutdown_server(1, "bye") is False
