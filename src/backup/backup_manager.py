#!/usr/bin/env python3
"""
Enhanced backup manager with retention policies
Automatic backup scheduling and cleanup system
"""

import asyncio
import shutil
import tarfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from ..config_loader import get_config, PalworldConfig
from ..logging_setup import get_logger, log_backup_event


@dataclass
class BackupInfo:
    """Backup file information structure"""
    filename: str
    filepath: Path
    size_bytes: int
    created_time: datetime
    backup_type: str  # 'daily', 'weekly', 'monthly'


class EnhancedBackupManager:
    """Enhanced backup manager with config integration and retention policies"""
    
    def __init__(self, config: Optional[PalworldConfig] = None):
        """
        Initialize backup manager with config
        
        Args:
            config: Palworld configuration (loads default if None)
        """
        self.config = config or get_config()
        self.logger = get_logger("palworld.backup")
        
        # Path configuration from config_loader
        self.backup_dir = self.config.paths.backup_dir
        self.source_dir = self.config.paths.server_dir / "Pal" / "Saved"
        
        # Backup settings from config
        self.enabled = self.config.backup.enabled
        self.interval_seconds = self.config.backup.interval_seconds
        self.retention_days = self.config.backup.retention_days
        self.retention_weeks = self.config.backup.retention_weeks
        self.retention_months = self.config.backup.retention_months
        self.compress = self.config.backup.compress
        self.max_backups = self.config.backup.max_backups
        self.cleanup_interval = self.config.backup.cleanup_interval
        
        # Ensure backup directory exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Backup scheduler task
        self._backup_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start_backup_scheduler(self):
        """Start automatic backup scheduler"""
        if not self.enabled:
            self.logger.warning("Backup is disabled in configuration")
            return
        
        if self._running:
            self.logger.warning("Backup scheduler is already running")
            return
        
        self._running = True
        
        # Start backup creation task
        self._backup_task = asyncio.create_task(self._backup_loop())
        
        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        log_backup_event(
            self.logger, "scheduler_start",
            f"Backup scheduler started (interval: {self.interval_seconds}s, cleanup: {self.cleanup_interval}s)"
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
        
        log_backup_event(self.logger, "scheduler_stop", "Backup scheduler stopped")
    
    async def _backup_loop(self):
        """Main backup creation loop"""
        # Wait 10 minutes after start for server stabilization
        await asyncio.sleep(600)
        
        while self._running:
            try:
                current_time = datetime.now()
                backup_type = self._determine_backup_type(current_time)
                
                self.logger.info(f"Creating {backup_type} backup at {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
                
                result = await self.create_backup(f"{backup_type}_auto", backup_type)
                
                if result.get('success'):
                    log_backup_event(
                        self.logger, "backup_success",
                        f"{backup_type.capitalize()} backup created successfully",
                        filename=result.get('filename'),
                        size_mb=result.get('size_mb', 0),
                        duration_seconds=result.get('duration_seconds', 0)
                    )
                else:
                    log_backup_event(
                        self.logger, "backup_fail",
                        f"Failed to create {backup_type} backup: {result.get('error')}",
                        error=result.get('error')
                    )
                
                # Wait for next backup
                await asyncio.sleep(self.interval_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Backup loop error", error=str(e))
                await asyncio.sleep(300)  # Wait 5 minutes on error
    
    async def _cleanup_loop(self):
        """Backup cleanup loop"""
        # Initial cleanup after 30 minutes
        await asyncio.sleep(1800)
        
        while self._running:
            try:
                self.logger.info("Starting backup cleanup process")
                cleaned_count = self.cleanup_old_backups()
                
                if cleaned_count > 0:
                    log_backup_event(
                        self.logger, "cleanup_success",
                        f"Cleaned up {cleaned_count} old backup files"
                    )
                
                # Wait for next cleanup
                await asyncio.sleep(self.cleanup_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Cleanup loop error", error=str(e))
                await asyncio.sleep(3600)  # Wait 1 hour on error
    
    def _determine_backup_type(self, current_time: datetime) -> str:
        """
        Determine backup type based on current time
        
        Args:
            current_time: Current datetime
            
        Returns:
            Backup type: 'daily', 'weekly', or 'monthly'
        """
        # Monthly backup on 1st day of month at 02:00
        if current_time.day == 1 and current_time.hour == 2:
            return 'monthly'
        
        # Weekly backup on Sunday at 03:00
        if current_time.weekday() == 6 and current_time.hour == 3:
            return 'weekly'
        
        # Default to daily backup
        return 'daily'
    
    async def create_backup(self, name: str = None, backup_type: str = 'manual') -> Dict[str, Any]:
        """
        Create a backup with specified name and type
        
        Args:
            name: Backup name (auto-generated if None)
            backup_type: Type of backup ('daily', 'weekly', 'monthly', 'manual')
            
        Returns:
            Dictionary with backup result information
        """
        start_time = time.time()
        
        try:
            if not self.source_dir.exists():
                return {
                    'success': False,
                    'error': f'Source directory does not exist: {self.source_dir}'
                }
            
            # Generate backup filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            if name:
                backup_name = f"{name}_{timestamp}"
            else:
                backup_name = f"{backup_type}_backup_{timestamp}"
            
            backup_filename = f"{backup_name}.tar.gz" if self.compress else f"{backup_name}.tar"
            backup_path = self.backup_dir / backup_filename
            
            # Create backup archive
            await self._create_archive(backup_path, backup_type)
            
            duration_seconds = time.time() - start_time
            size_bytes = backup_path.stat().st_size
            size_mb = size_bytes / (1024 * 1024)
            
            return {
                'success': True,
                'filename': backup_filename,
                'filepath': str(backup_path),
                'size_bytes': size_bytes,
                'size_mb': round(size_mb, 2),
                'duration_seconds': round(duration_seconds, 2),
                'backup_type': backup_type
            }
            
        except Exception as e:
            duration_seconds = time.time() - start_time
            
            return {
                'success': False,
                'error': str(e),
                'duration_seconds': round(duration_seconds, 2)
            }
    
    async def _create_archive(self, backup_path: Path, backup_type: str):
        """
        Create backup archive (async wrapper for tar creation)
        
        Args:
            backup_path: Path for backup file
            backup_type: Type of backup for logging
        """
        def create_tar():
            compression = 'gz' if self.compress else ''
            mode = f'w:{compression}' if compression else 'w'
            
            with tarfile.open(backup_path, mode) as tar:
                # Add save data directory
                if self.source_dir.exists():
                    tar.add(self.source_dir, arcname='SaveGames')
                
                # Add server configuration files
                config_dir = self.config.paths.server_dir / "Pal" / "Saved" / "Config"
                if config_dir.exists():
                    tar.add(config_dir, arcname='Config')
        
        # Run tar creation in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, create_tar)
    
    def list_backups(self) -> List[BackupInfo]:
        """
        List all backup files with metadata
        
        Returns:
            List of BackupInfo objects
        """
        backups = []
        
        if not self.backup_dir.exists():
            return backups
        
        # Find all backup files
        patterns = ['*.tar.gz', '*.tar'] if self.compress else ['*.tar']
        backup_files = []
        
        for pattern in patterns:
            backup_files.extend(self.backup_dir.glob(pattern))
        
        for backup_file in backup_files:
            try:
                # Extract backup type from filename
                backup_type = 'manual'
                if 'daily' in backup_file.name:
                    backup_type = 'daily'
                elif 'weekly' in backup_file.name:
                    backup_type = 'weekly'
                elif 'monthly' in backup_file.name:
                    backup_type = 'monthly'
                
                backup_info = BackupInfo(
                    filename=backup_file.name,
                    filepath=backup_file,
                    size_bytes=backup_file.stat().st_size,
                    created_time=datetime.fromtimestamp(backup_file.stat().st_ctime),
                    backup_type=backup_type
                )
                
                backups.append(backup_info)
                
            except Exception as e:
                self.logger.warning(f"Failed to process backup file {backup_file}: {e}")
        
        # Sort by creation time (newest first)
        backups.sort(key=lambda x: x.created_time, reverse=True)
        
        return backups
    
    def cleanup_old_backups(self) -> int:
        """
        Clean up old backups based on retention policies
        
        Returns:
            Number of deleted backup files
        """
        if not self.backup_dir.exists():
            return 0
        
        backups = self.list_backups()
        now = datetime.now()
        deleted_count = 0
        
        # Calculate cutoff dates
        daily_cutoff = now - timedelta(days=self.retention_days)
        weekly_cutoff = now - timedelta(weeks=self.retention_weeks)
        monthly_cutoff = now - timedelta(days=self.retention_months * 30)
        
        # Group backups by type
        daily_backups = [b for b in backups if b.backup_type == 'daily']
        weekly_backups = [b for b in backups if b.backup_type == 'weekly']
        monthly_backups = [b for b in backups if b.backup_type == 'monthly']
        manual_backups = [b for b in backups if b.backup_type == 'manual']
        
        # Clean up daily backups
        for backup in daily_backups:
            if backup.created_time < daily_cutoff:
                try:
                    backup.filepath.unlink()
                    deleted_count += 1
                    self.logger.info(f"Deleted old daily backup: {backup.filename}")
                except Exception as e:
                    self.logger.error(f"Failed to delete daily backup {backup.filename}: {e}")
        
        # Clean up weekly backups
        for backup in weekly_backups:
            if backup.created_time < weekly_cutoff:
                try:
                    backup.filepath.unlink()
                    deleted_count += 1
                    self.logger.info(f"Deleted old weekly backup: {backup.filename}")
                except Exception as e:
                    self.logger.error(f"Failed to delete weekly backup {backup.filename}: {e}")
        
        # Clean up monthly backups
        for backup in monthly_backups:
            if backup.created_time < monthly_cutoff:
                try:
                    backup.filepath.unlink()
                    deleted_count += 1
                    self.logger.info(f"Deleted old monthly backup: {backup.filename}")
                except Exception as e:
                    self.logger.error(f"Failed to delete monthly backup {backup.filename}: {e}")
        
        # Clean up excess manual backups (keep only latest 20)
        if len(manual_backups) > 20:
            excess_manual = manual_backups[20:]
            for backup in excess_manual:
                try:
                    backup.filepath.unlink()
                    deleted_count += 1
                    self.logger.info(f"Deleted excess manual backup: {backup.filename}")
                except Exception as e:
                    self.logger.error(f"Failed to delete manual backup {backup.filename}: {e}")
        
        # Emergency cleanup if total backups exceed max_backups
        remaining_backups = self.list_backups()
        if len(remaining_backups) > self.max_backups:
            excess_count = len(remaining_backups) - self.max_backups
            # Delete oldest backups first
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
        """
        Get backup statistics and summary
        
        Returns:
            Dictionary with backup statistics
        """
        backups = self.list_backups()
        
        total_size = sum(backup.size_bytes for backup in backups)
        daily_count = len([b for b in backups if b.backup_type == 'daily'])
        weekly_count = len([b for b in backups if b.backup_type == 'weekly'])
        monthly_count = len([b for b in backups if b.backup_type == 'monthly'])
        manual_count = len([b for b in backups if b.backup_type == 'manual'])
        
        return {
            'total_backups': len(backups),
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'daily_backups': daily_count,
            'weekly_backups': weekly_count,
            'monthly_backups': monthly_count,
            'manual_backups': manual_count,
            'oldest_backup': backups[-1].created_time if backups else None,
            'newest_backup': backups[0].created_time if backups else None,
            'retention_policy': {
                'days': self.retention_days,
                'weeks': self.retention_weeks,
                'months': self.retention_months
            }
        }


# Global backup manager instance
_backup_manager: Optional[EnhancedBackupManager] = None


def get_backup_manager(config: Optional[PalworldConfig] = None) -> EnhancedBackupManager:
    """Return global backup manager instance"""
    global _backup_manager
    
    if _backup_manager is None:
        _backup_manager = EnhancedBackupManager(config)
    
    return _backup_manager


async def main():
    """Test backup manager functionality"""
    print("🚀 Enhanced backup manager test start")
    
    # Get backup manager with config
    manager = get_backup_manager()
    
    print(f"Configuration loaded:")
    print(f"  - Backup enabled: {manager.enabled}")
    print(f"  - Backup interval: {manager.interval_seconds} seconds")
    print(f"  - Retention: {manager.retention_days}d/{manager.retention_weeks}w/{manager.retention_months}m")
    print(f"  - Max backups: {manager.max_backups}")
    
    # Create test backup
    result = await manager.create_backup("test_enhanced")
    print(f"Test backup result: {result}")
    
    # Show backup statistics
    stats = manager.get_backup_statistics()
    print(f"Backup statistics: {stats}")
    
    # Test cleanup
    cleaned = manager.cleanup_old_backups()
    print(f"Cleaned up {cleaned} old backups")
    
    print("✅ Enhanced backup manager test complete!")


if __name__ == "__main__":
    asyncio.run(main())
