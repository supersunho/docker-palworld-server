"""Integration tests for the main server manager."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from src.server_manager import PalworldServerManager, wait_for_api_ready
from src.container import ServiceContainer
from src.managers.lifecycle_manager import ServerLifecycleManager
from src.managers.api_facade import ServerAPIFacade
from src.managers.settings_generator import SettingsGenerator
from src.managers.process_manager import ProcessManager

pytestmark = pytest.mark.unit


class TestPalworldServerManager:
    """FS-13.x: Server manager behavior."""

    @pytest.fixture
    def manager(self, palworld_config):
        container = ServiceContainer()

        # Register a mock ProcessManager so the container resolves it
        # instead of creating a real one.
        mock_pm = MagicMock(spec=ProcessManager)
        mock_pm.is_server_running = MagicMock(return_value=True)
        mock_pm.stop_server = AsyncMock(return_value=True)
        mock_pm.start_server = AsyncMock(return_value=True)
        mock_pm.get_server_status = MagicMock(
            return_value={"running": True, "pid": 12345, "uptime": 3600}
        )
        container.register(ProcessManager, mock_pm)

        lifecycle = MagicMock(spec=ServerLifecycleManager)
        lifecycle.start = AsyncMock(return_value=True)
        lifecycle.verify_startup = AsyncMock(return_value=True)
        lifecycle.get_server_status = MagicMock(
            return_value={"running": True, "pid": 12345, "uptime": 3600}
        )
        container.register(ServerLifecycleManager, lifecycle)

        api_facade = MagicMock(spec=ServerAPIFacade)
        api_facade.initialize_clients = AsyncMock()
        api_facade.cleanup_clients = AsyncMock()
        api_facade.get_api_client = MagicMock(return_value=MagicMock())
        api_facade.get_server_info = AsyncMock(return_value=MagicMock())
        api_facade.get_players = AsyncMock(return_value=[])
        api_facade.announce = AsyncMock(return_value=True)
        api_facade.save_world = AsyncMock(return_value=True)
        api_facade.api_get_server_metrics = AsyncMock(return_value={"cpu": 45})
        container.register(ServerAPIFacade, api_facade)

        settings_gen = MagicMock(spec=SettingsGenerator)
        settings_gen.generate_server_settings = MagicMock(return_value="content")
        settings_gen.write_server_settings = MagicMock(return_value=True)
        settings_gen.generate_engine_settings = MagicMock(return_value="engine")
        settings_gen.write_engine_settings = MagicMock(return_value=True)
        container.register(SettingsGenerator, settings_gen)

        m = PalworldServerManager(config=palworld_config, container=container)

        # Mock monitoring manager
        m.monitoring_manager = MagicMock()
        m.monitoring_manager.start_monitoring = AsyncMock()
        m.monitoring_manager.stop_monitoring = AsyncMock()
        m.monitoring_manager.handle_error = AsyncMock()
        m.monitoring_manager.get_monitoring_status = MagicMock(
            return_value={"monitoring_active": True, "player_count": 0}
        )

        # Mock steamcmd
        m.steamcmd_manager = MagicMock()
        m.steamcmd_manager.run_command = AsyncMock(return_value=(True, []))

        return m

    @pytest.mark.asyncio
    async def test_server_startup_success(self, manager):
        """FS-13.1.4: Full startup succeeds (wait_for_api_ready mocked)."""
        mock_readiness = AsyncMock(return_value=True)
        with patch("src.server_manager.wait_for_api_ready", new=mock_readiness):
            result = await manager.start_server_with_verification()
        assert result is True
        assert manager._startup_completed is True
        mock_readiness.assert_awaited_once_with(manager, max_wait_time=60, check_interval=2)

    @pytest.mark.asyncio
    async def test_server_startup_rest_api_disabled(self, manager):
        """FS-13.1.4: REST API disabled skips readiness check."""
        manager.config.rest_api.enabled = False
        mock_readiness = AsyncMock(return_value=True)
        with patch("src.server_manager.wait_for_api_ready", new=mock_readiness):
            result = await manager.start_server_with_verification()
        assert result is True
        assert manager._startup_completed is True
        mock_readiness.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_server_startup_lifecycle_fails(self, manager):
        """FS-13.1.4: Startup fails when lifecycle fails."""
        manager.lifecycle_manager.start = AsyncMock(return_value=False)
        result = await manager.start_server_with_verification()
        assert result is False
        assert manager._startup_completed is False

    @pytest.mark.asyncio
    async def test_server_startup_stability_fails(self, manager):
        """FS-13.1.4: Startup fails when verify fails."""
        manager.lifecycle_manager.verify_startup = AsyncMock(return_value=False)
        result = await manager.start_server_with_verification()
        assert result is False

    def test_is_server_running(self, manager):
        """FS-13: Running status."""
        assert manager.is_server_running() is True

    @pytest.mark.asyncio
    async def test_start_server_delegates(self, manager):
        """FS-13.1.4: Start delegates."""
        result = await manager.start_server()
        assert result is True

    @pytest.mark.asyncio
    async def test_stop_server(self, manager):
        """FS-13.3.1: Stop delegates."""
        result = await manager.stop_server()
        assert result is True

    def test_generate_server_settings(self, manager):
        """FS-13.1.3: Settings generation."""
        assert manager.generate_server_settings() is True

    def test_generate_engine_settings(self, manager):
        """FS-13.1.3: Engine settings."""
        assert manager.generate_engine_settings() is True

    def test_get_overall_status(self, manager):
        """FS-13.4: Comprehensive status."""
        status = manager.get_overall_status()
        assert "server" in status
        assert "monitoring" in status
        assert "startup_completed" in status
        assert "backup_enabled" in status

    def test_is_startup_completed(self, manager):
        """FS-13.4: Startup state."""
        assert manager.is_startup_completed() is False
        manager._startup_completed = True
        assert manager.is_startup_completed() is True

    def test_get_api_manager(self, manager):
        """FS-13.4: Accessor returns facade."""
        api = manager.get_api_manager()
        assert api is manager.api_facade

    def test_get_process_manager(self, manager):
        """FS-13.4: Process manager accessor."""
        pm = manager.get_process_manager()
        assert pm is manager.process_manager

    @pytest.mark.asyncio
    async def test_api_get_players(self, manager):
        """FS-13.4: API delegation methods."""
        result = await manager.api_get_players()
        manager.api_facade.get_players.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_server_files(self, manager):
        """FS-13.1.2: SteamCMD download."""
        result = await manager.download_server_files()
        assert result == (True, True)


class TestWaitForApiReady:
    """FS-13.1.5: API readiness check."""

    def _make_async_context_manager(self, mock_obj):
        """Create an async context manager wrapper."""
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_obj)
        cm.__aexit__ = AsyncMock(return_value=None)
        return cm

    @pytest.mark.asyncio
    async def test_api_ready_returns_true(self):
        """FS-13.1.5: Returns True when API responds 200."""
        mock_response = MagicMock()
        mock_response.status = 200

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=self._make_async_context_manager(mock_response))

        manager = MagicMock()
        manager.config.rest_api.host = "localhost"
        manager.config.rest_api.port = 8212
        manager.config.server.admin_password = "admin"

        with patch("aiohttp.ClientSession") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await wait_for_api_ready(manager, max_wait_time=1, check_interval=1)
            assert result is True

    @pytest.mark.asyncio
    async def test_api_unauthorized_still_ready(self):
        """FS-13.1.5: 401 means API is ready."""
        mock_response = MagicMock()
        mock_response.status = 401

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=self._make_async_context_manager(mock_response))

        manager = MagicMock()
        manager.config.rest_api.host = "localhost"
        manager.config.rest_api.port = 8212
        manager.config.server.admin_password = "admin"

        with patch("aiohttp.ClientSession") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await wait_for_api_ready(manager, max_wait_time=1, check_interval=1)
            assert result is True

    @pytest.mark.asyncio
    async def test_api_timeout_returns_false(self):
        """FS-13.1.5: Returns False when API never responds."""
        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=ConnectionError("refused"))

        manager = MagicMock()
        manager.config.rest_api.host = "localhost"
        manager.config.rest_api.port = 8212
        manager.config.server.admin_password = "admin"

        with patch("aiohttp.ClientSession") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await wait_for_api_ready(manager, max_wait_time=1, check_interval=1)
            assert result is False


class TestSteamcmdRecoveryTransaction:
    """REC-02..05: transactional metadata recovery for the exact 0x6 state."""

    @pytest.fixture
    def recovery_manager(self, palworld_config, tmp_path):
        """Manager bound to a real temporary server_dir.

        Mirrors TestPalworldServerManager.manager but replaces the magic
        config.paths with a real Path so recovery moves hit the filesystem.
        """
        config = palworld_config
        config.paths = MagicMock(
            server_dir=tmp_path,
            backup_dir=tmp_path / "backups",
            log_dir=tmp_path / "logs",
            steamcmd_dir=tmp_path / "steamcmd",
        )
        container = ServiceContainer()
        lifecycle = MagicMock(spec=ServerLifecycleManager)
        lifecycle.start = AsyncMock(return_value=True)
        lifecycle.verify_startup = AsyncMock(return_value=True)
        lifecycle.get_server_status = MagicMock(
            return_value={"running": True, "pid": 12345, "uptime": 3600}
        )
        container.register(ServerLifecycleManager, lifecycle)
        mock_pm = MagicMock(spec=ProcessManager)
        mock_pm.is_server_running = MagicMock(return_value=True)
        mock_pm.stop_server = AsyncMock(return_value=True)
        mock_pm.start_server = AsyncMock(return_value=True)
        container.register(ProcessManager, mock_pm)
        api_facade = MagicMock(spec=ServerAPIFacade)
        api_facade.initialize_clients = AsyncMock()
        api_facade.cleanup_clients = AsyncMock()
        api_facade.get_server_info = AsyncMock(return_value=MagicMock())
        api_facade.get_players = AsyncMock(return_value=[])
        container.register(ServerAPIFacade, api_facade)
        settings_gen = MagicMock(spec=SettingsGenerator)
        settings_gen.generate_server_settings = MagicMock(return_value="content")
        settings_gen.write_server_settings = MagicMock(return_value=True)
        settings_gen.generate_engine_settings = MagicMock(return_value="engine")
        settings_gen.write_engine_settings = MagicMock(return_value=True)
        container.register(SettingsGenerator, settings_gen)

        m = PalworldServerManager(config=config, container=container)
        m.monitoring_manager = MagicMock()
        m.monitoring_manager.start_monitoring = AsyncMock()
        m.monitoring_manager.stop_monitoring = AsyncMock()
        m.monitoring_manager.handle_error = AsyncMock()
        m.monitoring_manager.get_monitoring_status = MagicMock(
            return_value={"monitoring_active": True, "player_count": 0}
        )
        m.steamcmd_manager = MagicMock()
        m.steamcmd_manager.run_command = AsyncMock(return_value=(True, []))
        return m

    def _marker(self, app_id: int) -> str:
        return f"App '{app_id}' state is 0x6 after update job."

    def _make_targets(self, server_dir, app_id: int, which=("manifest", "downloading", "temp")):
        created = {}
        manifest = server_dir / "steamapps" / f"appmanifest_{app_id}.acf"
        downloading = server_dir / "steamapps" / "downloading" / str(app_id)
        temp = server_dir / "steamapps" / "temp" / str(app_id)
        if "manifest" in which:
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_bytes(b"manifest-bytes")
            created["manifest"] = manifest
        if "downloading" in which:
            downloading.mkdir(parents=True, exist_ok=True)
            (downloading / "chunk.bin").write_bytes(b"downloading-bytes")
            created["downloading"] = downloading
        if "temp" in which:
            temp.mkdir(parents=True, exist_ok=True)
            (temp / "tmp.bin").write_bytes(b"temp-bytes")
            created["temp"] = temp
        return created

    def test_recovery_moves_only_present_targets_and_preserves_bytes(self, recovery_manager, tmp_path):
        """REC-02: move only the three allowed targets, preserve relative paths
        and file bytes, retain the snapshot, never delete originals' content."""
        m = recovery_manager
        app = m.config.steamcmd.app_id
        created = self._make_targets(tmp_path, app, which=("manifest", "downloading"))

        ok, snapshot, moved, reason = m._recover_steamcmd_metadata()

        assert ok is True
        assert reason is None
        assert snapshot is not None
        assert snapshot.parent == tmp_path / ".steamcmd-recovery"
        assert snapshot.name.startswith(f"app-{app}-")
        # Only the two present targets moved; temp was never created/moved.
        assert set(moved) == {created["manifest"], created["downloading"]}
        assert not created["manifest"].exists()
        assert not created["downloading"].exists()
        assert not (tmp_path / "steamapps" / "temp").exists()
        # Relative paths preserved under the snapshot; bytes intact.
        assert (snapshot / f"steamapps/appmanifest_{app}.acf").read_bytes() == b"manifest-bytes"
        assert (
            snapshot / f"steamapps/downloading/{app}/chunk.bin"
        ).read_bytes() == b"downloading-bytes"
        # No orphaned auto-deletion: snapshot still on disk.
        assert snapshot.exists()

    def test_recovery_no_targets_is_trivial_success(self, recovery_manager, tmp_path):
        """REC-02: no matching metadata present -> no snapshot, ok."""
        m = recovery_manager
        ok, snapshot, moved, reason = m._recover_steamcmd_metadata()
        assert ok is True
        assert snapshot is None
        assert moved == []
        assert reason is None

    def test_recovery_rejects_symlinked_target(self, recovery_manager, tmp_path):
        """REC-03: symlinked target is rejected; nothing moved."""
        m = recovery_manager
        app = m.config.steamcmd.app_id
        manifest = tmp_path / "steamapps" / f"appmanifest_{app}.acf"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        victim = tmp_path / "victim.acf"
        victim.write_bytes(b"outside")
        manifest.symlink_to(victim)

        ok, snapshot, moved, reason = m._recover_steamcmd_metadata()
        assert ok is False
        assert "symlink" in (reason or "")
        assert snapshot is None
        assert moved == []
        assert manifest.is_symlink()

    def test_recovery_rejects_symlinked_parent(self, recovery_manager, tmp_path):
        """REC-03: a symlinked ancestor (steamapps) is rejected."""
        m = recovery_manager
        app = m.config.steamcmd.app_id
        real = tmp_path / "real-steamapps"
        real.mkdir()
        (real / f"appmanifest_{app}.acf").write_bytes(b"manifest-bytes")
        (tmp_path / "steamapps").symlink_to(real, target_is_directory=True)

        ok, snapshot, moved, reason = m._recover_steamcmd_metadata()
        assert ok is False
        assert "symlink" in (reason or "")
        assert snapshot is None

    def test_recovery_rolls_back_on_mid_transaction_failure(
        self, recovery_manager, tmp_path, monkeypatch
    ):
        """REC-03: move failure rolls back already-moved entries in reverse."""
        m = recovery_manager
        app = m.config.steamcmd.app_id
        created = self._make_targets(tmp_path, app, which=("manifest", "downloading", "temp"))

        real_rename = Path.rename
        failed = False

        def flaky_rename(self_obj, target):
            nonlocal failed
            if not failed and self_obj == created["downloading"]:
                failed = True
                raise OSError("simulated move failure")
            return real_rename(self_obj, target)

        monkeypatch.setattr(Path, "rename", flaky_rename)

        ok, snapshot, moved, reason = m._recover_steamcmd_metadata()
        assert ok is False
        assert moved == [created["manifest"]]
        assert "simulated move failure" in (reason or "")
        # Manifest rolled back to its exact original location.
        assert created["manifest"].read_bytes() == b"manifest-bytes"
        # Downloading never moved; temp untouched.
        assert (created["downloading"] / "chunk.bin").read_bytes() == b"downloading-bytes"
        assert (created["temp"] / "tmp.bin").read_bytes() == b"temp-bytes"

    @pytest.mark.asyncio
    async def test_0x6_recovery_retries_identical_command_exactly_once(
        self, recovery_manager, tmp_path
    ):
        """REC-01/04: 0x6 failure -> recovery -> exactly one identical retry,
        retry result returned."""
        m = recovery_manager
        app = m.config.steamcmd.app_id
        self._make_targets(tmp_path, app, which=("manifest",))
        marker = self._marker(app)

        m.steamcmd_manager.run_command = AsyncMock(
            side_effect=[(False, [marker]), (True, ["Success! App '2394010' fully installed."])]
        )
        success, was_updated = await m.download_server_files()

        assert success is True
        assert was_updated is True
        calls = m.steamcmd_manager.run_command.await_args_list
        assert len(calls) == 2
        # Identical command construction on both invocations.
        assert calls[0].args[0] == calls[1].args[0]
        assert calls[0].args[0] == [
            "+force_install_dir",
            str(tmp_path),
            "+login",
            "anonymous",
            "+app_update",
            str(app),
            "validate",
            "+quit",
        ]
        # Snapshot retained.
        snapshots = list((tmp_path / ".steamcmd-recovery").glob(f"app-{app}-*"))
        assert len(snapshots) == 1

    @pytest.mark.asyncio
    async def test_0x6_recovery_retry_up_to_date_reports_not_updated(
        self, recovery_manager, tmp_path
    ):
        """REC-04: retry that reports 'already up to date' -> was_updated False."""
        m = recovery_manager
        app = m.config.steamcmd.app_id
        self._make_targets(tmp_path, app, which=("downloading",))
        marker = self._marker(app)

        m.steamcmd_manager.run_command = AsyncMock(
            side_effect=[
                (False, [marker]),
                (True, ["Success. App '2394010' already up to date."]),
            ]
        )
        success, was_updated = await m.download_server_files()
        assert success is True
        assert was_updated is False
        assert len(m.steamcmd_manager.run_command.await_args_list) == 2

    @pytest.mark.asyncio
    async def test_non_0x6_failure_no_recovery_no_retry(self, recovery_manager):
        """REC-01: unrelated failure keeps prior behavior -- no recovery, one run."""
        m = recovery_manager
        m.steamcmd_manager.run_command = AsyncMock(
            return_value=(False, ["Download failed: disk full", "ERROR! Failed to install app '2394010'."])
        )
        success, was_updated = await m.download_server_files()
        assert success is False
        assert was_updated is False
        assert len(m.steamcmd_manager.run_command.await_args_list) == 1
        m.monitoring_manager.handle_error.assert_awaited_once_with(
            "Server file download failed"
        )

    @pytest.mark.asyncio
    async def test_0x6_wrong_app_id_no_recovery(self, recovery_manager):
        """REC-01: same state marker but another app id is not recoverable."""
        m = recovery_manager
        m.steamcmd_manager.run_command = AsyncMock(
            return_value=(False, ["App '9999999' state is 0x6 after update job."])
        )
        success, was_updated = await m.download_server_files()
        assert success is False
        assert was_updated is False
        assert len(m.steamcmd_manager.run_command.await_args_list) == 1

    @pytest.mark.asyncio
    async def test_0x6_recovery_rollback_never_retries(self, recovery_manager, tmp_path, monkeypatch):
        """REC-03: incomplete transaction -> no retry even for 0x6."""
        m = recovery_manager
        app = m.config.steamcmd.app_id
        self._make_targets(tmp_path, app, which=("manifest", "downloading"))
        marker = self._marker(app)

        real_rename = Path.rename
        failed = False

        def flaky_rename(self_obj, target):
            nonlocal failed
            if not failed and self_obj == tmp_path / "steamapps" / "downloading" / str(app):
                failed = True
                raise OSError("simulated move failure")
            return real_rename(self_obj, target)

        monkeypatch.setattr(Path, "rename", flaky_rename)
        m.steamcmd_manager.run_command = AsyncMock(return_value=(False, [marker]))

        success, was_updated = await m.download_server_files()
        assert success is False
        assert was_updated is False
        # Exactly one run: the failed initial command, never a retry.
        assert len(m.steamcmd_manager.run_command.await_args_list) == 1
        m.monitoring_manager.handle_error.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_force_update_does_not_change_command_or_recovery(
        self, recovery_manager, tmp_path
    ):
        """REC-04: identical behavior whether or not FORCE_UPDATE is enabled."""
        m = recovery_manager
        app = m.config.steamcmd.app_id
        self._make_targets(tmp_path, app, which=("manifest",))
        marker = self._marker(app)
        m.config.steamcmd.force_update = True

        m.steamcmd_manager.run_command = AsyncMock(
            side_effect=[(False, [marker]), (True, ["Success! App '2394010' fully installed."])]
        )
        success, was_updated = await m.download_server_files()
        assert success is True
        calls = m.steamcmd_manager.run_command.await_args_list
        assert len(calls) == 2
        assert calls[0].args[0] == calls[1].args[0]
        assert "validate" in calls[0].args[0]

    @pytest.mark.asyncio
    async def test_0x6_recovery_logs_structured_diagnostics(
        self, recovery_manager, tmp_path, monkeypatch
    ):
        """REC-05: recovery diagnostics carry app id, snapshot path, moved paths,
        and outcome -- without unrelated env data."""
        m = recovery_manager
        app = m.config.steamcmd.app_id
        created = self._make_targets(tmp_path, app, which=("manifest", "temp"))
        marker = self._marker(app)
        events = []
        real_log_server_event = None
        import src.server_manager as sm

        def capture(logger, event_type, message, **kwargs):
            events.append((event_type, message, kwargs))

        monkeypatch.setattr(sm, "log_server_event", capture)
        m.steamcmd_manager.run_command = AsyncMock(
            side_effect=[(False, [marker]), (True, ["Success! App '2394010' fully installed."])]
        )

        await m.download_server_files()

        recovery = [e for e in events if e[0] == "steamcmd_recovery"]
        assert len(recovery) == 1
        _, msg, kwargs = recovery[0]
        assert kwargs["app_id"] == app
        assert kwargs["recovery_ok"] is True
        assert kwargs["failure_reason"] is None
        assert kwargs["snapshot_path"] is not None
        assert str(created["manifest"]) in kwargs["moved_paths"]
        assert str(created["temp"]) in kwargs["moved_paths"]
        # No unrelated environment data in diagnostics keys.
        assert not any("env" in k or "PATH" in k for k in kwargs)
        retry = [e for e in events if e[0] == "steamcmd_recovery_retry"]
        assert len(retry) == 1
        assert retry[0][2]["retry_success"] is True
