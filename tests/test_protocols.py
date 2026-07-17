"""Tests for protocol definitions."""

from typing import Protocol
from src.protocols import (


    IProcessManager, IConfigProvider, IServerAPI,
    ServerInfo
)
import pytest

pytestmark = pytest.mark.unit



class TestProtocolDefinitions:
    """FS-4.x: Protocol definitions."""

    def test_server_info_dataclass(self):
        """FS-4.3: ServerInfo fields."""
        info = ServerInfo(
            name="Test",
            players=5,
            max_players=16,
            uptime="1h",
            version="1.0",
            ip="127.0.0.1",
            port=8211,
            info="RCON raw data"
        )
        assert info.name == "Test"
        assert info.players == 5
        assert info.max_players == 16
        assert info.uptime == "1h"
        assert info.version == "1.0"
        assert info.ip == "127.0.0.1"
        assert info.port == 8211
        assert info.info == "RCON raw data"

    def test_server_info_defaults(self):
        info = ServerInfo()
        assert info.name == ""
        assert info.players == 0

    def test_iserverapi_is_protocol(self):
        """FS-4.3: IServerAPI is a Protocol."""
        assert issubclass(IServerAPI, Protocol)

    def test_iprocessmanager_is_protocol(self):
        """FS-4.1: IProcessManager is a Protocol."""
        assert issubclass(IProcessManager, Protocol)

    def test_iconfigprovider_is_protocol(self):
        """FS-4.2: IConfigProvider is a Protocol."""
        assert issubclass(IConfigProvider, Protocol)
