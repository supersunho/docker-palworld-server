#!/usr/bin/env python3
"""
Backup management system for Palworld server
Automated backup scheduling, compression, and cleanup with ARM64 optimization
"""

import asyncio
import os
import tarfile
import gzip
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
import subprocess

from ..config_loader import PalworldConfig
from ..logging_setup import get_logger, log_backup_event, log_server_event


class BackupManager:
    """Palworld server backup management class"""
    
    def __init__(self, config: PalworldConfig):
        self.config = config
        self.logger = get_logger("palworld.backup")
        
        # Backup paths
        self.source_dir = config.paths.server_dir / "Pal" / "Saved"
        self.backup_dir = config.paths.backup_dir
        
        # Backup settings
        self.compression_enabled = config.backup.compress
        self.retention_days = config.backup.retention_days
        self.interval_seconds = config.backup.interval_seconds
        
        # Backup task management
        self._backup_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Ensure backup directory exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    async def start_backup_scheduler(self) -> None:
        """Start automated backup scheduler"""
        if not self.config.backup.enabled:
            self.logger.info("Backup system disabled in configuration")
            return
        
        if self._running:
            self.logger.warning("Backup scheduler already running")
            return
        
        self._running = True
        self._backup_task = asyncio.create_task(self._backup_loop())
        
        log_backup_event(
            self.logger, "backup_start", 
            "Backup scheduler started",
            interval_minutes=self.interval_seconds // 60,
            retention_days=self.retention_days
        )
    
    async def stop_backup_scheduler(self) -> None:
        """Stop automated backup scheduler"""
        self._running = False
        
        if self._backup_task:
            self._backup_task.cancel()
            try:
                await self._backup_task
            except asyncio.CancelledError:
                pass
        
        log_backup_event(self.logger, "backup_stop", "Backup scheduler stopped")
    
    async def _backup_loop(self) -> None:
        """Main backup scheduling loop"""
        while self._running:
            try:
                # Perform backup
                backup_result = await self.create_backup()
                
                if backup_result["success"]:
                    log_backup_event(
                        self.logger, "backup_complete",
                        backup_result["filename"],
                        size_mb=backup_result["size_mb"],
                        duration_seconds=backup_result["duration"]
                    )
                    
                    # Record metrics if available
                    try:
                        from ..monitoring.metrics_collector import get_metrics_collector
                        collector = get_metrics_collector()
                        collector.record_backup_event(
                            backup_result["duration"], 
                            backup_result["size_bytes"]
                        )
                    except ImportError:
                        pass  # Metrics collector not available
                
                else:
                    log_backup_event(
                        self.logger, "backup_fail",
                        error=backup_result.get("error", "Unknown error")
                    )
                
                # Cleanup old backups
                await self.cleanup_old_backups()
                
                # Wait for next backup interval
                await asyncio.sleep(self.interval_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Backup loop error", error=str(e))
                await asyncio.sleep(60)  # Wait 1 minute on error
    
    async def create_backup(self, custom_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a backup of the server data
        
        Args:
            custom_name: Custom backup filename (auto-generated if None)
            
        Returns:
            Dictionary with backup result information
        """
        start_time = time.time()
        
        # Check if source directory exists
        if not self.source_dir.exists():
            return {
                "success": False,
                "error": f"Source directory not found: {self.source_dir}"
            }
        
        # Generate backup filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if custom_name:
            backup_name = f"{custom_name}_{timestamp}"
        else:
            backup_name = f"palworld_backup_{timestamp}"
        
        # Add compression extension if enabled
        if self.compression_enabled:
            backup_filename = f"{backup_name}.tar.gz"
        else:
            backup_filename = f"{backup_name}.tar"
        
        backup_path = self.backup_dir / backup_filename
        
        try:
            # Create backup using tarfile (ARM64 optimized)
            compression_mode = "w:gz" if self.compression_enabled else "w"
            
            with tarfile.open(backup_path, compression_mode) as tar:
                # Add all files from source directory
                for item in self.source_dir.rglob("*"):
                    if item.is_file():
                        # Create relative path for archive
                        arcname = item.relative_to(self.source_dir.parent)
                        tar.add(item, arcname=arcname)
            
            # Calculate backup size and duration
            backup_size = backup_path.stat().st_size
            duration = time.time() - start_time
            
            return {
                "success": True,
                "filename": backup_filename,
                "path": str(backup_path),
                "size_bytes": backup_size,
                "size_mb": backup_size / (1024 * 1024),
                "duration": duration,
                "compression": self.compression_enabled
            }
            
        except Exception as e:
            # Clean up failed backup file
            if backup_path.exists():
                backup_path.unlink()
            
            return {
                "success": False,
                "error": str(e),
                "duration": time.time() - start_time
            }
    
    async def restore_backup(self, backup_filename: str, 
                           target_dir: Optional[Path] = None) -> bool:
        """
        Restore server data from backup
        
        Args:
            backup_filename: Name of backup file to restore
            target_dir: Target directory (uses default if None)
            
        Returns:
            Restoration success status
        """
        backup_path = self.backup_dir / backup_filename
        
        if not backup_path.exists():
            self.logger.error("Backup file not found", backup_file=backup_filename)
            return False
        
        if target_dir is None:
            target_dir = self.source_dir.parent
        
        try:
            log_backup_event(
                self.logger, "restore_start", 
                f"Starting restore from {backup_filename}"
            )
            
            # Extract backup
            with tarfile.open(backup_path, "r:*") as tar:
                tar.extractall(target_dir)
            
            log_backup_event(
                self.logger, "restore_complete", 
                f"Restore completed from {backup_filename}"
            )
            return True
            
        except Exception as e:
            log_backup_event(
                self.logger, "restore_fail", 
                f"Restore failed from {backup_filename}",
                error=str(e)
            )
            return False
    
    async def cleanup_old_backups(self) -> int:
        """
        Clean up old backup files based on retention policy
        
        Returns:
            Number of files deleted
        """
        if self.retention_days <= 0:
            return 0
        
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        deleted_count = 0
        total_size_freed = 0
        
        try:
            backup_files = list(self.backup_dir.glob("palworld_backup_*.tar*"))
            
            for backup_file in backup_files:
                file_time = datetime.fromtimestamp(backup_file.stat().st_mtime)
                
                if file_time < cutoff_date:
                    file_size = backup_file.stat().st_size
                    backup_file.unlink()
                    deleted_count += 1
                    total_size_freed += file_size
                    
                    self.logger.debug(
                        "Deleted old backup",
                        filename=backup_file.name,
                        age_days=(datetime.now() - file_time).days
                    )
            
            if deleted_count > 0:
                log_backup_event(
                    self.logger, "backup_cleanup",
                    f"Cleaned up {deleted_count} old backup files",
                    deleted_count=deleted_count,
                    size_freed_mb=total_size_freed / (1024 * 1024)
                )
            
            return deleted_count
            
        except Exception as e:
            self.logger.error("Backup cleanup error", error=str(e))
            return 0
    
    def list_backups(self) -> List[Dict[str, Any]]:
        """
        List all available backups with metadata
        
        Returns:
            List of backup information dictionaries
        """
        backups = []
        
        try:
            backup_files = sorted(
                self.backup_dir.glob("palworld_backup_*.tar*"),
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )
            
            for backup_file in backup_files:
                stat = backup_file.stat()
                
                backups.append({
                    "filename": backup_file.name,
                    "path": str(backup_file),
                    "size_bytes": stat.st_size,
                    "size_mb": stat.st_size / (1024 * 1024),
                    "created_time": datetime.fromtimestamp(stat.st_mtime),
                    "age_days": (datetime.now() - datetime.fromtimestamp(stat.st_mtime)).days,
                    "compressed": backup_file.suffix == ".gz"
                })
            
        except Exception as e:
            self.logger.error("Error listing backups", error=str(e))
        
        return backups
    
    def get_backup_stats(self) -> Dict[str, Any]:
        """
        Get backup system statistics
        
        Returns:
            Backup statistics dictionary
        """
        backups = self.list_backups()
        
        if not backups:
            return {
                "total_backups": 0,
                "total_size_mb": 0,
                "latest_backup": None,
                "oldest_backup": None
            }
        
        total_size = sum(backup["size_bytes"] for backup in backups)
        
        return {
            "total_backups": len(backups),
            "total_size_mb": total_size / (1024 * 1024),
            "total_size_bytes": total_size,
            "latest_backup": backups[0]["filename"],
            "latest_backup_time": backups[0]["created_time"],
            "oldest_backup": backups[-1]["filename"],
            "oldest_backup_time": backups[-1]["created_time"],
            "compression_enabled": self.compression_enabled,
            "retention_days": self.retention_days
        }


# Global backup manager instance
_backup_manager: Optional[BackupManager] = None


def get_backup_manager(config: Optional[PalworldConfig] = None) -> BackupManager:
    """Return global backup manager instance"""
    global _backup_manager
    
    if _backup_manager is None:
        from ..config_loader import get_config
        _backup_manager = BackupManager(config or get_config())
    
    return _backup_manager


async def main():
    """Test run"""
    from ..config_loader import get_config
    
    config = get_config()
    backup_manager = BackupManager(config)
    
    print("🚀 Backup manager test start")
    
    # Create test backup
    result = await backup_manager.create_backup("test_backup")
    
    if result["success"]:
        print(f"✅ Backup created: {result['filename']}")
        print(f"   Size: {result['size_mb']:.2f} MB")
        print(f"   Duration: {result['duration']:.2f} seconds")
    else:
        print(f"❌ Backup failed: {result['error']}")
    
    # List backups
    backups = backup_manager.list_backups()
    print(f"📦 Total backups: {len(backups)}")
    
    # Get stats
    stats = backup_manager.get_backup_stats()
    print(f"📊 Backup stats: {stats['total_size_mb']:.2f} MB total")
    
    print("✅ Backup manager test complete!")


if __name__ == "__main__":
    asyncio.run(main())
