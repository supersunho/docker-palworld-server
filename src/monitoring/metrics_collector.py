#!/usr/bin/env python3
"""
Metrics collection system
Log-based monitoring for Palworld server performance tracking
"""

import asyncio
import psutil
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from pathlib import Path

from ..config_loader import PalworldConfig
from ..logging_setup import get_logger, log_server_event


@dataclass
class SystemMetrics:
    """System metrics data class"""
    timestamp: datetime = field(default_factory=datetime.now)
    cpu_percent: float = 0.0
    memory_usage_gb: float = 0.0
    memory_percent: float = 0.0
    disk_usage_gb: float = 0.0
    disk_percent: float = 0.0
    network_bytes_sent: int = 0
    network_bytes_recv: int = 0
    load_average: List[float] = field(default_factory=list)


@dataclass
class GameMetrics:
    """Game server metrics data class"""
    timestamp: datetime = field(default_factory=datetime.now)
    players_online: int = 0
    max_players: int = 32
    server_uptime_seconds: float = 0.0
    tps: float = 0.0  # Ticks Per Second
    world_save_size_mb: float = 0.0
    api_response_time_ms: float = 0.0


class MetricsCollector:
    """Main metrics collector class (log-based monitoring only)"""
    
    def __init__(self, config: PalworldConfig):
        self.config = config
        self.logger = get_logger("palworld.metrics")
        
        # Monitoring mode check (logs only)
        self.enable_logs = config.monitoring.mode in ['logs', 'both']
        
        # Collection state
        self.server_start_time = time.time()
        self.last_network_stats = psutil.net_io_counters()
        self._collection_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start_collection(self):
        """Start metrics collection"""
        if self._running:
            self.logger.warning("Metrics collection already running")
            return
        
        self._running = True
        
        # Start collection task
        self._collection_task = asyncio.create_task(self._collection_loop())
        log_server_event(self.logger, "metrics_start", "Log-based metrics collection started")
    
    async def stop_collection(self):
        """Stop metrics collection"""
        self._running = False
        
        if self._collection_task:
            self._collection_task.cancel()
            try:
                await self._collection_task
            except asyncio.CancelledError:
                pass
        
        log_server_event(self.logger, "metrics_stop", "Metrics collection stopped")
    
    async def _collection_loop(self):
        """Metrics collection loop"""
        interval = self.config.monitoring.metrics_interval
        
        while self._running:
            try:
                # Collect system metrics
                system_metrics = await self._collect_system_metrics()
                await self._process_system_metrics(system_metrics)
                
                # Game metrics collection (requires API client)
                # This part to be implemented with server_manager integration
                
                await asyncio.sleep(interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Metrics collection error", error=str(e))
                await asyncio.sleep(5)  # Short wait on error
    
    async def _collect_system_metrics(self) -> SystemMetrics:
        """Collect system metrics"""
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Memory info
        memory = psutil.virtual_memory()
        memory_usage_gb = memory.used / (1024**3)
        memory_percent = memory.percent
        
        # Disk info (based on server path)
        disk = psutil.disk_usage(str(self.config.paths.server_dir))
        disk_usage_gb = disk.used / (1024**3)
        disk_percent = (disk.used / disk.total) * 100
        
        # Network info
        net_io = psutil.net_io_counters()
        
        # Load average (Unix only)
        load_avg = []
        try:
            load_avg = list(psutil.getloadavg())
        except AttributeError:
            # Not supported on Windows
            pass
        
        return SystemMetrics(
            cpu_percent=cpu_percent,
            memory_usage_gb=memory_usage_gb,
            memory_percent=memory_percent,
            disk_usage_gb=disk_usage_gb,
            disk_percent=disk_percent,
            network_bytes_sent=net_io.bytes_sent,
            network_bytes_recv=net_io.bytes_recv,
            load_average=load_avg
        )
    
    async def _process_system_metrics(self, metrics: SystemMetrics):
        """Process system metrics (log-based monitoring only)"""
        # Log-based monitoring
        if self.enable_logs:
            self.logger.info(
                "📊 System metrics",
                event_type="metrics",
                cpu_percent=round(metrics.cpu_percent, 1),
                memory_gb=round(metrics.memory_usage_gb, 2),
                memory_percent=round(metrics.memory_percent, 1),
                disk_gb=round(metrics.disk_usage_gb, 2),
                disk_percent=round(metrics.disk_percent, 1),
                network_sent_mb=round(metrics.network_bytes_sent / (1024**2), 1),
                network_recv_mb=round(metrics.network_bytes_recv / (1024**2), 1)
            )
    
    def collect_game_metrics_sync(self, players_data: Optional[List[Dict]] = None,
                                 server_info: Optional[Dict] = None) -> GameMetrics:
        """Collect game metrics (sync, external data provided)"""
        players_online = len(players_data) if players_data else 0
        uptime = time.time() - self.server_start_time
        
        # Calculate world size
        world_size_mb = 0.0
        save_dir = self.config.paths.server_dir / "Pal" / "Saved"
        if save_dir.exists():
            try:
                world_size_mb = sum(
                    f.stat().st_size for f in save_dir.rglob("*") if f.is_file()
                ) / (1024**2)
            except Exception:
                pass
        
        # TPS from server info if available
        tps = 20.0  # default
        if server_info and 'tps' in server_info:
            tps = float(server_info['tps'])
        
        return GameMetrics(
            players_online=players_online,
            max_players=self.config.server.max_players,
            server_uptime_seconds=uptime,
            tps=tps,
            world_save_size_mb=world_size_mb,
            api_response_time_ms=0.0  # set by API client
        )
    
    async def process_game_metrics(self, metrics: GameMetrics):
        """Process game metrics (log-based monitoring only)"""
        # Log-based monitoring
        if self.enable_logs:
            uptime_hours = metrics.server_uptime_seconds / 3600
            self.logger.info(
                "🎮 Game metrics",
                event_type="metrics",
                players_online=metrics.players_online,
                max_players=metrics.max_players,
                uptime_hours=round(uptime_hours, 2),
                tps=round(metrics.tps, 1),
                world_size_mb=round(metrics.world_save_size_mb, 1)
            )
    
    def record_api_call(self, endpoint: str, status_code: int, duration_ms: float):
        """Record API call metrics (log-based only)"""
        if self.enable_logs:
            status_category = "success" if 200 <= status_code < 300 else "error"
            self.logger.info(
                "🔌 API call",
                event_type="api_metrics",
                endpoint=endpoint,
                status_code=status_code,
                status_category=status_category,
                duration_ms=round(duration_ms, 1)
            )
    
    def record_backup_event(self, duration_seconds: float, size_bytes: int):
        """Record backup event metrics (log-based only)"""
        if self.enable_logs:
            size_mb = size_bytes / (1024**2)
            self.logger.info(
                "💾 Backup event",
                event_type="backup_metrics",
                duration_seconds=round(duration_seconds, 1),
                size_mb=round(size_mb, 1),
                timestamp=time.time()
            )
    
    def record_player_event(self, event_type: str, player_name: str, player_count: int):
        """Record player join/leave events (log-based only)"""
        if self.enable_logs:
            self.logger.info(
                f"👤 Player {event_type}",
                event_type="player_metrics",
                player_name=player_name,
                current_players=player_count,
                max_players=self.config.server.max_players
            )
    
    def record_server_event(self, event_type: str, message: str, **kwargs):
        """Record server events (log-based only)"""
        if self.enable_logs:
            self.logger.info(
                f"🎮 Server {event_type}",
                event_type="server_metrics",
                message=message,
                **kwargs
            )
    
    def get_current_metrics_summary(self) -> Dict[str, Any]:
        """Get current metrics summary for external use"""
        try:
            # Collect current system metrics
            cpu_percent = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage(str(self.config.paths.server_dir))
            net_io = psutil.net_io_counters()
            
            uptime = time.time() - self.server_start_time
            
            return {
                "timestamp": time.time(),
                "uptime_seconds": uptime,
                "system": {
                    "cpu_percent": round(cpu_percent, 1),
                    "memory_percent": round(memory.percent, 1),
                    "memory_available_gb": round(memory.available / (1024**3), 2),
                    "disk_percent": round((disk.used / disk.total) * 100, 1),
                    "disk_free_gb": round(disk.free / (1024**3), 2),
                    "network_sent_mb": round(net_io.bytes_sent / (1024**2), 1),
                    "network_recv_mb": round(net_io.bytes_recv / (1024**2), 1)
                }
            }
            
        except Exception as e:
            self.logger.error("Failed to get metrics summary", error=str(e))
            return {
                "timestamp": time.time(),
                "error": str(e)
            }


# Global metrics collector instance
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector(config: Optional[PalworldConfig] = None) -> MetricsCollector:
    """Return global metrics collector instance"""
    global _metrics_collector
    
    if _metrics_collector is None:
        from ..config_loader import get_config
        _metrics_collector = MetricsCollector(config or get_config())
    
    return _metrics_collector


async def main():
    """Test run"""
    from ..config_loader import get_config
    
    config = get_config()
    collector = MetricsCollector(config)
    
    print("🚀 Log-based metrics collector test start")
    
    await collector.start_collection()
    
    # Run for 5 seconds
    await asyncio.sleep(5)
    
    # Test metrics summary
    summary = collector.get_current_metrics_summary()
    print(f"📊 Current metrics: {summary}")
    
    await collector.stop_collection()
    
    print("✅ Metrics collector test complete!")


if __name__ == "__main__":
    asyncio.run(main())
