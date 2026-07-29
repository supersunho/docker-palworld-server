#!/usr/bin/env python3
"""
Enhanced backup manager with retention policies
Automatic backup scheduling and cleanup system
"""

import asyncio
import tarfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from ..config_loader import get_config, PalworldConfig
from ..logging_setup import get_logger, log_backup_event
from typing import Callable, Awaitable

# Optional async callback for save-before-backup
SaveWorldFn = Optional[Callable[[], Awaitable[bool]]]


@dataclass
class BackupInfo:
    """Backup file information structure"""

    filename: str
    filepath: Path
    size_bytes: int
    created_time: datetime
    backup_type: str


class EnhancedBackupManager:
    """Enhanced backup manager with config integration and retention policies"""

    def __init__(
        self,
        config: Optional[PalworldConfig] = None,
        save_world_callback: SaveWorldFn = None,
    ):
        """Initialize backup manager with config"""
        self.config = config or get_config()
        self.logger = get_logger("palworld.backup")
        self.save_world_callback = save_world_callback

        self.backup_dir = self.config.paths.backup_dir
        self.source_dir = self.config.paths.server_dir / "Pal" / "Saved"

        self.enabled = self.config.backup.enabled
        self.interval_seconds = self.config.backup.interval_seconds
        self.retention_days = self.config.backup.retention_days
        self.retention_weeks = self.config.backup.retention_weeks
        self.retention_months = self.config.backup.retention_months
        self.compress = self.config.backup.compress
        self.max_backups = self.config.backup.max_backups
        self.cleanup_interval = self.config.backup.cleanup_interval

        self.backup_dir.mkdir(parents=True, exist_ok=True)

        self._backup_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        # Serialise backup operations to prevent concurrent archive creation
        self._backup_lock = asyncio.Lock()
        self._restore_lock = asyncio.Lock()
        # Dedup tracking: completed daily/weekly/monthly bucket keys
        # \"daily-YYYYMMDD\", \"weekly-YYYYWww\", \"monthly-YYYYMM\"
        self._completed_buckets: Dict[str, int] = {}

    async def start_backup_scheduler(self):
        """Start automatic backup scheduler"""
        if not self.enabled:
            self.logger.warning("Backup is disabled in configuration")
            return

        if self._running:
            self.logger.warning("Backup scheduler is already running")
            return

        self._running = True

        self._backup_task = asyncio.create_task(self._backup_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        log_backup_event(
            self.logger,
            "backup_start",
            f"Backup scheduler started (interval: {self.interval_seconds}s, cleanup: {self.cleanup_interval}s)",
        )

    async def stop_backup_scheduler(self):
        """Stop backup scheduler"""
        self._running = False

        if self._backup_task:
            self._backup_task.cancel()
            try:
                await self._backup_task
            except asyncio.CancelledError:
                pass

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        log_backup_event(self.logger, "backup_cleanup", "Backup scheduler stopped")

    def _next_calendar_schedule(self) -> float:
        """Calculate seconds until next scheduled backup.

        Returns the delay in seconds based on schedule_type:
        - "interval": aligned to interval_seconds boundary
        - "daily": next occurrence of schedule_time (HH:MM) today or tomorrow
        - "weekly": next Sunday at schedule_time
        - "monthly": next 1st of month at schedule_time
        """
        now = datetime.now()
        if self.config.backup.schedule_type == "interval":
            ts = time.time()
            aligned = ((ts // self.interval_seconds) + 1) * self.interval_seconds
            return aligned - ts

        try:
            target_hour, target_min = self._parse_schedule_time()
        except (ValueError, IndexError):
            self.logger.warning(
                "Invalid schedule_time '%s', falling back to 04:00",
                self.config.backup.schedule_time,
            )
            target_hour, target_min = 4, 0

        if self.config.backup.schedule_type == "daily":
            target = now.replace(hour=target_hour, minute=target_min, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return (target - now).total_seconds()

        if self.config.backup.schedule_type == "weekly":
            # Next Sunday (weekday() == 6)
            days_ahead = (6 - now.weekday()) % 7
            if days_ahead == 0 and now.hour >= target_hour:
                days_ahead = 7  # Next Sunday if already past today's target time
            target = (now + timedelta(days=days_ahead)).replace(
                hour=target_hour, minute=target_min, second=0, microsecond=0
            )
            return max(0, (target - now).total_seconds())

        if self.config.backup.schedule_type == "monthly":
            # Next 1st of month
            target = now.replace(
                day=1, hour=target_hour, minute=target_min, second=0, microsecond=0
            )
            if target <= now:
                # Move to next month
                month = now.month + 1
                year = now.year
                if month > 12:
                    month = 1
                    year += 1
                target = now.replace(
                    year=year,
                    month=month,
                    day=1,
                    hour=target_hour,
                    minute=target_min,
                    second=0,
                    microsecond=0,
                )
            return (target - now).total_seconds()

        # Fallback: interval
        ts = time.time()
        aligned = ((ts // self.interval_seconds) + 1) * self.interval_seconds
        return aligned - ts

    async def _backup_loop(self):
        """Main backup creation loop — schedule-aware with calendar dedup"""
        initial_delay = self._next_calendar_schedule()
        self.logger.info(
            "First backup in %ds (schedule: %s%s)",
            initial_delay,
            self.config.backup.schedule_type,
            (
                f" @ {self.config.backup.schedule_time}"
                if self.config.backup.schedule_type != "interval"
                else ""
            ),
        )
        await asyncio.sleep(initial_delay)

        while self._running:
            try:
                current_time = datetime.now()
                backup_type = self._determine_backup_type(current_time)

                # Skip if this calendar bucket was already completed
                if self.config.backup.schedule_type != "interval" and not self._needs_backup(
                    backup_type, current_time
                ):
                    self.logger.debug(
                        "Skipping %s backup — bucket already completed",
                        backup_type,
                    )
                    await asyncio.sleep(self._next_calendar_schedule())
                    continue

                self.logger.debug(
                    "Creating %s backup at %s",
                    backup_type,
                    current_time.strftime("%Y-%m-%d %H:%M:%S"),
                )

                result = await self.create_backup(f"{backup_type}_auto", backup_type)

                if result.get("success"):
                    # Mark this calendar bucket as completed
                    key = self._bucket_key(current_time, backup_type)
                    if key:
                        self._completed_buckets[key] = current_time.day
                    log_backup_event(
                        self.logger,
                        "backup_complete",
                        f"{backup_type.capitalize()} backup created successfully",
                        filename=result.get("filename"),
                        size_mb=result.get("size_mb", 0),
                        duration_seconds=result.get("duration_seconds", 0),
                    )
                else:
                    log_backup_event(
                        self.logger,
                        "backup_fail",
                        f"Failed to create {backup_type} backup: {result.get('error')}",
                        error=result.get("error"),
                    )

                # Wait until next schedule
                await asyncio.sleep(self._next_calendar_schedule())

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Backup loop error", error=str(e))
                await asyncio.sleep(300)

    async def _cleanup_loop(self):
        """Backup cleanup loop"""
        await asyncio.sleep(1800)

        while self._running:
            try:
                self.logger.debug("Starting backup cleanup process")
                cleaned_count = self.cleanup_old_backups()

                if cleaned_count > 0:
                    log_backup_event(
                        self.logger,
                        "cleanup_success",
                        f"Cleaned up {cleaned_count} old backup files",
                    )

                await asyncio.sleep(self.cleanup_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Cleanup loop error", error=str(e))
                await asyncio.sleep(3600)

    def _bucket_key(self, current_time: datetime, backup_type: str) -> str:
        """Generate a dedup key for a calendar backup bucket.

        Returns a string identifying the time period so the scheduler
        can skip a bucket that was already completed.
        """
        if backup_type == "daily":
            return f"daily-{current_time.strftime('%Y%m%d')}"
        elif backup_type == "weekly":
            # ISO week number: YYYY + 'W' + week number (01-53)
            return f"weekly-{current_time.strftime('%YW%W')}"
        elif backup_type == "monthly":
            return f"monthly-{current_time.strftime('%Y%m')}"
        return ""

    def _needs_backup(self, backup_type: str, current_time: datetime) -> bool:
        """Check whether the given calendar bucket still needs a backup.

        Returns True when the bucket has not been completed yet.
        For 'interval' and 'manual' types this always returns True.
        """
        key = self._bucket_key(current_time, backup_type)
        if not key:
            return True
        if self._completed_buckets.get(key) == current_time.day:
            return False
        return True

    def _determine_backup_type(self, current_time: datetime) -> str:
        """Determine backup type based on current time and config.

        Uses the configured schedule_time to decide whether the current
        slot is monthly (1st at schedule_time), weekly (Sunday at
        schedule_time), or a regular daily backup.
        """
        target_hour, target_min = self._parse_schedule_time()

        if (
            current_time.day == 1
            and current_time.hour == target_hour
            and current_time.minute == target_min
        ):
            return "monthly"

        if (
            current_time.weekday() == 6
            and current_time.hour == target_hour
            and current_time.minute == target_min
        ):
            return "weekly"

        return "daily"

    def _parse_schedule_time(self) -> tuple[int, int]:
        """Parse schedule_time config into (hour, minute), defaulting to (4, 0).

        Validates hour (0-23) and minute (0-59). Returns fallback on invalid values.
        """
        try:
            parts = self.config.backup.schedule_time.split(":")
            hour, minute = int(parts[0]), int(parts[1])
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return hour, minute
            self.logger.warning(
                "schedule_time '%s' out of range, falling back to 04:00",
                self.config.backup.schedule_time,
            )
            return 4, 0
        except (ValueError, IndexError):
            return 4, 0

    async def create_backup(
        self, name: Optional[str] = None, backup_type: str = "manual"
    ) -> Dict[str, Any]:
        """Create a backup with specified name and type"""
        start_time = time.time()

        try:
            if not self.source_dir.exists():
                return {
                    "success": False,
                    "error": f"Source directory does not exist: {self.source_dir}",
                }

            # Save world before backup — abort on failure
            if self.save_world_callback:
                try:
                    saved = await self.save_world_callback()
                    if saved:
                        self.logger.info("World saved before backup")
                    else:
                        self.logger.error("Save-world returned False — aborting backup")
                        return {
                            "success": False,
                            "error": "Save-world returned False, backup aborted to prevent data corruption",
                        }
                except Exception as e:
                    self.logger.error(f"Save-world failed before backup: {e} — aborting backup")
                    return {
                        "success": False,
                        "error": f"Save-world exception before backup: {e}",
                    }

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if name:
                backup_name = f"{name}_{timestamp}"
            else:
                backup_name = f"{backup_type}_backup_{timestamp}"

            backup_filename = f"{backup_name}.tar.gz" if self.compress else f"{backup_name}.tar"
            backup_path = self.backup_dir / backup_filename

            await self._create_archive(backup_path, backup_type)

            duration_seconds = time.time() - start_time
            size_bytes = backup_path.stat().st_size
            size_mb = size_bytes / (1024 * 1024)

            return {
                "success": True,
                "filename": backup_filename,
                "filepath": str(backup_path),
                "size_bytes": size_bytes,
                "size_mb": round(size_mb, 2),
                "duration_seconds": round(duration_seconds, 2),
                "backup_type": backup_type,
            }

        except Exception as e:
            duration_seconds = time.time() - start_time

            return {
                "success": False,
                "error": str(e),
                "duration_seconds": round(duration_seconds, 2),
            }

    async def _create_archive(self, backup_path: Path, backup_type: str):
        """Create backup archive from a snapshot copy.

        Uses an asyncio.Lock to serialise concurrent backup attempts.
        Copies the live source directory to a temp location, then
        archives the snapshot so the server can keep writing during
        the (relatively slow) compression phase.
        """
        async with self._backup_lock:
            loop = asyncio.get_event_loop()
            import shutil
            import tempfile

            snapshot_dir = Path(tempfile.mkdtemp(prefix="palworld_backup_"))

            try:
                # Async snapshot — copy source to temp dir
                await loop.run_in_executor(
                    None,
                    lambda: shutil.copytree(
                        self.source_dir,
                        snapshot_dir / "SaveGames",
                        ignore=shutil.ignore_patterns("*.backup", "*.tmp"),
                    ),
                )

                config_dir = self.config.paths.server_dir / "Pal" / "Saved" / "Config"
                if config_dir.exists():
                    await loop.run_in_executor(
                        None,
                        lambda: shutil.copytree(
                            config_dir,
                            snapshot_dir / "Config",
                        ),
                    )

                # Archive from snapshot
                def create_tar():
                    compression = "gz" if self.compress else ""
                    mode = f"w:{compression}" if compression else "w"

                    with tarfile.open(backup_path, mode) as tar:
                        for item in snapshot_dir.iterdir():
                            tar.add(item, arcname=item.name)

                await loop.run_in_executor(None, create_tar)
            finally:
                # Clean up the snapshot directory
                await loop.run_in_executor(
                    None,
                    lambda: shutil.rmtree(snapshot_dir, ignore_errors=True),
                )

    def list_backups(self) -> List[BackupInfo]:
        """List all backup files with metadata"""
        backups = []

        if not self.backup_dir.exists():
            return backups

        patterns = ["*.tar.gz", "*.tar"] if self.compress else ["*.tar"]
        backup_files = []

        for pattern in patterns:
            backup_files.extend(self.backup_dir.glob(pattern))

        for backup_file in backup_files:
            try:
                backup_type = "manual"
                if "daily" in backup_file.name:
                    backup_type = "daily"
                elif "weekly" in backup_file.name:
                    backup_type = "weekly"
                elif "monthly" in backup_file.name:
                    backup_type = "monthly"

                backup_info = BackupInfo(
                    filename=backup_file.name,
                    filepath=backup_file,
                    size_bytes=backup_file.stat().st_size,
                    created_time=datetime.fromtimestamp(backup_file.stat().st_mtime),
                    backup_type=backup_type,
                )

                backups.append(backup_info)

            except Exception as e:
                self.logger.warning(f"Failed to process backup file {backup_file}: {e}")

        backups.sort(key=lambda x: x.created_time, reverse=True)

        return backups

    async def restore_backup(self, backup_path: Path) -> Dict[str, Any]:
        """Restore server data from a backup archive.

        Extracts the backup archive to a unique staging directory with
        rollback support. Uses _restore_lock to prevent concurrent restores.

        Security: rejects path traversal, absolute paths, symlinks,
        hardlinks, and device entries.

        Args:
            backup_path: Path to the backup .tar or .tar.gz file.

        Returns:
            dict with success bool, error message if applicable,
            and duration_seconds.
        """
        start_time = time.time()
        staging_dir = None
        recovery_dir = None
        async with self._restore_lock:
            try:
                if not backup_path.exists():
                    return {
                        "success": False,
                        "error": f"Backup file does not exist: {backup_path}",
                        "duration_seconds": round(time.time() - start_time, 2),
                    }

                # Determine compression from file extension
                is_compressed = backup_path.suffix == ".gz"
                mode = "r:gz" if is_compressed else "r"

                # Unique staging and recovery directories
                import uuid

                staging_suffix = f".restore_staging_{uuid.uuid4().hex[:8]}"
                staging_dir = self.backup_dir / staging_suffix
                recovery_suffix = f".restore_recovery_{uuid.uuid4().hex[:8]}"
                recovery_dir = self.backup_dir / recovery_suffix
                config_dir = self.config.paths.server_dir / "Pal" / "Saved" / "Config"

                def validate_and_extract():
                    with tarfile.open(backup_path, mode) as tar:
                        members = tar.getmembers()

                        # 1. Reject non-regular file entries
                        for member in members:
                            if member.issym() or member.islnk():
                                raise ValueError(
                                    f"Archive contains a symbolic/hard link '{member.name}' — "
                                    "refusing to extract for security"
                                )
                            if not member.isfile() and not member.isdir():
                                raise ValueError(
                                    f"Archive contains a special entry '{member.name}' "
                                    f"(type {member.type}) — refusing to extract"
                                )

                        # 2. Validate and normalize paths; reject traversal / absolute
                        allowed_roots = {}
                        for member in members:
                            raw = member.name

                            # Reject absolute paths
                            if raw.startswith("/"):
                                raise ValueError(
                                    f"Archive contains absolute path '{raw}' — refusing to extract"
                                )

                            # Normalise and reject .. traversal
                            norm = Path(raw).as_posix()
                            if ".." in norm.split("/"):
                                raise ValueError(
                                    f"Archive contains path traversal '{raw}' — refusing to extract"
                                )

                            if norm.startswith("SaveGames/") or norm == "SaveGames":
                                stripped = (
                                    norm[len("SaveGames/") :]
                                    if norm.startswith("SaveGames/")
                                    else ""
                                )
                                target_root = Path(self.source_dir).resolve()
                            elif norm.startswith("Config/") or norm == "Config":
                                stripped = (
                                    norm[len("Config/") :] if norm.startswith("Config/") else ""
                                )
                                target_root = Path(config_dir).resolve()
                            else:
                                raise ValueError(
                                    f"Archive member '{raw}' is not under SaveGames/ or Config/ — "
                                    "refusing to extract"
                                )

                            # Resolve the full extracted path and verify it stays under root
                            candidate = (target_root / stripped).resolve()
                            if (
                                not str(candidate).startswith(str(target_root) + "/")
                                and candidate != target_root
                            ):
                                raise ValueError(
                                    f"Extracted path '{raw}' resolves outside target directory "
                                    f"({candidate}) — refusing to extract"
                                )

                            allowed_roots[member] = (target_root, stripped)

                        # 3. Check top-level SaveGames/ Config/ structure
                        arcnames = {m.name for m in members}
                        has_savegames = any(
                            n == "SaveGames" or n.startswith("SaveGames/") for n in arcnames
                        )
                        if not has_savegames:
                            raise ValueError(
                                "Archive does not contain 'SaveGames/' directory — "
                                "not a valid Palworld backup"
                            )

                        # 4. Clean staging directory
                        if staging_dir.exists():
                            import shutil

                            shutil.rmtree(staging_dir)
                        staging_dir.mkdir(parents=True, exist_ok=True)

                        # 5. Extract to staging (preserving original member names for structure)
                        tar.extractall(path=staging_dir, members=members)

                        # 6. Backup originals to recovery dir for rollback
                        import shutil
                        import json as _json

                        recovery_dir.mkdir(parents=True, exist_ok=True)
                        rollback_map = []  # [[orig_dest_str, backup_rel_path_str], ...]
                        for member, (target_root, stripped) in allowed_roots.items():
                            if member.isdir():
                                continue
                            dest = target_root / stripped
                            if dest.exists():
                                # Store in recovery dir under a sanitised relative path
                                dest_rel = str(dest).replace("/", "_").replace(":", "_")
                                backup_path_orig = recovery_dir / dest_rel
                                shutil.move(str(dest), str(backup_path_orig))
                                rollback_map.append([str(dest), dest_rel])
                        # Write manifest for rollback
                        with open(recovery_dir / "_manifest.json", "w") as _mf:
                            _json.dump(rollback_map, _mf)

                        # 7. Move staged files to their target roots
                        for member, (target_root, stripped) in allowed_roots.items():
                            if member.isdir():
                                continue
                            staging_path = staging_dir / member.name
                            if not staging_path.exists():
                                continue
                            dest = target_root / stripped
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(staging_path), str(dest))

                        # 8. Clean up staging and recovery on success
                        shutil.rmtree(staging_dir)
                        shutil.rmtree(recovery_dir)

                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, validate_and_extract)

                duration = round(time.time() - start_time, 2)
                log_backup_event(
                    self.logger,
                    "backup_restore",
                    f"Backup restored from {backup_path.name} in {duration}s",
                )
                return {"success": True, "duration_seconds": duration, "file": str(backup_path)}

            except Exception as e:
                duration = round(time.time() - start_time, 2)
                # Rollback: restore originals from recovery dir
                if recovery_dir is not None and recovery_dir.exists():
                    try:
                        import shutil
                        import json as _json

                        manifest_path = recovery_dir / "_manifest.json"
                        if manifest_path.exists():
                            with open(manifest_path) as _mf:
                                rollback_map = _json.load(_mf)
                            for orig_dest, backup_rel in rollback_map:
                                backup_file = recovery_dir / backup_rel
                                if backup_file.exists():
                                    orig_path = Path(orig_dest)
                                    orig_path.parent.mkdir(parents=True, exist_ok=True)
                                    shutil.move(str(backup_file), str(orig_path))
                        shutil.rmtree(recovery_dir)
                    except Exception:
                        pass
                # Clean up staging on failure
                if staging_dir is not None:
                    try:
                        import shutil

                        if staging_dir.exists():
                            shutil.rmtree(staging_dir)
                    except Exception:
                        pass
                self.logger.error(f"Backup restore failed: {e}")
                return {"success": False, "error": str(e), "duration_seconds": duration}

    def cleanup_old_backups(self) -> int:
        """Clean up old backups based on retention policies"""
        if not self.backup_dir.exists():
            return 0

        backups = self.list_backups()
        now = datetime.now()
        deleted_count = 0

        daily_cutoff = now - timedelta(days=self.retention_days)
        weekly_cutoff = now - timedelta(weeks=self.retention_weeks)
        monthly_cutoff = now - timedelta(days=self.retention_months * 30)

        daily_backups = [b for b in backups if b.backup_type == "daily"]
        weekly_backups = [b for b in backups if b.backup_type == "weekly"]
        monthly_backups = [b for b in backups if b.backup_type == "monthly"]
        manual_backups = [b for b in backups if b.backup_type == "manual"]

        for backup in daily_backups:
            if backup.created_time < daily_cutoff:
                try:
                    backup.filepath.unlink()
                    deleted_count += 1
                    self.logger.debug(f"Deleted old daily backup: {backup.filename}")
                except Exception as e:
                    self.logger.error(f"Failed to delete daily backup {backup.filename}: {e}")

        for backup in weekly_backups:
            if backup.created_time < weekly_cutoff:
                try:
                    backup.filepath.unlink()
                    deleted_count += 1
                    self.logger.debug(f"Deleted old weekly backup: {backup.filename}")
                except Exception as e:
                    self.logger.error(f"Failed to delete weekly backup {backup.filename}: {e}")

        for backup in monthly_backups:
            if backup.created_time < monthly_cutoff:
                try:
                    backup.filepath.unlink()
                    deleted_count += 1
                    self.logger.debug(f"Deleted old monthly backup: {backup.filename}")
                except Exception as e:
                    self.logger.error(f"Failed to delete monthly backup {backup.filename}: {e}")

        if len(manual_backups) > 20:
            excess_manual = manual_backups[20:]
            for backup in excess_manual:
                try:
                    backup.filepath.unlink()
                    deleted_count += 1
                    self.logger.debug(f"Deleted excess manual backup: {backup.filename}")
                except Exception as e:
                    self.logger.error(f"Failed to delete manual backup {backup.filename}: {e}")

        remaining_backups = self.list_backups()
        if len(remaining_backups) > self.max_backups:
            excess_count = len(remaining_backups) - self.max_backups
            oldest_backups = sorted(remaining_backups, key=lambda x: x.created_time)[:excess_count]

            for backup in oldest_backups:
                try:
                    backup.filepath.unlink()
                    deleted_count += 1
                    self.logger.info(f"Deleted backup due to max limit: {backup.filename}")
                except Exception as e:
                    self.logger.error(f"Failed to delete backup {backup.filename}: {e}")

        return deleted_count

    def get_backup_statistics(self) -> Dict[str, Any]:
        """Get backup statistics and summary"""
        backups = self.list_backups()

        total_size = sum(backup.size_bytes for backup in backups)
        daily_count = len([b for b in backups if b.backup_type == "daily"])
        weekly_count = len([b for b in backups if b.backup_type == "weekly"])
        monthly_count = len([b for b in backups if b.backup_type == "monthly"])
        manual_count = len([b for b in backups if b.backup_type == "manual"])

        return {
            "total_backups": len(backups),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "daily_backups": daily_count,
            "weekly_backups": weekly_count,
            "monthly_backups": monthly_count,
            "manual_backups": manual_count,
            "oldest_backup": backups[-1].created_time if backups else None,
            "newest_backup": backups[0].created_time if backups else None,
            "retention_policy": {
                "days": self.retention_days,
                "weeks": self.retention_weeks,
                "months": self.retention_months,
            },
        }


_backup_manager: Optional[EnhancedBackupManager] = None


def get_backup_manager(config: Optional[PalworldConfig] = None) -> EnhancedBackupManager:
    """Return global backup manager instance"""
    global _backup_manager

    if _backup_manager is None:
        _backup_manager = EnhancedBackupManager(config)

    return _backup_manager


async def _async_main():
    """Async backup scheduler main — runs until cancelled."""
    mgr = get_backup_manager()
    await mgr.start_backup_scheduler()
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await mgr.stop_backup_scheduler()


def main():
    """Sync entry point for console_scripts: wraps the async backup scheduler."""
    return asyncio.run(_async_main())


if __name__ == "__main__":
    import sys

    sys.exit(main())
