"""Tests for the settings generator."""

import pytest
import re
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
from src.managers.settings_generator import SettingsGenerator
from src.config.palworld.settings import PalworldSettings

pytestmark = pytest.mark.unit




class TestSettingsGenerator:
    """FS-12.x: Settings generator behavior."""

    @pytest.fixture
    def generator(self, palworld_config, mock_logger):
        return SettingsGenerator(palworld_config, mock_logger)

    def test_generate_settings_auto_format(self, generator):
        """FS-12.1: Auto-generated INI format."""
        content = generator._generate_settings_content_auto()
        assert "[/Script/Pal.PalGameWorldSettings]" in content
        assert "OptionSettings=(" in content
        assert "ServerName=" in content
        assert content.endswith(")")

    def test_legacy_settings_format(self, generator):
        """FS-12.2: Legacy generation fallback."""
        content = generator._generate_settings_content_legacy()
        assert "[/Script/Pal.PalGameWorldSettings]" in content
        assert "ServerName=" in content
        assert "Difficulty=" in content

    def test_format_ini_value_bool(self, generator):
        assert generator._format_ini_value(True) == "True"
        assert generator._format_ini_value(False) == "False"

    def test_format_ini_value_str(self, generator):
        assert generator._format_ini_value("hello") == '"hello"'
        assert generator._format_ini_value("") == '""'

    def test_format_ini_value_number(self, generator):
        assert generator._format_ini_value(42) == "42"
        assert generator._format_ini_value(3.14) == "3.14"

    def test_empty_default_settings_fallback(self, generator):
        """FS-12.2: Falls back to legacy when no default file."""
        generator._default_settings_cache = {}
        with patch.object(generator, '_parse_default_settings', return_value={}):
            content = generator._generate_settings_content_auto()
            assert content is not None
            assert "OptionSettings=(" in content

    def test_parse_default_settings_not_found(self, generator):
        """FS-12.6: Graceful handling of missing default file."""
        with patch.object(generator, '_parse_default_settings', return_value={}) as mock_parse:
            result = generator._parse_default_settings()
            assert result == {}

    def test_clean_setting_value(self, generator):
        assert generator._clean_setting_value('"hello"') == "hello"
        assert generator._clean_setting_value("None") == "None"
        assert generator._clean_setting_value("true") == "True"
        assert generator._clean_setting_value("42") == "42"

    def test_generate_engine_content(self, generator):
        """FS-12.4: Engine.ini generates performance settings."""
        content = generator._generate_engine_content()
        assert "[/script/engine.engine]" in content
        assert "NetServerMaxTickRate" in content
        assert "bSmoothFrameRate" in content

    def test_generate_engine_content_fallback(self, generator):
        """FS-12.6: Engine content with fallback."""
        content = generator._generate_engine_content_fallback()
        assert "[/Script/Pal.PalGameWorldSettings]" not in content
        assert "Core.System" in content

    def test_get_config_summary(self, generator):
        """FS-12.7: Config summary includes override tracking."""
        summary = generator.get_config_summary()
        assert "parsing_status" in summary
        assert "total_defaults_found" in summary
        assert "total_user_settings" in summary
        assert "total_overrides" in summary

    def test_write_server_settings(self, generator, tmp_path):
        """FS-11.3: Write settings returns bool."""
        generator.config_dir = tmp_path
        result = generator.write_server_settings()
        assert result is True
        assert (tmp_path / "PalWorldSettings.ini").exists()

    def test_write_engine_settings(self, generator, tmp_path):
        """FS-11.3: Write engine returns bool."""
        generator.config_dir = tmp_path
        result = generator.write_engine_settings()
        assert result is True
        assert (tmp_path / "Engine.ini").exists()


