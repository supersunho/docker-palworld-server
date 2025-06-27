#!/usr/bin/env python3
"""
Prometheus integration module
Based on search results using aiohttp-prometheus-exporter and prometheus-client integration
"""

import asyncio
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path

from aiohttp import web
from aiohttp_prometheus_exporter.handler import metrics
from aiohttp_prometheus_exporter.middleware import prometheus_middleware_factory
from prometheus_client import (
    Counter, Gauge, Histogram, Info, Summary,
    CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
)

from config_loader import PalworldConfig
from logging_setup import get_logger


class PalworldPrometheusMetrics:
    """Palworld dedicated Prometheus metrics class"""
    
    def __init__(self, registry: Optional[CollectorRegistry] = None):
        """
        Initialize Prometheus metrics
        
        Args:
            registry: Custom registry (uses default registry if None)
        """
        self.registry = registry
        
        # Server information metrics
        self.server_info = Info(
            'palworld_server_info', 
            'Palworld server information',
            registry=registry
        )
        
        # Player metrics
        self.players_online = Gauge(
            'palworld_players_online_count', 
            'Current online player count',
            registry=registry
        )
        
        self.players_max = Gauge(
            'palworld_players_max_count', 
            'Maximum player count',
            registry=registry
        )
        
        self.player_connections_total = Counter(
            'palworld_player_connections_total',
            'Total player connections',
            ['event_type'],  # join, leave, kick, ban
            registry=registry
        )
        
        # Server performance metrics
        self.server_uptime_seconds = Gauge(
            'palworld_server_uptime_seconds',
            'Server uptime in seconds',
            registry=registry
        )
        
        self.server_tps = Gauge(
            'palworld_server_tps',
            'Server TPS (Ticks Per Second)',
            registry=registry
        )
        
        self.world_size_bytes = Gauge(
            'palworld_world_size_bytes',
            'World file size in bytes',
            registry=registry
        )
        
        # System resource metrics
        self.cpu_usage_percent = Gauge(
            'palworld_cpu_usage_percent',
            'CPU usage percentage',
            registry=registry
        )
        
        self.memory_usage_bytes = Gauge(
            'palworld_memory_usage_bytes',
            'Memory usage in bytes',
            registry=registry
        )
        
        self.memory_usage_percent = Gauge(
            'palworld_memory_usage_percent',
            'Memory usage percentage',
            registry=registry
        )
        
        self.disk_usage_bytes = Gauge(
            'palworld_disk_usage_bytes',
            'Disk usage in bytes',
            registry=registry
        )
        
        self.disk_usage_percent = Gauge(
            'palworld_disk_usage_percent',
            'Disk usage percentage',
            registry=registry
        )
        
        # Network metrics
        self.network_bytes_sent_total = Counter(
            'palworld_network_bytes_sent_total',
            'Total network bytes sent',
            registry=registry
        )
        
        self.network_bytes_received_total = Counter(
            'palworld_network_bytes_received_total',
            'Total network bytes received',
            registry=registry
        )
        
        # API metrics (based on search results)
        self.api_requests_total = Counter(
            'palworld_api_requests_total',
            'Total API requests',
            ['endpoint', 'method', 'status_code'],
            registry=registry
        )
        
        self.api_request_duration_seconds = Histogram(
            'palworld_api_request_duration_seconds',
            'API request processing time in seconds',
            ['endpoint', 'method'],
            buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
            registry=registry
        )
        
        # Backup metrics
        self.backup_duration_seconds = Histogram(
            'palworld_backup_duration_seconds',
            'Backup processing time in seconds',
            buckets=[10, 30, 60, 120, 300, 600, 1800],
            registry=registry
        )
        
        self.backup_size_bytes = Gauge(
            'palworld_backup_size_bytes',
            'Backup file size in bytes',
            registry=registry
        )
        
        self.backup_operations_total = Counter(
            'palworld_backup_operations_total',
            'Total backup operations',
            ['result'],  # success, failure
            registry=registry
        )
        
        self.last_backup_timestamp = Gauge(
            'palworld_last_backup_timestamp',
            'Last successful backup timestamp',
            registry=registry
        )
        
        # SteamCMD metrics
        self.steamcmd_operations_total = Counter(
            'palworld_steamcmd_operations_total',
            'Total SteamCMD operations',
            ['operation', 'result'],  # operation: download, update; result: success, failure
            registry=registry
        )
        
        self.steamcmd_duration_seconds = Histogram(
            'palworld_steamcmd_duration_seconds',
            'SteamCMD operation processing time in seconds',
            ['operation'],
            buckets=[30, 60, 120, 300, 600, 1200, 1800],
            registry=registry
        )


