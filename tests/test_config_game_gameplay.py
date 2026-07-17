"""Tests for GameplayConfig dataclass."""

import pytest
from dataclasses import fields, asdict
from src.config.game.gameplay import GameplayConfig

pytestmark = pytest.mark.unit


class TestGameplayConfig:
    """GameplayConfig dataclass unit tests."""

    def test_default_values(self):
        """Default values match expectations."""
        config = GameplayConfig()
        assert config.region == ""
        assert config.banlist_url == "https://api.palworldgame.com/api/banlist.txt"
        assert config.enable_player_to_player_damage is False
        assert config.enable_friendly_fire is False
        assert config.enable_invader_enemy is True
        assert config.is_multiplay is True
        assert config.is_pvp is False
        assert config.coop_player_max_num == 4
        assert config.enable_non_login_penalty is True
        assert config.enable_fast_travel is True
        assert config.is_start_location_select_by_map is True
        assert config.exist_player_after_logout is False
        assert config.enable_defense_other_guild_player is False
        assert config.can_pickup_other_guild_death_penalty_drop is False
        assert config.enable_aim_assist_pad is True
        assert config.enable_aim_assist_keyboard is False
        assert config.active_unko is False
        assert config.use_auth is True

    def test_field_count(self):
        """Field count guards against drift."""
        assert len(fields(GameplayConfig)) == 18

    def test_type_hints(self):
        """Type hints match expected types."""
        for f in fields(GameplayConfig):
            if f.name in ("region", "banlist_url"):
                assert f.type is str, f"Expected str for {f.name}, got {f.type}"
            elif f.name == "coop_player_max_num":
                assert f.type is int, f"Expected int for {f.name}, got {f.type}"
            else:
                assert f.type is bool, f"Expected bool for {f.name}, got {f.type}"

    def test_custom_values(self):
        """Constructor args propagate correctly."""
        config = GameplayConfig(is_multiplay=False, is_pvp=True, coop_player_max_num=8)
        assert config.is_multiplay is False
        assert config.is_pvp is True
        assert config.coop_player_max_num == 8

    def test_asdict_roundtrip(self):
        """asdict round-trip preserves values."""
        config = GameplayConfig(enable_fast_travel=False, region="us")
        d = asdict(config)
        restored = GameplayConfig(**d)
        assert restored == config

    @pytest.mark.parametrize("field_name", [
        "enable_friendly_fire", "enable_non_login_penalty", "enable_fast_travel",
    ])
    def test_toggle_fields(self, field_name):
        """Boolean fields accept both True and False."""
        for val in [True, False]:
            config = GameplayConfig(**{field_name: val})
            assert getattr(config, field_name) is val

    @pytest.mark.parametrize("field_name", ["coop_player_max_num"])
    def test_integer_boundaries(self, field_name):
        """Integer fields accept boundary values."""
        for val in [0, 1, 100]:
            config = GameplayConfig(**{field_name: val})
            assert getattr(config, field_name) == val