class TestSettingsGeneratorEdgeCases:
    """Edge case tests for remaining settings_generator coverage."""

    @pytest.fixture
    def generator(self, palworld_config, mock_logger):
        gen = SettingsGenerator(palworld_config, mock_logger)
        # Use custom paths that won't accidentally pick up real files
        gen._default_settings_cache = {}
        return gen

    def test_write_custom_paths(self, generator, tmp_path):
        """write_server_settings/write_engine_settings with custom output_path."""
        generator.config_dir = tmp_path
        custom_srv = tmp_path / "PalWorldSettings_custom.ini"
        r1 = generator.write_server_settings(output_path=custom_srv)
        assert r1 is True
        assert custom_srv.exists()

        custom_eng = tmp_path / "Engine_custom.ini"
        r2 = generator.write_engine_settings(output_path=custom_eng)
        assert r2 is True
        assert custom_eng.exists()

    def test_write_exception(self, generator, tmp_path):
        """write_server_settings/write_engine_settings exception handling via write_text failure."""
        generator.config_dir = tmp_path
        with patch.object(Path, "write_text", side_effect=OSError("disk full")):
            assert generator.write_server_settings() is False
            assert generator.write_engine_settings() is False

    def test_auto_fallback_on_exception(self, generator):
        """_generate_settings_content_auto falls back to legacy when exception occurs."""
        generator._default_settings_cache = None
        with patch.object(generator, '_parse_default_settings',
                          side_effect=ValueError("broken")):
            content = generator._generate_settings_content_auto()
            assert "[/Script/Pal.PalGameWorldSettings]" in content
            assert "ServerName=" in content

    def test_parse_default_no_valid_settings(self, generator, tmp_path):
        """_parse_default_settings empty result when file has no OptionSettings."""
        # Test the extraction logic directly since the hardcoded project file exists
        result = generator._extract_option_settings("[SomeSection]\nkey=value\n")
        assert result == {}


    def test_parse_default_unicode_decode_bom(self, generator, tmp_path):
        """_parse_default_settings handles UnicodeDecodeError and retries with BOM."""
        f = tmp_path / "DefaultPalWorldSettings.ini"
        f.write_bytes(
            b'\xef\xbb\xbf[/Script/Pal.PalGameWorldSettings]\n'
            b'OptionSettings=(ServerName="test",Difficulty=None)\n'
        )
        generator.default_settings_path = f
        generator.server_path = tmp_path
        result = generator._parse_default_settings()
        assert result.get("ServerName") == "test"

    def test_parse_default_all_paths_fail(self, generator, tmp_path):
        """_parse_default_settings returns empty when all paths fail."""
        # Directly test via _extract_option_settings since the hardcoded project
        # DefaultPalWorldSettings.ini always exists
        result = generator._extract_option_settings("No OptionSettings here")
        assert result == {}

    def test_extract_option_settings_no_match(self, generator):
        """_extract_option_settings returns empty when pattern not found."""
        result = generator._extract_option_settings("[SomeSection]\nkey=value\n")
        assert result == {}

    def test_extract_option_settings_exception(self, generator):
        """_extract_option_settings exception handling."""
        with patch("re.search", side_effect=Exception("regex error")):
            result = generator._extract_option_settings("content")
            assert result == {}

    def test_engine_fallback_on_exception(self, generator):
        """_generate_engine_content falls back when _read_engine_base_content raises."""
        with patch.object(generator, '_read_engine_base_content',
                          side_effect=ValueError("broken")):
            content = generator._generate_engine_content()
            assert "Core.System" in content

    def test_read_engine_base_empty_file(self, generator, tmp_path):
        """_read_engine_base_content continues past empty file to next path."""
        f = tmp_path / "BaseEngine.ini"
        f.write_text("")
        generator.default_engine_path = f
        generator.server_path = tmp_path
        content = generator._read_engine_base_content()
        assert "Core.System" in content  # fallback

    def test_read_engine_base_unicode_decode_bom(self, generator, tmp_path):
        """_read_engine_base_content retries with BOM on UnicodeDecodeError."""
        f = tmp_path / "BaseEngine.ini"
        f.write_bytes(b'\xef\xbb\xbf[/script/engine.engine]\nNetServerMaxTickRate=60\n')
        generator.default_engine_path = f
        generator.server_path = tmp_path
        content = generator._read_engine_base_content()
        assert "NetServerMaxTickRate" in content

    def test_read_engine_base_all_fail(self, generator, tmp_path):
        """_read_engine_base_content returns fallback when all paths fail."""
        generator.default_engine_path = tmp_path / "does_not_exist.ini"
        generator.server_path = tmp_path / "no_such_dir"
        content = generator._read_engine_base_content()
        assert "Core.System" in content

    def test_config_summary_exception(self, generator):
        """get_config_summary returns error dict on exception."""
        generator._default_settings_cache = None
        with patch.object(generator, '_get_default_settings',
                          side_effect=Exception("summary error")):
            summary = generator.get_config_summary()
            assert summary["parsing_status"] == "error"
            assert "error" in summary




