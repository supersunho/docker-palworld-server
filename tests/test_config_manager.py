"""Tests for the config file manager (including hot-reload)."""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path
from src.managers.config_manager import ConfigManager

pytestmark = pytest.mark.unit


async def _noop():
    pass


class TestConfigManager:
    """FS-11.x: Config manager behavior."""

    @pytest.fixture
    def manager(self, palworld_config, mock_logger):
        return ConfigManager(palworld_config, mock_logger)

    def test_init_creates_default_generator(self, palworld_config, mock_logger):
        """FS-11.1: Default SettingsGenerator created when none provided."""
        mgr = ConfigManager(palworld_config, mock_logger)
        assert mgr.generator is not None

    def test_generate_server_settings_success(self, manager, tmp_path):
        """FS-11.1+11.2: Generates PalWorldSettings.ini."""
        manager.config_dir = tmp_path
        manager.generator.generate_server_settings = MagicMock(return_value="content")
        result = manager.generate_server_settings()
        assert result is True
        assert (tmp_path / "PalWorldSettings.ini").exists()
        assert (tmp_path / "PalWorldSettings.ini").read_text() == "content"

    def test_generate_server_settings_creates_dir(self, manager, tmp_path):
        """FS-11.2: Creates directory if missing."""
        config_dir = tmp_path / "new" / "dir"
        manager.config_dir = config_dir
        manager.generator.generate_server_settings = MagicMock(return_value="content")
        result = manager.generate_server_settings()
        assert result is True
        assert config_dir.exists()

    def test_generate_server_settings_failure(self, manager):
        """FS-11.3: Returns False on failure."""
        manager.generator.generate_server_settings = MagicMock(side_effect=Exception("fail"))
        result = manager.generate_server_settings()
        assert result is False

    def test_generate_engine_settings_success(self, manager, tmp_path):
        """FS-11.1: Generates Engine.ini."""
        manager.config_dir = tmp_path
        manager.generator.generate_engine_settings = MagicMock(return_value="engine")
        result = manager.generate_engine_settings()
        assert result is True
        assert (tmp_path / "Engine.ini").read_text() == "engine"

    def test_generate_engine_settings_failure(self, manager):
        """FS-11.3: Returns False on failure."""
        manager.generator.generate_engine_settings = MagicMock(side_effect=Exception("fail"))
        result = manager.generate_engine_settings()
        assert result is False

    # ---- Hot-reload tests ----

    def test_reload_and_apply_returns_false(self, manager):
        """FS-11.5: reload_and_apply returns False when validation fails."""
        with patch.object(manager, "_validate_config", side_effect=ValueError("bad config")):
            result = manager.reload_and_apply()
            assert result is False

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_watch_config_detects_change(self, manager, tmp_path):
        """FS-11.7: watch_config detects YAML changes and triggers callback."""
        # Make config path point to temp
        config_path = tmp_path / "config" / "default.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("initial: value\n")

        # Monkey-patch _check_yaml_changed to simulate change
        manager._check_yaml_changed = MagicMock(side_effect=[False, True])
        # Patch reload_and_apply to succeed without reading real config
        with patch.object(manager, "reload_and_apply", return_value=True):
            callback = AsyncMock()

            # Run watch for a limited time
            import asyncio

            task = asyncio.create_task(manager.watch_config(check_interval=0.1, on_change=callback))

            # Let it run a couple cycles
            await asyncio.sleep(0.3)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Callback should have been invoked when _check_yaml_changed returned True
            assert callback.called

    def test_is_watching_initially_false(self, manager):
        """FS-11.8: is_watching returns False initially."""
        assert manager.is_watching() is False

    @pytest.mark.asyncio
    async def test_start_stop_watching(self, manager):
        """FS-11.9: start_watching and stop_watching lifecycle."""
        with patch.object(manager, "watch_config", side_effect=_noop):
            await manager.start_watching()
            # Task was created and cancelled immediately
            await manager.stop_watching()

    @pytest.mark.asyncio
    async def test_start_watching_twice_warns(self, manager):
        """FS-11.10: Starting watcher twice logs warning."""
        with patch.object(manager, "watch_config", side_effect=_noop):
            await manager.start_watching()
            with patch.object(manager.logger, "warning") as mock_warn:
                await manager.start_watching()
                mock_warn.assert_called_once()
            await manager.stop_watching()

    # ---- Checksum / change-detection tests ----

    def test_compute_checksums_both_missing(self, manager, tmp_path):
        """FS-11.11: _compute_checksums returns empty strings when files missing."""
        manager.config_dir = tmp_path
        result = manager._compute_checksums()
        assert result["server_settings"] == ""
        assert result["engine_settings"] == ""

    def test_compute_checksums_with_files(self, manager, tmp_path):
        """FS-11.11: _compute_checksums returns valid SHA256 for existing files."""
        manager.config_dir = tmp_path
        (tmp_path / "PalWorldSettings.ini").write_text("Option=(Val=True)")
        (tmp_path / "Engine.ini").write_text("[Core]\nOptimization=1\n")
        result = manager._compute_checksums()
        assert len(result["server_settings"]) == 64  # SHA256 hexdigest
        assert len(result["engine_settings"]) == 64
        assert result["server_settings"] != result["engine_settings"]

    def test_update_checksum_stores_hash(self, manager):
        """FS-11.11: _update_checksum stores SHA256 hash by key."""
        manager._update_checksum("test_key", "some content")
        assert "test_key" in manager._checksums
        import hashlib

        expected = hashlib.sha256(b"some content").hexdigest()
        assert manager._checksums["test_key"] == expected

    def test_reload_and_apply_exception(self, manager):
        """FS-11.12: reload_and_apply returns False on generator exception."""
        with (
            patch("src.managers.config_manager.Path.exists", return_value=True),
            patch(
                "src.managers.config_manager.Path.read_text", return_value="server:\n  name: Test\n"
            ),
            patch("src.managers.config_manager.Path.resolve") as mock_resolve,
            patch("src.config.base.ConfigLoader") as mock_loader_cls,
            patch("src.managers.config_manager.SettingsGenerator") as mock_gen_cls,
        ):
            mock_resolve.return_value = Path("/tmp/test_config/default.yaml").resolve()
            mock_config = MagicMock()
            mock_config.server.name = "Test"
            mock_config.server.port = 8211
            mock_config.rest_api = MagicMock(enabled=True, port=8212)
            mock_config.rcon = MagicMock(enabled=True, port=25575)
            mock_config.backup = MagicMock(enabled=True)
            mock_loader_cls.return_value.load_config.return_value = mock_config

            mock_gen = MagicMock()
            mock_gen.generate_server_settings.side_effect = RuntimeError("unexpected")
            mock_gen_cls.return_value = mock_gen

            result = manager.reload_and_apply()
            assert result is False

    @pytest.mark.asyncio
    async def test_stop_watching_no_task(self, manager):
        """FS-11.13: stop_watching is a no-op when no task is running."""
        assert manager._watch_task is None
        await manager.stop_watching()  # should not raise

    def test_check_yaml_changed_not_found(self, manager):
        """FS-11.14: _check_yaml_changed returns False when config file missing."""
        with patch("src.managers.config_manager.Path.exists", return_value=False):
            assert manager._check_yaml_changed() is False

    def test_check_yaml_changed_first_call(self, manager, tmp_path):
        """FS-11.14: First call stores checksum and returns False."""
        config_path = tmp_path / "config" / "default.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("some: config\n")
        with (
            patch("src.managers.config_manager.Path.exists", return_value=True),
            patch("src.managers.config_manager.Path.read_text", return_value="some: config\n"),
        ):
            assert manager._check_yaml_changed() is False
            assert "yaml_config" in manager._checksums

    def test_check_yaml_changed_detects_change(self, manager):
        """FS-11.14: Returns True when content differs from stored checksum."""
        import hashlib

        old_hash = hashlib.sha256(b"old content").hexdigest()
        new_hash = hashlib.sha256(b"new content").hexdigest()
        manager._checksums["yaml_config"] = old_hash
        with (
            patch("src.managers.config_manager.Path.exists", return_value=True),
            patch("src.managers.config_manager.Path.read_text", return_value="new content"),
        ):
            assert manager._check_yaml_changed() is True
            assert manager._checksums["yaml_config"] == new_hash

    def test_check_yaml_changed_no_change(self, manager):
        """FS-11.14: Returns False when content matches stored checksum."""
        import hashlib

        content = "same content"
        h = hashlib.sha256(content.encode("utf-8")).hexdigest()
        manager._checksums["yaml_config"] = h
        with (
            patch("src.managers.config_manager.Path.exists", return_value=True),
            patch("src.managers.config_manager.Path.read_text", return_value=content),
        ):
            assert manager._check_yaml_changed() is False

    def test_check_yaml_changed_read_error(self, manager):
        """FS-11.14: Returns False on read error."""
        manager._checksums["yaml_config"] = "old_hash"
        with (
            patch("src.managers.config_manager.Path.exists", return_value=True),
            patch(
                "src.managers.config_manager.Path.read_text", side_effect=PermissionError("denied")
            ),
        ):
            assert manager._check_yaml_changed() is False
            # checksum should NOT be updated on error
            assert manager._checksums["yaml_config"] == "old_hash"

    def test_check_yaml_changed_no_config(self, manager):
        """FS-11.7: _check_yaml_changed returns False when no config file."""
        # Temporarily clear config_dir to trigger missing path
        result = manager._check_yaml_changed()
        assert result is False

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_watch_config_stop_via_cancel(self, manager):
        """FS-11.10: watch_config stops when task is cancelled."""
        # watch_config catches CancelledError internally and breaks the loop
        task = asyncio.create_task(manager.watch_config())
        await asyncio.sleep(0.1)  # Let one polling tick run
        # Cancel the task — watch_config handles CancelledError and exits
        task.cancel()
        await task  # Should complete normally (CancelledError swallowed)