class PrometheusIntegration:
    """Prometheus integration management class"""
    
    def __init__(self, config: PalworldConfig):
        self.config = config
        self.logger = get_logger("palworld.prometheus")
        
        # Create custom registry (separate from default registry)
        self.registry = CollectorRegistry()
        
        # Metrics instance
        self.metrics = PalworldPrometheusMetrics(self.registry)
        
        # Web app (for metrics endpoint)
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        
        # Last network statistics (for delta calculation)
        self._last_network_sent = 0
        self._last_network_recv = 0
    
    def setup_aiohttp_app(self, app: web.Application, app_name: str = "palworld") -> web.Application:
        """
        Setup Prometheus middleware for aiohttp app (based on search results)
        
        Args:
            app: aiohttp application
            app_name: Application name (for metric labels)
            
        Returns:
            Configured aiohttp application
        """
        # Add aiohttp-prometheus-exporter middleware
        app.middlewares.append(prometheus_middleware_factory())
        
        # Add default metrics endpoint
        app.router.add_get("/metrics", metrics())
        
        # Add custom metrics endpoint
        app.router.add_get("/metrics/palworld", self._custom_metrics_handler)
        
        self.logger.info(
            "🔧 aiohttp Prometheus middleware setup complete",
            app_name=app_name,
            endpoints=["/metrics", "/metrics/palworld"]
        )
        
        return app
    
    async def _custom_metrics_handler(self, request: web.Request) -> web.Response:
        """Custom metrics endpoint handler"""
        try:
            output = generate_latest(self.registry)
            return web.Response(
                body=output,
                content_type=CONTENT_TYPE_LATEST
            )
        except Exception as e:
            self.logger.error("Custom metrics generation failed", error=str(e))
            return web.Response(
                text=f"Metrics generation error: {e}",
                status=500
            )
    
    async def start_metrics_server(self, port: Optional[int] = None) -> None:
        """
        Start independent metrics server
        
        Args:
            port: Metrics server port (gets from config if None)
        """
        if not port:
            port = self.config.monitoring.dashboard_port
        
        # Create metrics-only app
        self.app = web.Application()
        
        # Default metrics endpoint
        self.app.router.add_get("/metrics", self._custom_metrics_handler)
        
        # Health check endpoint
        self.app.router.add_get("/health", self._health_check_handler)
        
        # Start server
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        site = web.TCPSite(
            self.runner,
            self.config.rest_api.host,
            port
        )
        await site.start()
        
        self.logger.info(
            "📊 Prometheus metrics server started",
            host=self.config.rest_api.host,
            port=port,
            endpoints=["/metrics", "/health"]
        )
    
    async def _health_check_handler(self, request: web.Request) -> web.Response:
        """Health check handler"""
        health_data = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "metrics_registry": "active",
            "config_monitoring_mode": self.config.monitoring.mode
        }
        return web.json_response(health_data)
    
    async def stop_metrics_server(self) -> None:
        """Stop metrics server"""
        if self.runner:
            await self.runner.cleanup()
            self.logger.info("📊 Prometheus metrics server stopped")
    
    def init_server_info(self, server_info: Dict[str, Any]) -> None:
        """Initialize server information metrics"""
        self.metrics.server_info.info({
            'server_name': server_info.get('name', 'Unknown'),
            'version': server_info.get('version', 'Unknown'),
            'max_players': str(server_info.get('max_players', 0)),
            'monitoring_mode': self.config.monitoring.mode,
            'backup_enabled': str(self.config.backup.enabled),
            'discord_enabled': str(self.config.discord.enabled)
        })
        
        # Set maximum player count
        self.metrics.players_max.set(server_info.get('max_players', 0))
    
    def update_system_metrics(self, cpu_percent: float, memory_usage_bytes: int, 
                            memory_percent: float, disk_usage_bytes: int, 
                            disk_percent: float, network_sent: int, network_recv: int) -> None:
        """Update system metrics"""
        self.metrics.cpu_usage_percent.set(cpu_percent)
        self.metrics.memory_usage_bytes.set(memory_usage_bytes)
        self.metrics.memory_usage_percent.set(memory_percent)
        self.metrics.disk_usage_bytes.set(disk_usage_bytes)
        self.metrics.disk_usage_percent.set(disk_percent)
        
        # Network counter (delta calculation)
        if self._last_network_sent > 0:
            sent_diff = network_sent - self._last_network_sent
            if sent_diff > 0:
                self.metrics.network_bytes_sent_total._value._value += sent_diff
        
        if self._last_network_recv > 0:
            recv_diff = network_recv - self._last_network_recv
            if recv_diff > 0:
                self.metrics.network_bytes_received_total._value._value += recv_diff
        
        self._last_network_sent = network_sent
        self._last_network_recv = network_recv
    
    def update_game_metrics(self, players_online: int, uptime_seconds: float, 
                           tps: float, world_size_bytes: int) -> None:
        """Update game metrics"""
        self.metrics.players_online.set(players_online)
        self.metrics.server_uptime_seconds.set(uptime_seconds)
        self.metrics.server_tps.set(tps)
        self.metrics.world_size_bytes.set(world_size_bytes)
    
    def record_player_event(self, event_type: str) -> None:
        """Record player event"""
        self.metrics.player_connections_total.labels(event_type=event_type).inc()
    
    def record_api_request(self, endpoint: str, method: str, status_code: int, 
                          duration_seconds: float) -> None:
        """Record API request metrics"""
        self.metrics.api_requests_total.labels(
            endpoint=endpoint,
            method=method,
            status_code=str(status_code)
        ).inc()
        
        self.metrics.api_request_duration_seconds.labels(
            endpoint=endpoint,
            method=method
        ).observe(duration_seconds)
    
    def record_backup_event(self, success: bool, duration_seconds: float, 
                           size_bytes: int = 0) -> None:
        """Record backup event metrics"""
        result = "success" if success else "failure"
        
        self.metrics.backup_operations_total.labels(result=result).inc()
        self.metrics.backup_duration_seconds.observe(duration_seconds)
        
        if success:
            self.metrics.backup_size_bytes.set(size_bytes)
            self.metrics.last_backup_timestamp.set(time.time())
    
    def record_steamcmd_event(self, operation: str, success: bool, 
                             duration_seconds: float) -> None:
        """Record SteamCMD event metrics"""
        result = "success" if success else "failure"
        
        self.metrics.steamcmd_operations_total.labels(
            operation=operation,
            result=result
        ).inc()
        
        self.metrics.steamcmd_duration_seconds.labels(
            operation=operation
        ).observe(duration_seconds)


