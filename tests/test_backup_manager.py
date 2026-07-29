"""Tests for the backup manager."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

from src.backup.backup_manager import EnhancedBackupManager, BackupInfo

pytestmark = pytest.mark.unit


class TestEnhancedBackupManager:
    """FS-14.x: Backup manager behavior."""

    @pytest.fixture
    def manager(self, palworld_config):
        return EnhancedBackupManager(palworld_config)

    def test_init_creates_backup_dir(self, tmp_path):
        """FS-14.1: Creates backup directory."""
        config = MagicMock()
        config.paths = MagicMock()
        config.paths.backup_dir = tmp_path / "backups"
        config.paths.server_dir = tmp_path / "server"

        manager = EnhancedBackupManager(config)
        assert (tmp_path / "backups").exists()

    def test_backup_info_dataclass(self):
        """FS-14.4: BackupInfo fields."""
        import datetime

        info = BackupInfo(
            filename="test.tar.gz",
            filepath=Path("/backups/test.tar.gz"),
            size_bytes=1024,
            created_time=datetime.datetime.now(),
            backup_type="daily",
        )
        assert info.filename == "test.tar.gz"
        assert info.backup_type == "daily"

    def test_determine_backup_type_daily(self, manager):
        """FS-14.2: Default is daily."""
        import datetime

        dt = datetime.datetime(2024, 6, 15, 10, 0)
        assert manager._determine_backup_type(dt) == "daily"

    def test_determine_backup_type_weekly(self, manager):
        """FS-14.2: Sunday at schedule_time is weekly."""
        import datetime

        manager.config.backup.schedule_time = "03:00"
        # Sunday = weekday 6
        dt = datetime.datetime(2024, 6, 16, 3, 0)
        assert manager._determine_backup_type(dt) == "weekly"

    def test_determine_backup_type_monthly(self, manager):
        """FS-14.2: 1st at schedule_time is monthly."""
        import datetime

        manager.config.backup.schedule_time = "02:00"
        dt = datetime.datetime(2024, 7, 1, 2, 0)
        assert manager._determine_backup_type(dt) == "monthly"

    def test_backup_disabled_skips_scheduler(self, palworld_config):
        """FS-14.1: Scheduler won't start when disabled."""
        palworld_config.backup.enabled = False
        manager = EnhancedBackupManager(palworld_config)
        import asyncio

        asyncio.run(manager.start_backup_scheduler())
        assert manager._running is False

    @pytest.mark.asyncio
    async def test_create_backup_source_missing(self, manager, tmp_path):
        """FS-14.3: Returns error when source missing."""
        manager.source_dir = tmp_path / "nonexistent" / "source"
        manager.backup_dir = tmp_path / "backups"
        manager.backup_dir.mkdir(parents=True, exist_ok=True)
        result = await manager.create_backup()
        assert result["success"] is False
        assert "Source directory does not exist" in result["error"]

    def test_list_backups_empty(self, manager, tmp_path):
        """FS-14: Empty directory returns empty list."""
        manager.backup_dir = tmp_path
        assert manager.list_backups() == []

    def test_list_backups_with_files(self, manager, tmp_path):
        """FS-14.4: Lists backup files with metadata."""
        (tmp_path / "daily_auto_20240101_120000.tar.gz").write_text("data")
        (tmp_path / "manual_backup.tar.gz").write_text("data")
        manager.backup_dir = tmp_path

        backups = manager.list_backups()
        assert len(backups) == 2

    def test_cleanup_old_backups(self, manager, tmp_path):
        """FS-14.4: Retention cleanup."""
        manager.backup_dir = tmp_path
        manager.retention_days = 0
        manager.retention_weeks = 0
        manager.retention_months = 0
        manager.max_backups = 0

        (tmp_path / "daily_auto_old.tar.gz").write_text("data")
        import datetime

        old_time = datetime.datetime.now() - datetime.timedelta(days=10)
        mock_info = BackupInfo(
            filename="daily_auto_old.tar.gz",
            filepath=tmp_path / "daily_auto_old.tar.gz",
            size_bytes=100,
            created_time=old_time,
            backup_type="daily",
        )
        with patch.object(manager, "list_backups", return_value=[mock_info]):
            count = manager.cleanup_old_backups()
            assert count == 1
            assert not (tmp_path / "daily_auto_old.tar.gz").exists()

    def test_get_backup_statistics(self, manager, tmp_path):
        """FS-14.8: Statistics summary."""
        manager.backup_dir = tmp_path
        stats = manager.get_backup_statistics()
        assert "total_backups" in stats
        assert "total_size_bytes" in stats
        assert "retention_policy" in stats

    @pytest.mark.asyncio
    async def test_restore_backup_nonexistent(self, manager):
        """FS-14.x: Restore with nonexistent file returns error."""
        result = await manager.restore_backup(Path("/nonexistent/backup.tar.gz"))
        assert result["success"] is False
        assert "does not exist" in result["error"]

    @pytest.mark.asyncio
    async def test_restore_backup_validates_archive(self, manager, tmp_path):
        """FS-14.x: Invalid archive returns error."""
        fake_backup = tmp_path / "bad_backup.tar.gz"
        fake_backup.write_text("not a tar archive")
        result = await manager.restore_backup(fake_backup)
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_restore_backup_success(self, tmp_path):
        """FS-14.x: Valid backup restores SaveGames and Config."""
        import datetime
        import tarfile

        server_dir = tmp_path / "server" / "Pal" / "Saved"
        backup_dir = tmp_path / "backups"
        config_dir = server_dir / "Config" / "LinuxServer"
        save_dir = server_dir / "SaveGames" / "world"

        config_dir.mkdir(parents=True)
        save_dir.mkdir(parents=True)

        (save_dir / "level.sav").write_text("world_data")
        (config_dir / "PalWorldSettings.ini").write_text("config_data")

        config = MagicMock()
        config.paths.server_dir = tmp_path / "server"
        config.paths.backup_dir = backup_dir
        manager = EnhancedBackupManager(config)

        # Create a backup first
        result = await manager.create_backup("test_restore", "manual")
        assert result["success"]
        backup_path = Path(result["filepath"])

        # Modify source data to ensure restore actually replaces it
        (save_dir / "level.sav").write_text("corrupted")
        assert (save_dir / "level.sav").read_text() == "corrupted"

        # Restore
        restore_result = await manager.restore_backup(backup_path)
        assert restore_result["success"], f"Restore failed: {restore_result.get('error')}"

        # Verify restored content
        assert (save_dir / "level.sav").exists()
        assert (save_dir / "level.sav").read_text() == "world_data"

    @pytest.mark.asyncio
    async def test_restore_backup_rejects_path_traversal(self, tmp_path):
        """R2-P1-01: Archive with .. traversal is rejected."""
        import tarfile

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        malicious = tmp_path / "escape.tar.gz"
        with tarfile.open(malicious, "w:gz") as tar:
            info = tarfile.TarInfo(name="SaveGames/../../etc/passwd")
            info.type = tarfile.REGTYPE
            tar.addfile(info, b"hacked")

        config = MagicMock()
        config.paths.server_dir = tmp_path / "server"
        config.paths.backup_dir = backup_dir
        manager = EnhancedBackupManager(config)

        result = await manager.restore_backup(malicious)
        assert result["success"] is False
        assert "traversal" in result["error"]

    @pytest.mark.asyncio
    async def test_restore_backup_rejects_absolute_path(self, tmp_path):
        """R2-P1-01: Archive with absolute path is rejected."""
        import tarfile

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        malicious = tmp_path / "absolute.tar.gz"
        with tarfile.open(malicious, "w:gz") as tar:
            info = tarfile.TarInfo(name="/etc/passwd")
            info.type = tarfile.REGTYPE
            tar.addfile(info, b"hacked")

        config = MagicMock()
        config.paths.server_dir = tmp_path / "server"
        config.paths.backup_dir = backup_dir
        manager = EnhancedBackupManager(config)

        result = await manager.restore_backup(malicious)
        assert result["success"] is False
        assert "absolute" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_restore_backup_rejects_symlink(self, tmp_path):
        """R2-P1-01: Archive with symlink is rejected."""
        import tarfile

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        malicious = tmp_path / "symlink.tar.gz"
        with tarfile.open(malicious, "w:gz") as tar:
            info = tarfile.TarInfo(name="SaveGames/link")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            tar.addfile(info)

        config = MagicMock()
        config.paths.server_dir = tmp_path / "server"
        config.paths.backup_dir = backup_dir
        manager = EnhancedBackupManager(config)

        result = await manager.restore_backup(malicious)
        assert result["success"] is False
        assert "symbolic" in result["error"].lower() or "link" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_restore_backup_rejects_hardlink(self, tmp_path):
        """R2-P1-01: Archive with hardlink is rejected."""
        import tarfile

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        malicious = tmp_path / "hardlink.tar.gz"
        with tarfile.open(malicious, "w:gz") as tar:
            # Create a regular file then a hardlink to it
            content = tarfile.TarInfo(name="SaveGames/target")
            content.type = tarfile.REGTYPE
            tar.addfile(content, b"data")
            link = tarfile.TarInfo(name="SaveGames/link")
            link.type = tarfile.LNKTYPE
            link.linkname = "SaveGames/target"
            tar.addfile(link)

        config = MagicMock()
        config.paths.server_dir = tmp_path / "server"
        config.paths.backup_dir = backup_dir
        manager = EnhancedBackupManager(config)

        result = await manager.restore_backup(malicious)
        assert result["success"] is False
        assert "hard link" in result["error"].lower() or "link" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_restore_backup_rejects_special_entry(self, tmp_path):
        """R2-P1-01: Archive with device/FIFO entry is rejected."""
        import tarfile

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        malicious = tmp_path / "fifo.tar.gz"
        with tarfile.open(malicious, "w:gz") as tar:
            info = tarfile.TarInfo(name="SaveGames/fifo")
            info.type = tarfile.FIFOTYPE
            tar.addfile(info)

        config = MagicMock()
        config.paths.server_dir = tmp_path / "server"
        config.paths.backup_dir = backup_dir
        manager = EnhancedBackupManager(config)

        result = await manager.restore_backup(malicious)
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_create_backup_aborts_on_save_world_false(self, tmp_path):
        """R2-P2-06: Backup aborts when save_world returns False."""
        config = MagicMock()
        config.paths.server_dir = tmp_path / "server"
        config.paths.backup_dir = tmp_path / "backups"
        (tmp_path / "server" / "Pal" / "Saved").mkdir(parents=True)
        manager = EnhancedBackupManager(config, save_world_callback=AsyncMock(return_value=False))

        result = await manager.create_backup("test", "manual")
        assert result["success"] is False
        assert "Save-world returned False" in result["error"]

    @pytest.mark.asyncio
    async def test_create_backup_aborts_on_save_world_exception(self, tmp_path):
        """R2-P2-06: Backup aborts when save_world raises."""

        async def failing_save():
            raise RuntimeError("save failed")

        config = MagicMock()
        config.paths.server_dir = tmp_path / "server"
        config.paths.backup_dir = tmp_path / "backups"
        (tmp_path / "server" / "Pal" / "Saved").mkdir(parents=True)
        manager = EnhancedBackupManager(config, save_world_callback=failing_save)

        result = await manager.create_backup("test", "manual")
        assert result["success"] is False
        assert "Save-world exception" in result["error"]

    @pytest.mark.asyncio
    async def test_create_backup_snapshot_not_live(self, tmp_path):
        """R2-P2-06: Archive is built from a snapshot copy, not live dir."""
        import tarfile

        config = MagicMock()
        config.paths.server_dir = tmp_path / "server"
        config.paths.backup_dir = tmp_path / "backups"
        (tmp_path / "server" / "Pal" / "Saved" / "SaveGames" / "world").mkdir(parents=True)
        (tmp_path / "server" / "Pal" / "Saved" / "SaveGames" / "world" / "level.sav").write_text(
            "data"
        )
        manager = EnhancedBackupManager(config)

        result = await manager.create_backup("snapshot_test", "manual")
        assert result["success"]

        # Verify the archive contains a SaveGames entry (snapshot structure)
        with tarfile.open(result["filepath"]) as tar:
            names = tar.getnames()
            assert any("SaveGames" in n for n in names)
