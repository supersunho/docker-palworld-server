"""Tests for GuildConfig dataclass."""

import pytest
from dataclasses import fields, asdict
from src.config.game.guild import GuildConfig

pytestmark = pytest.mark.unit


class TestGuildConfig:
    """GuildConfig dataclass unit tests."""

    def test_default_values(self):
        """Default values match expectations."""
        config = GuildConfig()
        assert config.player_max_num == 20
        assert config.auto_reset_guild_no_online_players is False
        assert config.auto_reset_guild_time_no_online_players == 72.0

    def test_field_count(self):
        """Field count guards against drift."""
        assert len(fields(GuildConfig)) == 3

    def test_type_hints(self):
        """Type hints match expected types."""
        for f in fields(GuildConfig):
            if f.name == "player_max_num":
                assert f.type is int, f"Expected int for {f.name}, got {f.type}"
            elif f.name == "auto_reset_guild_no_online_players":
                assert f.type is bool, f"Expected bool for {f.name}, got {f.type}"
            elif f.name == "auto_reset_guild_time_no_online_players":
                assert f.type is float, f"Expected float for {f.name}, got {f.type}"

    def test_custom_values(self):
        """Constructor args propagate correctly."""
        config = GuildConfig(player_max_num=50, auto_reset_guild_no_online_players=True)
        assert config.player_max_num == 50
        assert config.auto_reset_guild_no_online_players is True

    def test_asdict_roundtrip(self):
        """asdict round-trip preserves values."""
        config = GuildConfig(player_max_num=10, auto_reset_guild_time_no_online_players=48.0)
        d = asdict(config)
        restored = GuildConfig(**d)
        assert restored == config

    def test_time_boundary(self):
        """Time field accepts zero and large values."""
        config = GuildConfig(auto_reset_guild_time_no_online_players=0.0)
        assert config.auto_reset_guild_time_no_online_players == 0.0
        config = GuildConfig(auto_reset_guild_time_no_online_players=999.9)
        assert config.auto_reset_guild_time_no_online_players == 999.9
