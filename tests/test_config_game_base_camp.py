"""Tests for BaseCampConfig dataclass."""

import pytest
from dataclasses import fields, asdict
from src.config.game.base_camp import BaseCampConfig

pytestmark = pytest.mark.unit


class TestBaseCampConfig:
    """BaseCampConfig dataclass unit tests."""

    def test_default_values(self):
        """Default values match expectations."""
        config = BaseCampConfig()
        assert config.max_num == 128
        assert config.worker_max_num == 15

    def test_field_count(self):
        """Field count guards against drift."""
        assert len(fields(BaseCampConfig)) == 2

    def test_type_hints(self):
        """All fields are int."""
        for f in fields(BaseCampConfig):
            assert f.type is int, f"Expected int for {f.name}, got {f.type}"

    def test_custom_values(self):
        """Constructor args propagate correctly."""
        config = BaseCampConfig(max_num=64, worker_max_num=10)
        assert config.max_num == 64
        assert config.worker_max_num == 10

    def test_asdict_roundtrip(self):
        """asdict round-trip preserves values."""
        config = BaseCampConfig(max_num=32, worker_max_num=8)
        d = asdict(config)
        restored = BaseCampConfig(**d)
        assert restored == config

    @pytest.mark.parametrize("field_name", ["max_num", "worker_max_num"])
    def test_boundary_values(self, field_name):
        """Accept boundary values (zero, one, large)."""
        for val in [0, 1, 999999]:
            config = BaseCampConfig(**{field_name: val})
            assert getattr(config, field_name) == val
