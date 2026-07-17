"""Tests for PalSettingsConfig dataclass."""

import pytest
from dataclasses import fields, asdict
from src.config.game.pal_settings import PalSettingsConfig

pytestmark = pytest.mark.unit


class TestPalSettingsConfig:
    """PalSettingsConfig dataclass unit tests."""

    EXPECTED_DEFAULTS = {
        "egg_default_hatching_time": 72.0,
        "work_speed_rate": 1.0,
        "day_time_speed_rate": 1.0,
        "night_time_speed_rate": 1.0,
        "exp_rate": 1.0,
        "pal_capture_rate": 1.0,
        "pal_spawn_num_rate": 1.0,
        "pal_damage_rate_attack": 1.0,
        "pal_damage_rate_defense": 1.0,
        "pal_stomach_decrease_rate": 1.0,
        "pal_stamina_decrease_rate": 1.0,
        "pal_auto_hp_regene_rate": 1.0,
        "pal_auto_hp_regene_rate_in_sleep": 1.0,
        "player_damage_rate_attack": 1.0,
        "player_damage_rate_defense": 1.0,
        "player_stomach_decrease_rate": 1.0,
        "player_stamina_decrease_rate": 1.0,
        "player_auto_hp_regene_rate": 1.0,
        "player_auto_hp_regene_rate_in_sleep": 1.0,
    }

    def test_default_values(self):
        """Default values match expectations."""
        config = PalSettingsConfig()
        for field_name, expected in self.EXPECTED_DEFAULTS.items():
            assert getattr(config, field_name) == expected, (
                f"Expected {field_name}={expected}, got {getattr(config, field_name)}"
            )

    def test_field_count(self):
        """Field count guards against drift."""
        assert len(fields(PalSettingsConfig)) == 19

    def test_type_hints(self):
        """All fields are float."""
        for f in fields(PalSettingsConfig):
            assert f.type is float, f"Expected float for {f.name}, got {f.type}"

    def test_custom_values(self):
        """Constructor args propagate correctly."""
        config = PalSettingsConfig(exp_rate=3.0, pal_capture_rate=2.5, egg_default_hatching_time=48.0)
        assert config.exp_rate == 3.0
        assert config.pal_capture_rate == 2.5
        assert config.egg_default_hatching_time == 48.0

    def test_asdict_roundtrip(self):
        """asdict round-trip preserves values."""
        config = PalSettingsConfig(work_speed_rate=2.0, pal_spawn_num_rate=3.0)
        d = asdict(config)
        restored = PalSettingsConfig(**d)
        assert restored == config

    @pytest.mark.parametrize("field_name", [
        "exp_rate", "pal_capture_rate", "pal_spawn_num_rate",
    ])
    def test_rate_boundaries(self, field_name):
        """Rate fields accept boundary values (zero, negative, very large)."""
        for val in [0.0, -1.0, 100.0]:
            config = PalSettingsConfig(**{field_name: val})
            assert getattr(config, field_name) == val

    def test_zero_hatching_time(self):
        """Egg hatching time accepts zero."""
        config = PalSettingsConfig(egg_default_hatching_time=0.0)
        assert config.egg_default_hatching_time == 0.0
