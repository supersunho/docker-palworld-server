"""Tests for REST API client."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.clients.rest_api_client import RestAPIClient

pytestmark = pytest.mark.unit


@pytest.fixture
def api_config():
    """Minimal API config fixture."""
    config = MagicMock()
    config.rest_api.enabled = True
    config.rest_api.port = 8212
    config.rest_api.host = "localhost"
    config.rest_api.timeout = 30
    return config


@pytest.fixture
def api_client(api_config):
    """RestAPIClient fixture with mock logger."""
    logger = MagicMock()
    return RestAPIClient(api_config, logger)


class TestRestAPIClient:
    """Tests for RestAPIClient."""

    @pytest.mark.asyncio
    async def test_aenter_success(self, api_client):
        """__aenter__ creates aiohttp session."""
        with patch("aiohttp.ClientSession") as mock_session:
            session = MagicMock()
            mock_session.return_value = session
            result = await api_client.__aenter__()
            assert result is api_client
            assert api_client.session is session

    @pytest.mark.asyncio
    async def test_aexit_closes_session(self, api_client):
        """__aexit__ closes the HTTP session."""
        api_client.session = MagicMock()
        api_client.session.close = AsyncMock()
        await api_client.__aexit__(None, None, None)
        api_client.session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_aexit_no_session(self, api_client):
        """__aexit__ handles missing session gracefully."""
        api_client.session = None
        await api_client.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_make_request_no_session(self, api_client):
        """_make_request returns None when no session."""
        result = await api_client._make_request("/test")
        assert result is None

    @pytest.mark.asyncio
    async def test_make_request_timeout(self, api_client):
        """_make_request handles asyncio.TimeoutError."""
        api_client.session = MagicMock()
        api_client.session.request = MagicMock()
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError)
        api_client.session.request.return_value = cm
        result = await api_client._make_request("/test")
        assert result is None

    @pytest.mark.asyncio
    async def test_make_request_client_error(self, api_client):
        """_make_request handles aiohttp.ClientError."""
        import aiohttp


        api_client.session = MagicMock()
        api_client.session.request = MagicMock()
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError)
        api_client.session.request.return_value = cm
        result = await api_client._make_request("/test")
        assert result is None

    @pytest.mark.asyncio
    async def test_make_request_http_error(self, api_client):
        """_make_request returns None on HTTP error response."""
        api_client.session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")
        api_client.session.request = MagicMock()
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        api_client.session.request.return_value = cm
        result = await api_client._make_request("/test")
        assert result is None

    @pytest.mark.asyncio
    async def test_make_request_success_json(self, api_client):
        """_make_request returns JSON on success."""
        api_client.session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"key": "value"}')
        mock_response.json = AsyncMock(return_value={"key": "value"})
        api_client.session.request = MagicMock()
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        api_client.session.request.return_value = cm
        result = await api_client._make_request("/test")
        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_make_request_success_raw_text(self, api_client):
        """_make_request returns raw rext when JSON parsing fails."""
        api_client.session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="not json")
        mock_response.json = AsyncMock(side_effect=ValueError("not json"))
        api_client.session.request = MagicMock()
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        api_client.session.request.return_value = cm
        result = await api_client._make_request("/test")
        assert result == {"raw_response": "not json"}

    @pytest.mark.asyncio
    async def test_make_request_with_retry_success(self, api_client):
        """_make_request_with_retry returns result on first attempt."""
        api_client._make_request = AsyncMock(return_value={"ok": True})
        result = await api_client._make_request_with_retry("/test")
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_make_request_with_retry_exhausted(self, api_client):
        """_make_request_with_retry returns None after all retries."""
        api_client._make_request = AsyncMock(side_effect=Exception("fail"))
        result = await api_client._make_request_with_retry("/test", retry_count=2)
        assert result is None
        assert api_client._make_request.await_count == 3

    @pytest.mark.asyncio
    async def test_get_server_info(self, api_client):
        api_client._make_request_with_retry = AsyncMock(return_value={"name": "test"})
        result = await api_client.get_server_info()
        assert result == {"name": "test"}

    @pytest.mark.asyncio
    async def test_get_players(self, api_client):
        api_client._make_request_with_retry = AsyncMock(return_value={"players": [{"name": "P1"}, {"name": "P2"}]})
        result = await api_client.get_players()
        assert result == [{"name": "P1"}, {"name": "P2"}]

    @pytest.mark.asyncio
    async def test_get_players_none(self, api_client):
        api_client._make_request_with_retry = AsyncMock(return_value=None)
        result = await api_client.get_players()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_server_settings(self, api_client):
        api_client._make_request_with_retry = AsyncMock(return_value={"difficulty": "Normal"})
        result = await api_client.get_server_settings()
        assert result == {"difficulty": "Normal"}

    @pytest.mark.asyncio
    async def test_get_server_metrics(self, api_client):
        api_client._make_request_with_retry = AsyncMock(return_value={"cpu": 45.0})
        result = await api_client.get_server_metrics()
        assert result == {"cpu": 45.0}

    @pytest.mark.asyncio
    async def test_announce_message(self, api_client):
        api_client._make_request_with_retry = AsyncMock(return_value={})
        result = await api_client.announce_message("hello")
        assert result is True

    @pytest.mark.asyncio
    async def test_kick_player(self, api_client):
        api_client._make_request_with_retry = AsyncMock(return_value={})
        result = await api_client.kick_player("uid1")
        assert result is True

    @pytest.mark.asyncio
    async def test_ban_player(self, api_client):
        api_client._make_request_with_retry = AsyncMock(return_value={})
        result = await api_client.ban_player("uid1")
        assert result is True

    @pytest.mark.asyncio
    async def test_unban_player(self, api_client):
        api_client._make_request_with_retry = AsyncMock(return_value={})
        result = await api_client.unban_player("uid1")
        assert result is True

    @pytest.mark.asyncio
    async def test_save_world(self, api_client):
        api_client._make_request_with_retry = AsyncMock(return_value={})
        result = await api_client.save_world()
        assert result is True

    @pytest.mark.asyncio
    async def test_shutdown_server(self, api_client):
        api_client._make_request_with_retry = AsyncMock(return_value={})
        result = await api_client.shutdown_server(1, "bye")
        assert result is True
