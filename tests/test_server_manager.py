"""Integration tests for the main server manager."""

import asyncio
import contextlib
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.container import ServiceContainer
from src.managers.api_facade import ServerAPIFacade
from src.managers.lifecycle_manager import ServerLifecycleManager
from src.managers.process_manager import ProcessManager
from src.managers.settings_generator import SettingsGenerator
from src.server_manager import (
    PalworldServerManager,
    ServerDownloadResult,
    wait_for_api_ready,
)

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
        assert result.success is True
        assert result.can_start is True
        assert result.was_updated is True
        assert result.recovery_attempted is False
        assert result.fallback_used is False


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
        result = await m.download_server_files()

        assert result.success is True
        assert result.was_updated is True
        assert result.can_start is True
        assert result.recovery_attempted is True
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
        result = await m.download_server_files()
        assert result.success is True
        assert result.can_start is True
        assert result.was_updated is False
        assert result.recovery_attempted is True
        assert len(m.steamcmd_manager.run_command.await_args_list) == 2

    @pytest.mark.asyncio
    async def test_non_0x6_failure_no_recovery_no_retry(self, recovery_manager):
        """REC-01: unrelated failure keeps prior behavior -- no recovery, one run."""
        m = recovery_manager
        m.steamcmd_manager.run_command = AsyncMock(
            return_value=(False, ["Download failed: disk full", "ERROR! Failed to install app '2394010'."])
        )
        result = await m.download_server_files()
        assert result.success is False
        assert result.can_start is False
        assert result.was_updated is False
        assert result.recovery_attempted is False
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
        result = await m.download_server_files()
        assert result.success is False
        assert result.can_start is False
        assert result.was_updated is False
        assert result.recovery_attempted is False
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

        result = await m.download_server_files()
        assert result.success is False
        assert result.can_start is False
        assert result.was_updated is False
        assert result.recovery_attempted is False
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
        result = await m.download_server_files()
        assert result.success is True
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

    def test_recovery_rejects_symlinked_recovery_root(self, recovery_manager, tmp_path):
        """REC-03: a pre-existing symlinked .steamcmd-recovery root is rejected
        so snapshot mkdir/rename cannot escape the server directory."""
        m = recovery_manager
        app = m.config.steamcmd.app_id
        created = self._make_targets(tmp_path, app, which=("manifest",))
        outside = tmp_path.parent / "outside-recovery"
        outside.mkdir(exist_ok=True)
        (tmp_path / ".steamcmd-recovery").symlink_to(outside, target_is_directory=True)

        ok, snapshot, moved, reason = m._recover_steamcmd_metadata()
        assert ok is False
        assert "recovery root" in (reason or "")
        assert snapshot is None
        assert moved == []
        # Metadata stayed in place; nothing written through the symlink.
        assert created["manifest"].read_bytes() == b"manifest-bytes"
        assert list(outside.iterdir()) == []

    @pytest.mark.asyncio
    async def test_symlinked_recovery_root_never_retries(
        self, recovery_manager, tmp_path
    ):
        """REC-03: rejected recovery root -> no retry, prior behavior preserved."""
        m = recovery_manager
        app = m.config.steamcmd.app_id
        self._make_targets(tmp_path, app, which=("manifest",))
        marker = self._marker(app)
        outside = tmp_path.parent / "outside-recovery-2"
        outside.mkdir(exist_ok=True)
        (tmp_path / ".steamcmd-recovery").symlink_to(outside, target_is_directory=True)
        m.steamcmd_manager.run_command = AsyncMock(return_value=(False, [marker]))

        result = await m.download_server_files()
        assert result.success is False
        assert result.can_start is False
        assert result.was_updated is False
        assert result.recovery_attempted is False
        # Only the failed initial command ran; no retry after rejection.
        assert len(m.steamcmd_manager.run_command.await_args_list) == 1
        assert list(outside.iterdir()) == []

    def test_recovery_rejects_out_of_root_target(self, recovery_manager, tmp_path, monkeypatch):
        """REC-03: containment guard rejects a helper returning an out-of-root
        target instead of letting the parent loop climb past server_dir."""
        m = recovery_manager
        app = m.config.steamcmd.app_id
        outside = tmp_path.parent / "outside-target.acf"
        outside.write_bytes(b"outside")

        monkeypatch.setattr(
            m,
            "_steamcmd_recovery_targets",
            lambda: [tmp_path / "steamapps" / f"appmanifest_{app}.acf", outside],
        )
        ok, snapshot, moved, reason = m._recover_steamcmd_metadata()
        assert ok is False
        assert "outside server dir" in (reason or "")
        assert snapshot is None
        assert moved == []
        assert outside.exists()

    @pytest.mark.asyncio
    async def test_non_directory_recovery_root_fails_structured(self, recovery_manager, tmp_path):
        """REC-03/05: a regular-file recovery root fails snapshot creation with
        a structured reason; one SteamCMD call, no retry, no crash."""
        m = recovery_manager
        app = m.config.steamcmd.app_id
        self._make_targets(tmp_path, app, which=("manifest",))
        marker = self._marker(app)
        (tmp_path / ".steamcmd-recovery").write_text("not-a-directory")
        m.steamcmd_manager.run_command = AsyncMock(return_value=(False, [marker]))

        result = await m.download_server_files()
        assert result.success is False
        assert result.can_start is False
        assert result.was_updated is False
        assert result.recovery_attempted is False
        assert len(m.steamcmd_manager.run_command.await_args_list) == 1
        m.monitoring_manager.handle_error.assert_awaited_once()
        # Manifest untouched; the file root is still a plain file.
        assert (tmp_path / "steamapps" / f"appmanifest_{app}.acf").read_bytes() == b"manifest-bytes"
        assert (tmp_path / ".steamcmd-recovery").is_file()

    def test_recovery_snapshot_collision_never_merges(self, recovery_manager, tmp_path, monkeypatch):
        """REC-02: a pre-existing/colliding snapshot directory is never reused;
        recovery allocates a suffixed sibling and leaves the existing entry intact."""
        from datetime import timezone as tzmod

        import src.server_manager as sm

        m = recovery_manager
        app = m.config.steamcmd.app_id
        created = self._make_targets(tmp_path, app, which=("manifest",))

        # Freeze the clock so the first candidate is deterministic.
        class FakeDateTime:
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 8, 11, 12, 0, 0, 123456, tzinfo=tzmod.utc)

        monkeypatch.setattr(sm, "datetime", FakeDateTime)
        recovery_root = tmp_path / ".steamcmd-recovery"
        recovery_root.mkdir(exist_ok=True)
        candidate = recovery_root / f"app-{app}-20260811T120000123456Z"
        candidate.mkdir()
        (candidate / "stale.bin").write_bytes(b"pre-existing")

        ok, snapshot, moved, reason = m._recover_steamcmd_metadata()
        assert ok is True
        assert reason is None
        # A distinct suffixed snapshot was allocated; the colliding dir is intact.
        assert snapshot.name == f"app-{app}-20260811T120000123456Z-1"
        assert (candidate / "stale.bin").read_bytes() == b"pre-existing"
        # Manifest moved into the new suffixed snapshot under the preserved path.
        assert (
            snapshot / f"steamapps/appmanifest_{app}.acf"
        ).read_bytes() == b"manifest-bytes"
        assert not created["manifest"].exists()

    @pytest.mark.asyncio
    async def test_retry_failure_falls_back_to_valid_executable(
        self, recovery_manager, tmp_path, monkeypatch, capsys
    ):
        """BOOT-02/D-06..D-08: retry failure + valid executable -> fallback
        with the exact deferred-update warning; handle_error not called."""
        m = recovery_manager
        app = m.config.steamcmd.app_id
        self._make_targets(tmp_path, app, which=("manifest",))
        marker = self._marker(app)
        exe = tmp_path / "PalServer.sh"
        exe.write_text("#!/bin/sh\nexec ./PalServer-Linux-Test\n")
        exe.chmod(0o755)

        import src.server_manager as sm

        events = []

        def capture(logger, event_type, message, **kwargs):
            events.append((event_type, message))

        monkeypatch.setattr(sm, "log_server_event", capture)

        m.steamcmd_manager.run_command = AsyncMock(return_value=(False, [marker]))
        result = await m.download_server_files()

        assert result.success is True
        assert result.can_start is True
        assert result.was_updated is False
        assert result.recovery_attempted is True
        assert result.fallback_used is True
        # Exact deferred-update literal on the console (D-08) and in the
        # structured server_fallback log event.
        out = capsys.readouterr().out
        assert (
            "UPDATE DEFERRED: SteamCMD recovery failed; "
            "starting existing server build (may be older)" in out
        )
        assert ("server_fallback", sm.FALLBACK_WARNING) in events
        # Instance is startable, not failed: no error handling.
        m.monitoring_manager.handle_error.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_retry_failure_missing_executable_is_fatal(
        self, recovery_manager, tmp_path
    ):
        """BOOT-02/D-06: retry failure with no PalServer.sh -> fatal, no
        fallback; success=True but can_start=False (D-03)."""
        m = recovery_manager
        app = m.config.steamcmd.app_id
        self._make_targets(tmp_path, app, which=("manifest",))
        marker = self._marker(app)
        m.steamcmd_manager.run_command = AsyncMock(return_value=(False, [marker]))
        result = await m.download_server_files()

        assert result.success is True
        assert result.can_start is False
        assert result.was_updated is False
        assert result.recovery_attempted is True
        assert result.fallback_used is False
        assert len(m.steamcmd_manager.run_command.await_args_list) == 2
        m.monitoring_manager.handle_error.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retry_failure_non_executable_is_invalid(
        self, recovery_manager, tmp_path
    ):
        """BOOT-02/D-06: a non-executable PalServer.sh is not a valid
        fallback and stays fatal."""
        m = recovery_manager
        app = m.config.steamcmd.app_id
        self._make_targets(tmp_path, app, which=("manifest",))
        marker = self._marker(app)
        exe = tmp_path / "PalServer.sh"
        exe.write_text("plain text, not executable")
        exe.chmod(0o644)
        m.steamcmd_manager.run_command = AsyncMock(return_value=(False, [marker]))
        result = await m.download_server_files()

        assert result.success is True
        assert result.can_start is False
        assert result.fallback_used is False
        assert result.recovery_attempted is True
        m.monitoring_manager.handle_error.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_main_proceeds_via_normal_start_on_fallback(
        self, monkeypatch
    ):
        """BOOT-02/D-07: can_start=True (fallback_used=True) routes startup
        through the normal generate/start flow -- not a bypass."""
        import src.server_manager as sm

        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=manager)
        manager.__aexit__ = AsyncMock(return_value=False)
        manager.download_server_files = AsyncMock(
            return_value=ServerDownloadResult(
                success=True,
                can_start=True,
                was_updated=False,
                recovery_attempted=True,
                fallback_used=True,
            )
        )
        manager.generate_server_settings = MagicMock(return_value=True)
        manager.generate_engine_settings = MagicMock(return_value=True)
        manager.start_server_with_verification = AsyncMock(return_value=True)
        manager.get_overall_status = MagicMock(
            return_value={
                "monitoring": {"monitoring_active": True},
                "startup_completed": True,
            }
        )
        manager.is_server_running = MagicMock(return_value=False)
        manager.config = MagicMock()
        manager.config.monitoring.mode = "none"
        manager.config.steamcmd.check_version_update = False

        config = MagicMock()
        config.server.name = "Test"
        config.server.port = 8211
        config.server.max_players = 32
        config.monitoring.log_level = "info"
        config.monitoring.log_format_style = "plain"
        config.monitoring.mode = "none"
        config.paths.log_dir = "logs"
        config.steamcmd.update_on_start = True
        config.steamcmd.check_version_update = False

        monkeypatch.setattr(sm, "get_config", lambda: config)
        monkeypatch.setattr(sm, "setup_logging", lambda **kwargs: None)
        monkeypatch.setattr(sm, "PalworldServerManager", lambda cfg: manager)

        exit_code = await sm._async_main()

        assert exit_code == 0
        manager.download_server_files.assert_awaited_once()
        manager.start_server_with_verification.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_recovery_gate_consumed_causes_single_reset(
        self, recovery_manager, tmp_path, monkeypatch
    ):
        """BOOT-04/D-13: two 0x6 failures on one instance run exactly one
        reset; the second call skips reset/retry and reports
        recovery_attempted=False."""
        import src.server_manager as sm

        m = recovery_manager
        app = m.config.steamcmd.app_id
        self._make_targets(tmp_path, app, which=("manifest",))
        marker = self._marker(app)

        calls = []
        real_recover = sm.PalworldServerManager._recover_steamcmd_metadata

        def counting_recover(instance):
            calls.append(1)
            return real_recover(instance)

        monkeypatch.setattr(
            sm.PalworldServerManager, "_recover_steamcmd_metadata", counting_recover
        )

        # Call 1: initial 0x6 -> gate consumed, reset + retry run, retry fails,
        # no executable -> fatal (recovery_attempted=True).
        m.steamcmd_manager.run_command = AsyncMock(return_value=(False, [marker]))
        r1 = await m.download_server_files()
        assert r1.recovery_attempted is True
        assert r1.fallback_used is False
        assert r1.can_start is False
        assert len(calls) == 1
        # Call 2 on the same instance: gate already consumed -> skip reset and
        # retry, straight to fallback/fatal, recovery_attempted=False.
        r2 = await m.download_server_files()
        assert r2.recovery_attempted is False
        assert r2.can_start is False
        # Exactly one reset across the whole instance lifetime.
        assert len(calls) == 1
        # Call 1 = initial + retry; call 2 = initial only (no retry).
        assert len(m.steamcmd_manager.run_command.await_args_list) == 3

    @pytest.mark.asyncio
    async def test_recovery_gate_consumed_even_on_rollback(
        self, recovery_manager, tmp_path, monkeypatch
    ):
        """BOOT-04: a rollback (reset ok=False) still consumes the instance
        gate at transaction entry -- a later 0x6 does not re-run the reset."""
        import src.server_manager as sm

        m = recovery_manager
        app = m.config.steamcmd.app_id
        self._make_targets(tmp_path, app, which=("manifest",))
        marker = self._marker(app)

        calls = []

        def rollback_recover(instance):
            calls.append(1)
            return (False, None, [], "simulated rollback")

        monkeypatch.setattr(
            sm.PalworldServerManager, "_recover_steamcmd_metadata", rollback_recover
        )

        m.steamcmd_manager.run_command = AsyncMock(return_value=(False, [marker]))
        # First call: gate consumed, reset rolled back (ok=False) -> no reset
        # ran this call (recovery_attempted=False) but the gate stays consumed.
        r1 = await m.download_server_files()
        assert r1.recovery_attempted is False
        assert r1.can_start is False
        assert len(calls) == 1
        # Second 0x6 on the same instance: gate already consumed -> skip reset,
        # straight to fallback/fatal, recovery_attempted=False.
        r2 = await m.download_server_files()
        assert r2.recovery_attempted is False
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_recovery_gate_not_reset_by_successful_start(
        self, recovery_manager, tmp_path, monkeypatch
    ):
        """BOOT-04: a later successful start/update does NOT reset the
        instance one-reset limit; a subsequent 0x6 still skips recovery."""
        import src.server_manager as sm

        m = recovery_manager
        app = m.config.steamcmd.app_id
        self._make_targets(tmp_path, app, which=("manifest",))
        marker = self._marker(app)

        calls = []
        real_recover = sm.PalworldServerManager._recover_steamcmd_metadata

        def counting_recover(instance):
            calls.append(1)
            return real_recover(instance)

        monkeypatch.setattr(
            sm.PalworldServerManager, "_recover_steamcmd_metadata", counting_recover
        )

        # First call: initial 0x6, reset ok, retry succeeds -> was_updated.
        m.steamcmd_manager.run_command = AsyncMock(
            side_effect=[(False, [marker]), (True, ["update complete"])]
        )
        r1 = await m.download_server_files()
        assert r1.recovery_attempted is True
        assert r1.can_start is True
        assert r1.was_updated is True
        assert len(calls) == 1

        # Later 0x6 failure on the same instance: no recovery re-run.
        m.steamcmd_manager.run_command = AsyncMock(return_value=(False, [marker]))
        r2 = await m.download_server_files()
        assert r2.recovery_attempted is False
        assert len(calls) == 1  # limit survives the successful start

    @pytest.mark.asyncio
    async def test_update_loop_fallback_defers_without_restart_or_announce(
        self, monkeypatch, capsys
    ):
        """BOOT-04/D-09..D-11: periodic loop on fallback_used=True logs the
        exact warning, does NOT announce an update or restart, and reschedules
        at the normal 6h interval."""
        import src.server_manager as sm

        real_sleep = asyncio.sleep
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=manager)
        manager.__aexit__ = AsyncMock(return_value=False)
        manager.config.monitoring.mode = "none"
        manager.config.steamcmd.check_version_update = True
        manager.config.steamcmd.update_on_start = True
        manager.generate_server_settings = MagicMock(return_value=True)
        manager.generate_engine_settings = MagicMock(return_value=True)

        fallback_calls = {"n": 0}

        async def fake_download():
            fallback_calls["n"] += 1
            return ServerDownloadResult(
                success=True,
                can_start=True,
                was_updated=False,
                recovery_attempted=True,
                fallback_used=True,
            )

        manager.download_server_files = fake_download
        manager.start_server_with_verification = AsyncMock(return_value=True)
        manager.is_server_running = MagicMock(return_value=True)
        manager.announce_message_any = AsyncMock(return_value=True)
        manager.get_overall_status = MagicMock(
            return_value={
                "monitoring": {"monitoring_active": True},
                "startup_completed": True,
            }
        )
        mm = MagicMock()
        mm.get_monitoring_status = MagicMock(return_value={"player_count": 0})
        mm.event_dispatcher.discord_notifier = None
        manager.get_monitoring_manager = MagicMock(return_value=mm)

        config = MagicMock()
        config.server.name = "Test"
        config.server.port = 8211
        config.server.max_players = 32
        config.monitoring.log_level = "info"
        config.monitoring.log_format_style = "plain"
        config.monitoring.mode = "none"
        config.paths.log_dir = "logs"
        config.steamcmd.update_on_start = True
        config.steamcmd.check_version_update = True

        sleep_durations = []

        def fake_sleep(*args, **kwargs):
            if args:
                sleep_durations.append(args[0])
            return real_sleep(0)

        monkeypatch.setattr(asyncio, "sleep", fake_sleep)
        monkeypatch.setattr(sm, "get_config", lambda: config)
        monkeypatch.setattr(sm, "setup_logging", lambda **kwargs: None)
        monkeypatch.setattr(sm, "PalworldServerManager", lambda cfg: manager)

        task = asyncio.create_task(sm._async_main())
        observed = False
        try:
            deadline = asyncio.get_event_loop().time() + 5
            while not observed:
                if asyncio.get_event_loop().time() > deadline:
                    raise AssertionError(
                        "update loop never reached the fallback reschedule"
                    )
                # Startup download (call 1) + at least one periodic download
                # (call 2), and the normal-6h reschedule sleep recorded.
                if fallback_calls["n"] >= 2 and (6 * 3600) in sleep_durations:
                    observed = True
                    break
                await real_sleep(0.01)
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        out = capsys.readouterr().out
        assert (
            "UPDATE DEFERRED: SteamCMD recovery failed; "
            "starting existing server build (may be older)" in out
        )
        # Pre-check announcement is kept, but the update/restart notify is NOT
        # issued for a deferred fallback.
        announce_msgs = [c.args[0] for c in manager.announce_message_any.call_args_list]
        assert any("Server update check in progress..." in a for a in announce_msgs)
        assert not any(
            "A new Palworld update has been downloaded" in a for a in announce_msgs
        )
        # No restart: start_server_with_verification only from startup.
        manager.start_server_with_verification.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_loop_was_updated_still_announces(self, monkeypatch):
        """BOOT-04 regression: periodic loop with was_updated=True still
        announces the update in-game."""
        import src.server_manager as sm

        real_sleep = asyncio.sleep
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=manager)
        manager.__aexit__ = AsyncMock(return_value=False)
        manager.config.monitoring.mode = "none"
        manager.config.steamcmd.check_version_update = True
        manager.config.steamcmd.update_on_start = True
        manager.generate_server_settings = MagicMock(return_value=True)
        manager.generate_engine_settings = MagicMock(return_value=True)

        async def fake_download():
            return ServerDownloadResult(
                success=True,
                can_start=True,
                was_updated=True,
                recovery_attempted=False,
                fallback_used=False,
            )

        manager.download_server_files = fake_download
        manager.start_server_with_verification = AsyncMock(return_value=True)
        manager.is_server_running = MagicMock(return_value=True)
        manager.announce_message_any = AsyncMock(return_value=True)
        manager.get_overall_status = MagicMock(
            return_value={
                "monitoring": {"monitoring_active": True},
                "startup_completed": True,
            }
        )
        mm = MagicMock()
        mm.get_monitoring_status = MagicMock(return_value={"player_count": 0})
        mm.event_dispatcher.discord_notifier = None
        manager.get_monitoring_manager = MagicMock(return_value=mm)

        config = MagicMock()
        config.server.name = "Test"
        config.server.port = 8211
        config.server.max_players = 32
        config.monitoring.log_level = "info"
        config.monitoring.log_format_style = "plain"
        config.monitoring.mode = "none"
        config.paths.log_dir = "logs"
        config.steamcmd.update_on_start = True
        config.steamcmd.check_version_update = True

        def fake_sleep(*args, **kwargs):
            return real_sleep(0)

        monkeypatch.setattr(asyncio, "sleep", fake_sleep)
        monkeypatch.setattr(sm, "get_config", lambda: config)
        monkeypatch.setattr(sm, "setup_logging", lambda **kwargs: None)
        monkeypatch.setattr(sm, "PalworldServerManager", lambda cfg: manager)

        task = asyncio.create_task(sm._async_main())
        announced = False
        try:
            deadline = asyncio.get_event_loop().time() + 5
            while not announced:
                if asyncio.get_event_loop().time() > deadline:
                    raise AssertionError("update loop never announced an update")
                msgs = [
                    c.args[0]
                    for c in manager.announce_message_any.call_args_list
                    if c.args
                ]
                if any("A new Palworld update has been downloaded" in m for m in msgs):
                    announced = True
                    break
                await real_sleep(0.01)
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        assert announced