class PrometheusConfig:
    """Prometheus configuration file generation class"""
    
    def __init__(self, config: PalworldConfig):
        self.config = config
        self.logger = get_logger("palworld.prometheus.config")
    
    def generate_prometheus_yml(self, output_path: Path) -> bool:
        """
        Generate prometheus.yml configuration file
        
        Args:
            output_path: Output file path
            
        Returns:
            Generation success status
        """
        try:
            prometheus_config = f"""
# Prometheus configuration file (for Palworld server)
# Auto-generated - {datetime.now().isoformat()}

global:
  scrape_interval: {self.config.monitoring.metrics_interval}s
  evaluation_interval: {self.config.monitoring.metrics_interval}s
  external_labels:
    palworld_server: '{self.config.server.name}'

# Rule file loading (alert rules)
rule_files:
  - "palworld_alerts.yml"

# Scraping job configuration
scrape_configs:
  # Palworld server metrics
  - job_name: 'palworld-server'
    static_configs:
      - targets: ['{self.config.rest_api.host}:{self.config.monitoring.dashboard_port}']
    scrape_interval: {self.config.monitoring.metrics_interval}s
    metrics_path: '/metrics/palworld'
    scrape_timeout: 10s
    
  # aiohttp default metrics
  - job_name: 'palworld-aiohttp'
    static_configs:
      - targets: ['{self.config.rest_api.host}:{self.config.monitoring.dashboard_port}']
    scrape_interval: {self.config.monitoring.metrics_interval}s
    metrics_path: '/metrics'
    scrape_timeout: 10s

# Alertmanager configuration (for Discord notifications)
alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093
"""
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(prometheus_config.strip(), encoding='utf-8')
            
            self.logger.info(
                "📝 prometheus.yml generation complete",
                output_path=str(output_path)
            )
            return True
            
        except Exception as e:
            self.logger.error("prometheus.yml generation failed", error=str(e))
            return False
    
    def generate_alerts_yml(self, output_path: Path) -> bool:
        """
        Generate alert rules file
        
        Args:
            output_path: Output file path
            
        Returns:
            Generation success status
        """
        try:
            alerts_config = f"""
# Palworld server alert rules
# Auto-generated - {datetime.now().isoformat()}

groups:
  - name: palworld_server_alerts
    rules:
      # Server down detection
      - alert: PalworldServerDown
        expr: up{{job="palworld-server"}} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Palworld server is down"
          description: "{{{{ $labels.instance }}}} server has been unresponsive for more than 1 minute"

      # High CPU usage
      - alert: HighCPUUsage
        expr: palworld_cpu_usage_percent > 80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High CPU usage detected"
          description: "CPU usage is {{{{ $value }}}}% for more than 5 minutes (threshold: 80%)"

      # High memory usage
      - alert: HighMemoryUsage
        expr: palworld_memory_usage_percent > 90
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "High memory usage detected"
          description: "Memory usage is {{{{ $value }}}}% exceeding 90% threshold"

      # Low disk space
      - alert: LowDiskSpace
        expr: palworld_disk_usage_percent > 85
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Low disk space"
          description: "Disk usage is {{{{ $value }}}}% exceeding 85% threshold"

      # Low TPS
      - alert: LowServerTPS
        expr: palworld_server_tps < 15
        for: 3m
        labels:
          severity: warning
        annotations:
          summary: "Server performance degradation detected"
          description: "Server TPS is {{{{ $value }}}} below 15 for more than 3 minutes"

      # Backup failure
      - alert: BackupFailure
        expr: increase(palworld_backup_operations_total{{result="failure"}}[1h]) > 0
        labels:
          severity: warning
        annotations:
          summary: "Backup failure detected"
          description: "Backup failures occurred in the last hour"

      # Near max players
      - alert: NearMaxPlayers
        expr: palworld_players_online_count / palworld_players_max_count > 0.9
        for: 1m
        labels:
          severity: info
        annotations:
          summary: "Player count near maximum"
          description: "Current player count exceeds 90% of maximum capacity"
"""
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(alerts_config.strip(), encoding='utf-8')
            
            self.logger.info(
                "📝 palworld_alerts.yml generation complete",
                output_path=str(output_path)
            )
            return True
            
        except Exception as e:
            self.logger.error("Alert rules file generation failed", error=str(e))
            return False


