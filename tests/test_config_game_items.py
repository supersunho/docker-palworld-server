"""Tests for ItemsConfig dataclass."""

import pytest
from dataclasses import fields, asdict
from src.config.game.items import ItemsConfig

pytestmark = pytest.mark.unit


class TestItemsConfig:
    """ItemsConfig dataclass unit tests."""

    def test_default_values(self):
        """Default values match expectations."""
        config = ItemsConfig()
        assert config.drop_item_max_num == 3000
        assert config.drop_item_max_num_unko == 100
        assert config.drop_item_alive_max_hours == 1.0

    def test_field_count(self):
        """Field count guards against drift."""
        assert len(fields(ItemsConfig)) == 3

    def test_type_hints(self):
        """Type hints match expected types."""
        for f in fields(ItemsConfig):
            if f.name == "drop_item_alive_max_hours":
                assert f.type is float, f"Expected float for {f.name}, got {f.type}"
            else:
                assert f.type is int, f"Expected int for {f.name}, got {f.type}"

    def test_custom_values(self):
        """Constructor args propagate correctly."""
        config = ItemsConfig(drop_item_max_num=5000, drop_item_alive_max_hours=2.0)
        assert config.drop_item_max_num == 5000
        assert config.drop_item_alive_max_hours == 2.0

    def test_asdict_roundtrip(self):
        """asdict round-trip preserves values."""
        config = ItemsConfig(drop_item_max_num=100, drop_item_max_num_unko=50)
        d = asdict(config)
        restored = ItemsConfig(**d)
        assert restored == config

    @pytest.mark.parametrize("field_name", ["drop_item_max_num", "drop_item_max_num_unko"])
    def test_integer_boundaries(self, field_name):
        """Integer fields accept boundary values."""
        for val in [0, 1, 99999]:
            config = ItemsConfig(**{field_name: val})
            assert getattr(config, field_name) == val

    @pytest.mark.parametrize("field_name", ["drop_item_alive_max_hours"])
    def test_float_boundaries(self, field_name):
        """Float fields accept boundary values."""
        for val in [0.0, -1.0, 8760.0]:
            config = ItemsConfig(**{field_name: val})
            assert getattr(config, field_name) == val
