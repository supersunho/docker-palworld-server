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
        assert info is not None

        assert await facade.announce_message_any("Hello") is True
        assert await facade.save_world_any() is True

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
