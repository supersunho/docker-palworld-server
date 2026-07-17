"""Tests for DifficultyConfig dataclass."""

import pytest
from dataclasses import fields, asdict
from src.config.game.difficulty import DifficultyConfig

pytestmark = pytest.mark.unit


class TestDifficultyConfig:
    """DifficultyConfig dataclass unit tests."""

    def test_default_values(self):
        """Default values match expectations."""
        config = DifficultyConfig()
        assert config.level == "None"
        assert config.death_penalty == "All"

    def test_field_count(self):
        """Field count guards against drift."""
        assert len(fields(DifficultyConfig)) == 2

    def test_type_hints(self):
        """All fields are str."""
        for f in fields(DifficultyConfig):
            assert f.type is str, f"Expected str for {f.name}, got {f.type}"

    def test_custom_values(self):
        """Constructor args propagate correctly."""
        config = DifficultyConfig(level="Hard", death_penalty="Items")
        assert config.level == "Hard"
        assert config.death_penalty == "Items"

    def test_asdict_roundtrip(self):
        """asdict round-trip preserves values."""
        config = DifficultyConfig(level="Normal", death_penalty="None")
        d = asdict(config)
        restored = DifficultyConfig(**d)
        assert restored == config

    def test_empty_strings(self):
        """Accepts empty string values."""
        config = DifficultyConfig(level="", death_penalty="")
        assert config.level == ""
        assert config.death_penalty == ""