# Global Prometheus integration instance
_prometheus_integration: Optional[PrometheusIntegration] = None


def get_prometheus_integration(config: Optional[PalworldConfig] = None) -> PrometheusIntegration:
    """Return global Prometheus integration instance"""
    global _prometheus_integration
    
    if _prometheus_integration is None:
        from config_loader import get_config
        _prometheus_integration = PrometheusIntegration(config or get_config())
    
    return _prometheus_integration


async def main():
    """Test run"""
    from config_loader import get_config
    
    config = get_config()
    prometheus = PrometheusIntegration(config)
    
    print("🚀 Prometheus integration test start")
    
    # Initialize server information
    prometheus.init_server_info({
        'name': config.server.name,
        'version': '1.0.0',
        'max_players': config.server.max_players
    })
    
    # Start metrics server
    await prometheus.start_metrics_server()
    
    # Record test metrics
    prometheus.update_system_metrics(50.0, 8589934592, 75.0, 21474836480, 45.0, 1024000, 2048000)
    prometheus.update_game_metrics(5, 3600.0, 19.8, 1073741824)
    prometheus.record_player_event("join")
    
    print(f"📊 Metrics server running: http://localhost:{config.monitoring.dashboard_port}/metrics")
    
    # Run for 5 seconds
    await asyncio.sleep(5)
    
    await prometheus.stop_metrics_server()
    
    print("✅ Prometheus integration test complete!")


if __name__ == "__main__":
    asyncio.run(main())
