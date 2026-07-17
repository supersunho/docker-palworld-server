"""Regression tests for environment-backed Palworld INI settings."""

from dataclasses import fields
import os
from pathlib import Path
import re
from unittest.mock import patch

from src.config.base import ConfigLoader
from src.managers.settings_generator import SettingsGenerator
import pytest

pytestmark = pytest.mark.unit


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SETTINGS = ROOT / "config" / "DefaultPalWorldSettings.ini"
DEFAULT_YAML = ROOT / "config" / "default.yaml"
ENV_EXAMPLE = ROOT / ".env.palworld.example"


def _example_environment_keys() -> set[str]:
    """Return variable names declared by the Palworld example env file."""
    return {
        match.group(1)
        for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        if (match := re.match(r"^([A-Z][A-Z0-9_]*)=", line))
    }


def _palworld_ini_keys() -> set[str]:
    """Extract every key from the OptionSettings tuple in the sample INI."""
    content = DEFAULT_SETTINGS.read_text(encoding="utf-8")
    option_settings = re.search(r"OptionSettings=\((.*)\)", content, re.DOTALL)
    assert option_settings, "DefaultPalWorldSettings.ini has no OptionSettings tuple"
    return {
        match.group(1)
        for match in re.finditer(r"(?:^|,)([A-Za-z][A-Za-z0-9_]*)=", option_settings.group(1))
    }


def _yaml_section_lines(section: str) -> list[str]:
    """Return lines belonging to a top-level YAML section."""
    content = DEFAULT_YAML.read_text(encoding="utf-8")
    section_start = content.index(f"{section}:\n") + len(f"{section}:\n")
    remainder = content[section_start:]
    section_end = re.search(r"^[^ \n][^\n]*:\n", remainder, re.MULTILINE)
    if section_end:
        remainder = remainder[: section_end.start()]
    return remainder.splitlines()


def _palworld_environment_mappings() -> dict[str, str]:
    """Map each Palworld INI key to its environment variable."""
    mappings = {}
    for line in _yaml_section_lines("palworld_settings"):
        match = re.search(
            r"^\s{4}([A-Za-z][A-Za-z0-9_]*)\s*:.*\$\{([A-Z][A-Z0-9_]*)",
            line,
        )
        if match:
            mappings[match.group(1)] = match.group(2)
    return mappings


def _engine_environment_mappings() -> dict[str, str]:
    """Map each EngineConfig field to its environment variable."""
    mappings = {}
    for line in _yaml_section_lines("engine"):
        match = re.search(
            r"^\s{4}([a-z][a-z0-9_]*)\s*:.*\$\{([A-Z][A-Z0-9_]*)",
            line,
        )
        if match:
            mappings[match.group(1)] = match.group(2)
    return mappings


def _override_for_type(field_type: type) -> str:
    """Return a YAML-safe value that is easy to identify in generated INI."""
    if field_type is bool:
        return "false"
    if field_type is int:
        return "7"
    if field_type is float:
        return "2.5"
    return "environment-override"


def _expected_override(field_type: type):
    """Return the Python value produced by ConfigLoader for an override."""
    if field_type is bool:
        return False
    if field_type is int:
        return 7
    if field_type is float:
        return 2.5
    return "environment-override"


def test_all_palworld_ini_settings_have_environment_mappings():
    """Every sample Palworld setting must be env-backed and in the example."""
    mappings = _palworld_environment_mappings()
    assert _palworld_ini_keys() == set(mappings)
    assert set(mappings.values()) <= _example_environment_keys()


def test_all_engine_settings_have_environment_mappings():
    """Every generated Engine.ini performance setting must be env-backed."""
    mappings = _engine_environment_mappings()
    assert len(mappings) == 13
    assert set(mappings.values()) <= _example_environment_keys()


def test_example_steamcmd_app_id_is_consumed():
    """The example's SteamCMD app ID must not be silently ignored."""
    assert "${STEAMCMD_APP_ID:" in DEFAULT_YAML.read_text(encoding="utf-8")


def test_environment_overrides_reach_generated_ini(palworld_config, mock_logger):
    """Environment overrides reach both generated INI files end to end."""
    palworld_fields = {field.name: field for field in fields(palworld_config.palworld_settings)}
    engine_fields = {field.name: field for field in fields(palworld_config.engine)}
    palworld_mappings = _palworld_environment_mappings()
    engine_mappings = _engine_environment_mappings()

    overrides = {
        env_name: _override_for_type(palworld_fields[ini_key].type)
        for ini_key, env_name in palworld_mappings.items()
    }
    overrides.update(
        {
            env_name: _override_for_type(engine_fields[field_name].type)
            for field_name, env_name in engine_mappings.items()
        }
    )

    with patch.dict(os.environ, overrides, clear=False):
        config = ConfigLoader(DEFAULT_YAML).load_config()

    for ini_key, env_name in palworld_mappings.items():
        field_type = palworld_fields[ini_key].type
        assert getattr(config.palworld_settings, ini_key) == _expected_override(field_type), ini_key

    for field_name, env_name in engine_mappings.items():
        field_type = engine_fields[field_name].type
        assert getattr(config.engine, field_name) == _expected_override(field_type), field_name

    generator = SettingsGenerator(config, mock_logger)
    settings_content = generator.generate_server_settings()
    engine_content = generator.generate_engine_settings()

    for ini_key in palworld_mappings:
        assert f"{ini_key}=" in settings_content

    engine_ini_names = {
        "lan_server_max_tick_rate": "LanServerMaxTickRate",
        "net_server_max_tick_rate": "NetServerMaxTickRate",
        "configured_internet_speed": "ConfiguredInternetSpeed",
        "configured_lan_speed": "ConfiguredLanSpeed",
        "max_client_rate": "MaxClientRate",
        "max_internet_client_rate": "MaxInternetClientRate",
        "smooth_frame_rate": "bSmoothFrameRate",
        "use_fixed_frame_rate": "bUseFixedFrameRate",
        "min_desired_frame_rate": "MinDesiredFrameRate",
        "fixed_frame_rate": "FixedFrameRate",
        "net_client_ticks_per_second": "NetClientTicksPerSecond",
        "frame_rate_lower_bound": "SmoothedFrameRateRange",
        "frame_rate_upper_bound": "SmoothedFrameRateRange",
    }
    for field_name in engine_mappings:
        assert f"{engine_ini_names[field_name]}=" in engine_content or (
            engine_ini_names[field_name] == "SmoothedFrameRateRange"
            and "SmoothedFrameRateRange=" in engine_content
        )
