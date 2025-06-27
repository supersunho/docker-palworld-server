#!/usr/bin/env python3
"""
Metrics collection system
Reflecting user's dual monitoring requirements (logs + prometheus)
"""

import asyncio
import psutil
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from pathlib import Path
from monitoring.prometheus_integration import get_prometheus_integration

# Prometheus metrics (optional import)
try:
    from prometheus_client import Counter, Gauge, Histogram, Info, start_http_server
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

from config_loader import PalworldConfig
from logging_setup import get_logger, log_server_event


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


class PrometheusMetrics:
    """Prometheus metrics definition class"""
    
    def __init__(self):
        if not PROMETHEUS_AVAILABLE:
            return
        
        # System metrics
        self.cpu_usage = Gauge('palworld_cpu_usage_percent', 'CPU usage percent')
        self.memory_usage = Gauge('palworld_memory_usage_bytes', 'Memory usage bytes')
        self.memory_percent = Gauge('palworld_memory_usage_percent', 'Memory usage percent')
        self.disk_usage = Gauge('palworld_disk_usage_bytes', 'Disk usage bytes')
        self.disk_percent = Gauge('palworld_disk_usage_percent', 'Disk usage percent')
        
        # Network metrics
        self.network_sent = Counter('palworld_network_bytes_sent_total', 'Bytes sent')
        self.network_recv = Counter('palworld_network_bytes_received_total', 'Bytes received')
        
        # Game metrics
        self.players_online = Gauge('palworld_players_online', 'Online player count')
        self.max_players = Gauge('palworld_max_players', 'Max player count')
        self.server_uptime = Gauge('palworld_uptime_seconds', 'Server uptime')
        self.tps = Gauge('palworld_tps', 'Ticks Per Second')
        self.world_size = Gauge('palworld_world_size_bytes', 'World size')
        
        # API metrics
        self.api_response_time = Histogram(
            'palworld_api_response_time_seconds',
            'API response time',
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
        )
        self.api_requests_total = Counter(
            'palworld_api_requests_total',
            'Total API requests',
            ['endpoint', 'status']
        )
        
        # Backup metrics
        self.backup_duration = Histogram(
            'palworld_backup_duration_seconds',
            'Backup duration seconds',
            buckets=[10, 30, 60, 120, 300, 600]
        )
        self.backup_size = Gauge('palworld_backup_size_bytes', 'Backup file size')
        self.last_backup_timestamp = Gauge('palworld_last_backup_timestamp', 'Last backup time')
        
        # Server info
        self.server_info = Info('palworld_server_info', 'Server info')
    
    def update_system_metrics(self, metrics: SystemMetrics):
        """Update system metrics"""
        if not PROMETHEUS_AVAILABLE:
            return
        
        self.cpu_usage.set(metrics.cpu_percent)
        self.memory_usage.set(metrics.memory_usage_gb * 1024**3)  # GB to bytes
        self.memory_percent.set(metrics.memory_percent)
        self.disk_usage.set(metrics.disk_usage_gb * 1024**3)  # GB to bytes
        self.disk_percent.set(metrics.disk_percent)
        
        # Network is cumulative, so only add difference
        self.network_sent._value._value = metrics.network_bytes_sent
        self.network_recv._value._value = metrics.network_bytes_recv
    
    def update_game_metrics(self, metrics: GameMetrics):
        """Update game metrics"""
        if not PROMETHEUS_AVAILABLE:
            return
        
        self.players_online.set(metrics.players_online)
        self.max_players.set(metrics.max_players)
        self.server_uptime.set(metrics.server_uptime_seconds)
        self.tps.set(metrics.tps)
        self.world_size.set(metrics.world_save_size_mb * 1024**2)  # MB to bytes


class MetricsCollector:
    """Main metrics collector class"""
    
    def __init__(self, config: PalworldConfig):
        self.config = config
        self.logger = get_logger("palworld.metrics")
        
        # Monitoring mode check
        self.enable_logs = config.monitoring.mode in ['logs', 'both']
        self.enable_prometheus = config.monitoring.mode in ['prometheus', 'both']
        
        # Prometheus metrics (if enabled)
        self.prometheus_metrics: Optional[PrometheusMetrics] = None
        if self.enable_prometheus and PROMETHEUS_AVAILABLE:
            self.prometheus_metrics = PrometheusMetrics()
            self.logger.info("📊 Prometheus metrics enabled")
        elif self.enable_prometheus and not PROMETHEUS_AVAILABLE:
            self.logger.warning("⚠️ Prometheus library not found, switching to log mode")
            self.enable_prometheus = False
            self.enable_logs = True
        
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
        
        # Start Prometheus HTTP server (if enabled)
        if self.enable_prometheus and self.prometheus_metrics:
            try:
                start_http_server(self.config.monitoring.dashboard_port)
                log_server_event(
                    self.logger, "metrics_start", 
                    f"Prometheus metrics server started",
                    port=self.config.monitoring.dashboard_port
                )
            except Exception as e:
                self.logger.error("Failed to start Prometheus server", error=str(e))
        
        # Start collection task
        self._collection_task = asyncio.create_task(self._collection_loop())
        log_server_event(self.logger, "metrics_start", "Metrics collection started")
    
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
        """Process system metrics"""
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
        
        # Prometheus metrics update
        if self.enable_prometheus and self.prometheus_metrics:
            self.prometheus_metrics.update_system_metrics(metrics)
    
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
        """Process game metrics"""
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
        
        # Prometheus metrics update
        if self.enable_prometheus and self.prometheus_metrics:
            self.prometheus_metrics.update_game_metrics(metrics)
    
    def record_api_call(self, endpoint: str, status_code: int, duration_ms: float):
        """Record API call metrics"""
        if self.enable_prometheus and self.prometheus_metrics:
            # Record response time (seconds)
            self.prometheus_metrics.api_response_time.observe(duration_ms / 1000)
            
            # Increment request counter
            status_category = "success" if 200 <= status_code < 300 else "error"
            self.prometheus_metrics.api_requests_total.labels(
                endpoint=endpoint, 
                status=status_category
            ).inc()
    
    def record_backup_event(self, duration_seconds: float, size_bytes: int):
        """Record backup event metrics"""
        if self.enable_prometheus and self.prometheus_metrics:
            self.prometheus_metrics.backup_duration.observe(duration_seconds)
            self.prometheus_metrics.backup_size.set(size_bytes)
            self.prometheus_metrics.last_backup_timestamp.set(time.time())


# Global metrics collector instance
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector(config: Optional[PalworldConfig] = None) -> MetricsCollector:
    """Return global metrics collector instance"""
    global _metrics_collector
    
    if _metrics_collector is None:
        from config_loader import get_config
        _metrics_collector = MetricsCollector(config or get_config())
    
    return _metrics_collector


async def main():
    """Test run"""
    from config_loader import get_config
    
    config = get_config()
    collector = MetricsCollector(config)
    
    print("🚀 Metrics collector test start")
    
    await collector.start_collection()
    
    # Run for 5 seconds
    await asyncio.sleep(5)
    
    await collector.stop_collection()
    
    print("✅ Metrics collector test complete!")


if __name__ == "__main__":
    asyncio.run(main())