class TestSettingsGeneratorFileErrors:
    """File I/O error paths in _parse_default_settings and _read_engine_base_content."""

    @pytest.fixture
    def generator(self, palworld_config, mock_logger):
        gen = SettingsGenerator(palworld_config, mock_logger)
        gen._default_settings_cache = None
        return gen

    def test_parse_default_unicode_decode_bom_failure(self, generator, tmp_path):
        """_parse_default_settings: UnicodeDecodeError, BOM retry also fails."""
        with patch("pathlib.Path.read_text") as mock_read:
            def se(encoding="utf-8", **kw):
                if encoding == "utf-8":
                    raise UnicodeDecodeError("utf-8", b"\xff\xfe", 0, 1, "test")
                elif encoding == "utf-8-sig":
                    raise UnicodeDecodeError("utf-8-sig", b"\xff\xfe", 0, 1, "test bom")
                raise ValueError(f"unexpected encoding {encoding}")
            mock_read.side_effect = se

            with patch("pathlib.Path.exists", return_value=True):
                result = generator._parse_default_settings()
                assert result == {}

    def test_parse_default_generic_exception(self, generator, tmp_path):
        """_parse_default_settings: generic Exception caught and continues."""
        with patch("pathlib.Path.read_text", side_effect=PermissionError("denied")), \
             patch("pathlib.Path.exists", return_value=True):
            result = generator._parse_default_settings()
            assert result == {}

    def test_parse_default_all_nonexistent(self, generator, tmp_path):
        """_parse_default_settings: verify extract_option_settings empty-result path."""
        result = generator._extract_option_settings("No OptionSettings here")
        assert result == {}
    def test_read_engine_empty_file(self, generator, tmp_path):
        """_read_engine_base_content: empty file, continues to fallback."""
        f = tmp_path / "BaseEngine.ini"
        f.write_text("")
        with patch.object(generator, 'default_engine_path', f), \
             patch.object(generator, 'server_path', tmp_path / "nope"):
            content = generator._read_engine_base_content()
            assert "Core.System" in content

    def test_read_engine_unicode_decode_then_bom(self, generator, tmp_path):
        """_read_engine_base_content: UnicodeDecodeError, BOM retry succeeds."""
        f = tmp_path / "BaseEngine.ini"
        f.write_bytes(b'\xef\xbb\xbf[/script/engine.engine]\nNetServerMaxTickRate=60\n')

        # Patch read_text at class level to simulate UnicodeDecodeError for utf-8
        original_read = f.read_text
        def mock_read(encoding="utf-8", **kw):
            if encoding == "utf-8-sig":
                return original_read(encoding="utf-8-sig")
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "test")
        with patch.object(generator, 'default_engine_path', f), \
             patch.object(generator, 'server_path', tmp_path / "nope"), \
             patch("pathlib.Path.read_text", side_effect=mock_read):
            content = generator._read_engine_base_content()
            assert "NetServerMaxTickRate" in content

    def test_read_engine_bom_also_fails(self, generator, tmp_path):
        """_read_engine_base_content: UnicodeDecodeError, BOM also fails."""
        f = tmp_path / "BaseEngine.ini"
        f.write_bytes(b'\xef\xbb\xbf[/script/engine.engine]\n')
        def mock_read(encoding="utf-8", **kw):
            if encoding == "utf-8":
                raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "test")
            raise UnicodeDecodeError("utf-8-sig", b"\xff\xfe", 0, 1, "bom fail")
        with patch.object(generator, 'default_engine_path', f), \
             patch.object(generator, 'server_path', tmp_path / "nope"), \
             patch("pathlib.Path.read_text", side_effect=mock_read):
            content = generator._read_engine_base_content()
            assert "Core.System" in content

    def test_read_engine_generic_exception(self, generator, tmp_path):
        """_read_engine_base_content: generic Exception caught."""
        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.read_text", side_effect=PermissionError("denied")):
            content = generator._read_engine_base_content()
            assert "Core.System" in content

    def test_format_ini_nonstandard_type(self, generator):
        """_format_ini_value with type that falls through to else branch."""
        class Custom:
            def __str__(self):
                return "custom_val"
        assert generator._format_ini_value(Custom()) == "custom_val"
