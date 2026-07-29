#!/usr/bin/env python3
"""
Metrics collection system
Log-based + Prometheus monitoring for Palworld server performance tracking
"""

import asyncio
import psutil
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from pathlib import Path
import gc

from ..config_loader import PalworldConfig
from ..logging_setup import get_logger, log_server_event

# Prometheus metrics (module-level, registered once)
try:
    from prometheus_client import start_http_server, Gauge, Counter, Histogram, generate_latest

    # System metrics
    pal_cpu_percent = Gauge("pal_cpu_percent", "CPU usage percentage")
    pal_memory_percent = Gauge("pal_memory_percent", "Memory usage percentage")
    pal_memory_gb = Gauge("pal_memory_gb", "Memory usage in GB")
    pal_disk_percent = Gauge("pal_disk_percent", "Disk usage percentage")
    pal_disk_gb = Gauge("pal_disk_gb", "Disk usage in GB")
    pal_network_sent = Gauge("pal_network_bytes_sent", "Network bytes sent")
    pal_network_recv = Gauge("pal_network_bytes_recv", "Network bytes received")

    # Game server metrics
    pal_players_online = Gauge("pal_players_online", "Current players online")
    pal_max_players = Gauge("pal_max_players", "Maximum players")
    pal_server_uptime = Gauge("pal_server_uptime_seconds", "Server uptime in seconds")
    pal_server_running = Gauge("pal_server_running", "Server running (1=yes, 0=no)")
    pal_tps = Gauge("pal_tps", "Server TPS (ticks per second)")
    pal_world_size_mb = Gauge("pal_world_size_mb", "World save data size in MB")

    # Event counters
    pal_player_joins = Counter("pal_player_joins_total", "Total player joins")
    pal_player_leaves = Counter("pal_player_leaves_total", "Total player leaves")
    pal_backups_total = Counter("pal_backups_total", "Total backups created")
    pal_restarts_total = Counter("pal_restarts_total", "Total server restarts")
    pal_errors_total = Counter("pal_errors_total", "Total errors", ["type"])

    # API performance
    pal_api_duration = Histogram(
        "pal_api_request_duration_seconds",
        "API request duration in seconds",
        ["endpoint"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
    )

    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False


@dataclass
class SystemMetrics:
    """System metrics data structure"""

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
    """Game server metrics data structure"""

    timestamp: datetime = field(default_factory=datetime.now)
    players_online: int = 0
    max_players: int = 32
    server_uptime_seconds: float = 0.0
    tps: float = 0.0
    world_save_size_mb: float = 0.0
    api_response_time_ms: float = 0.0


class MetricsCollector:
    """Metrics collector for Palworld server monitoring.

    Supports two modes:
    - 'logs': Structured log output via structlog
    - 'prometheus': Prometheus HTTP endpoint on /metrics
    - 'both': Both logging and Prometheus
    """

    def __init__(self, config: PalworldConfig):
        self.config = config
        self.logger = get_logger("palworld.metrics")

        self.mode = config.monitoring.mode
        self.enable_logs = self.mode in ("logs", "both")
        self.enable_prometheus = self.mode in ("prometheus", "both") and _PROMETHEUS_AVAILABLE

        self.server_start_time = time.time()
        self.last_network_stats = psutil.net_io_counters()
        self._collection_task: Optional[asyncio.Task] = None
        self._prometheus_server_started = False
        self._running = False

        # Track last collection time to manage psutil resources
        self._last_collection_time = 0
        self._collection_interval = config.monitoring.metrics_interval

        # Event counters
        self._total_joins = 0
        self._total_leaves = 0
        self._total_errors = 0

    async def start_collection(self):
        """Start metrics collection (and Prometheus HTTP server if enabled)"""
        if self._running:
            self.logger.warning("Metrics collection already running")
            return

        self._running = True

        # Start Prometheus HTTP server if enabled
        if self.enable_prometheus and not self._prometheus_server_started:
            try:
                port = self.config.monitoring.dashboard_port
                start_http_server(port)
                self._prometheus_server_started = True
                self.logger.info("Prometheus metrics server started", port=port)
                # Set initial server_running state
                pal_server_running.set(1)
            except Exception as e:
                self.logger.error("Failed to start Prometheus HTTP server", error=str(e))

        self._collection_task = asyncio.create_task(self._collection_loop())
        log_server_event(
            self.logger, "metrics_start", f"Metrics collection started (mode={self.mode})"
        )

    async def stop_collection(self):
        """Stop metrics collection"""
        self._running = False

        if self._collection_task:
            self._collection_task.cancel()
            try:
                await self._collection_task
            except asyncio.CancelledError:
                pass

        if self.enable_prometheus:
            pal_server_running.set(0)

        log_server_event(self.logger, "metrics_stop", "Metrics collection stopped")

    async def _collection_loop(self):
        """Metrics collection loop"""
        interval = self.config.monitoring.metrics_interval

        while self._running:
            try:
                system_metrics = await self._collect_system_metrics()
                await self._process_system_metrics(system_metrics)

                # Update Prometheus metrics with latest system data
                if self.enable_prometheus:
                    self._update_prometheus_system(system_metrics)

                # Perform garbage collection periodically to prevent memory accumulation
                current_time = time.time()
                if current_time - self._last_collection_time > 300:  # Every 5 minutes
                    gc.collect()
                    self._last_collection_time = current_time

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Metrics collection error", error=str(e))
                if self.enable_prometheus:
                    pal_errors_total.labels(type="collection").inc()
                await asyncio.sleep(5)

    def _update_prometheus_system(self, metrics: SystemMetrics):
        """Update Prometheus gauges with system metrics"""
        try:
            pal_cpu_percent.set(metrics.cpu_percent)
            pal_memory_percent.set(metrics.memory_percent)
            pal_memory_gb.set(metrics.memory_usage_gb)
            pal_disk_percent.set(metrics.disk_percent)
            pal_disk_gb.set(metrics.disk_usage_gb)
            pal_network_sent.set(metrics.network_bytes_sent)
            pal_network_recv.set(metrics.network_bytes_recv)
        except Exception:
            pass  # Gracefully handle if prometheus_client isn't available

    def _update_prometheus_game(self, metrics: GameMetrics):
        """Update Prometheus gauges with game metrics"""
        try:
            pal_players_online.set(metrics.players_online)
            pal_max_players.set(metrics.max_players)
            pal_server_uptime.set(metrics.server_uptime_seconds)
            pal_tps.set(metrics.tps)
            pal_world_size_mb.set(metrics.world_save_size_mb)
        except Exception:
            pass

    async def _collect_system_metrics(self) -> SystemMetrics:
        """Collect system metrics"""
        cpu_percent = psutil.cpu_percent(interval=1)

        memory = psutil.virtual_memory()
        memory_usage_gb = memory.used / (1024**3)
        memory_percent = memory.percent

        disk = psutil.disk_usage(str(self.config.paths.server_dir))
        disk_usage_gb = disk.used / (1024**3)
        disk_percent = (disk.used / disk.total) * 100

        net_io = psutil.net_io_counters()

        load_avg = []
        try:
            load_avg = list(psutil.getloadavg())
        except AttributeError:
            pass

        return SystemMetrics(
            cpu_percent=cpu_percent,
            memory_usage_gb=memory_usage_gb,
            memory_percent=memory_percent,
            disk_usage_gb=disk_usage_gb,
            disk_percent=disk_percent,
            network_bytes_sent=net_io.bytes_sent,
            network_bytes_recv=net_io.bytes_recv,
            load_average=load_avg,
        )

    async def _process_system_metrics(self, metrics: SystemMetrics):
        """Process system metrics"""
        if self.enable_logs:
            self.logger.info(
                "System metrics",
                event_type="metrics",
                cpu_percent=round(metrics.cpu_percent, 1),
                memory_gb=round(metrics.memory_usage_gb, 2),
                memory_percent=round(metrics.memory_percent, 1),
                disk_gb=round(metrics.disk_usage_gb, 2),
                disk_percent=round(metrics.disk_percent, 1),
                network_sent_mb=round(metrics.network_bytes_sent / (1024**2), 1),
                network_recv_mb=round(metrics.network_bytes_recv / (1024**2), 1),
            )

    def collect_game_metrics_sync(
        self, players_data: Optional[List[Dict]] = None, server_info: Optional[Dict] = None
    ) -> GameMetrics:
        """Collect game metrics with external data"""
        players_online = len(players_data) if players_data else 0
        uptime = time.time() - self.server_start_time

        world_size_mb = 0.0
        save_dir = self.config.paths.server_dir / "Pal" / "Saved"
        if save_dir.exists():
            try:
                world_size_mb = sum(
                    f.stat().st_size for f in save_dir.rglob("*") if f.is_file()
                ) / (1024**2)
            except Exception:
                pass

        tps = 20.0
        if server_info and "tps" in server_info:
            tps = float(server_info["tps"])

        return GameMetrics(
            players_online=players_online,
            max_players=self.config.server.max_players,
            server_uptime_seconds=uptime,
            tps=tps,
            world_save_size_mb=world_size_mb,
            api_response_time_ms=0.0,
        )

    async def process_game_metrics(self, metrics: GameMetrics):
        """Process game metrics"""
        # Update Prometheus with game metrics
        if self.enable_prometheus:
            self._update_prometheus_game(metrics)

        if self.enable_logs:
            uptime_hours = metrics.server_uptime_seconds / 3600
            self.logger.info(
                "Game metrics",
                event_type="metrics",
                players_online=metrics.players_online,
                max_players=metrics.max_players,
                uptime_hours=round(uptime_hours, 2),
                tps=round(metrics.tps, 1),
                world_size_mb=round(metrics.world_save_size_mb, 1),
            )

    def record_api_call(self, endpoint: str, status_code: int, duration_ms: float):
        """Record API call metrics"""
        if self.enable_prometheus:
            try:
                pal_api_duration.labels(endpoint=endpoint).observe(duration_ms / 1000.0)
            except Exception:
                pass

        if self.enable_logs:
            status_category = "success" if 200 <= status_code < 300 else "error"
            self.logger.info(
                "API call",
                event_type="api_metrics",
                endpoint=endpoint,
                status_code=status_code,
                status_category=status_category,
                duration_ms=round(duration_ms, 1),
            )

    def record_backup_event(self, duration_seconds: float, size_bytes: int):
        """Record backup event metrics"""
        if self.enable_prometheus:
            try:
                pal_backups_total.inc()
            except Exception:
                pass

        if self.enable_logs:
            size_mb = size_bytes / (1024**2)
            self.logger.info(
                "Backup event",
                event_type="backup_metrics",
                duration_seconds=round(duration_seconds, 1),
                size_mb=round(size_mb, 1),
                timestamp=time.time(),
            )

    def record_player_event(self, event_type: str, player_name: str, player_count: int):
        """Record player join/leave events"""
        if self.enable_prometheus:
            try:
                if event_type == "join":
                    pal_player_joins.inc()
                    self._total_joins += 1
                elif event_type == "leave":
                    pal_player_leaves.inc()
                    self._total_leaves += 1
            except Exception:
                pass

        if self.enable_logs:
            self.logger.info(
                f"Player {event_type}",
                event_type="player_metrics",
                player_name=player_name,
                current_players=player_count,
                max_players=self.config.server.max_players,
            )

    def record_server_event(self, event_type: str, message: str, **kwargs):
        """Record server events"""
        if self.enable_prometheus:
            try:
                if event_type in ("restart", "stop"):
                    pal_restarts_total.inc()
            except Exception:
                pass

        if self.enable_logs:
            self.logger.info(
                f"Server {event_type}", event_type="server_metrics", message=message, **kwargs
            )

    def get_current_metrics_summary(self) -> Dict[str, Any]:
        """Get current metrics summary"""
        try:
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
                    "network_recv_mb": round(net_io.bytes_recv / (1024**2), 1),
                },
            }

        except Exception as e:
            self.logger.error("Failed to get metrics summary", error=str(e))
            return {"timestamp": time.time(), "error": str(e)}


_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector(config: Optional[PalworldConfig] = None) -> MetricsCollector:
    """Return global metrics collector instance"""
    global _metrics_collector

    if _metrics_collector is None:
        from ..config_loader import get_config

        _metrics_collector = MetricsCollector(config or get_config())

    return _metrics_collector


async def _async_main():
    """Standalone metrics collector mode for supervisor process."""
    from ..config_loader import get_config

    collector = MetricsCollector(get_config())
    await collector.start_collection()
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await collector.stop_collection()


def main():
    """Sync entry point: wraps _async_main for console_scripts / supervisor."""
    return asyncio.run(_async_main())


if __name__ == "__main__":
    import sys
    sys.exit(main())
