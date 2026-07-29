"""Tests for BuildingConfig dataclass."""

import pytest
from dataclasses import fields, asdict
from src.config.game.building import BuildingConfig

pytestmark = pytest.mark.unit


class TestBuildingConfig:
    """BuildingConfig dataclass unit tests."""

    def test_default_values(self):
        """Default values match expectations."""
        config = BuildingConfig()
        assert config.build_object_damage_rate == 1.0
        assert config.build_object_deterioration_damage_rate == 1.0
        assert config.collection_drop_rate == 1.0
        assert config.collection_object_hp_rate == 1.0
        assert config.collection_object_respawn_speed_rate == 1.0
        assert config.enemy_drop_item_rate == 1.0

    def test_field_count(self):
        """Field count guards against drift."""
        assert len(fields(BuildingConfig)) == 6

    def test_type_hints(self):
        """All fields are float."""
        for f in fields(BuildingConfig):
            assert f.type is float, f"Expected float for {f.name}, got {f.type}"

    def test_custom_values(self):
        """Constructor args propagate correctly."""
        config = BuildingConfig(build_object_damage_rate=2.5, collection_drop_rate=0.5)
        assert config.build_object_damage_rate == 2.5
        assert config.collection_drop_rate == 0.5

    def test_asdict_roundtrip(self):
        """asdict round-trip preserves values."""
        config = BuildingConfig(enemy_drop_item_rate=3.0)
        d = asdict(config)
        restored = BuildingConfig(**d)
        assert restored == config

    @pytest.mark.parametrize(
        "field_name",
        [
            "build_object_damage_rate",
            "build_object_deterioration_damage_rate",
            "collection_drop_rate",
            "enemy_drop_item_rate",
        ],
    )
    def test_boundary_values(self, field_name):
        """Accept boundary values (zero, negative, large)."""
        for val in [0.0, -1.0, 100.0]:
            config = BuildingConfig(**{field_name: val})
            assert getattr(config, field_name) == val
