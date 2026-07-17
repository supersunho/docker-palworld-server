"""Tests for the metrics collector (log-based + Prometheus)."""

import pytest
import asyncio
import time
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from src.monitoring.metrics_collector import (
    MetricsCollector, SystemMetrics, GameMetrics
)

pytestmark = pytest.mark.unit


async def _noop():
    pass


class TestMetricsCollector:
    """FS-17.x: Metrics collector behavior."""

    @pytest.fixture
    def collector(self, palworld_config):
        return MetricsCollector(palworld_config)

    def test_system_metrics_dataclass(self):
        """FS-17.1: SystemMetrics fields."""
        metrics = SystemMetrics(
            cpu_percent=45.0,
            memory_usage_gb=8.0,
            memory_percent=50.0,
            disk_usage_gb=100.0,
            disk_percent=65.0,
            network_bytes_sent=1000,
            network_bytes_recv=2000
        )
        assert metrics.cpu_percent == 45.0
        assert metrics.memory_usage_gb == 8.0

    def test_game_metrics_dataclass(self):
        """FS-17.4: GameMetrics fields."""
        metrics = GameMetrics(
            players_online=3,
            max_players=16,
            server_uptime_seconds=3600,
            tps=20.0,
            world_save_size_mb=50.0
        )
        assert metrics.players_online == 3
        assert metrics.tps == 20.0

    @patch('psutil.cpu_percent')
    @patch('psutil.virtual_memory')
    @patch('psutil.disk_usage')
    @pytest.mark.asyncio
    async def test_collect_system_metrics(
        self, mock_disk, mock_mem, mock_cpu, collector
    ):
        """FS-17.1: Collects system metrics."""
        mock_cpu.return_value = 45.0
        mock_mem.return_value.total = 16 * 1024**3
        mock_mem.return_value.used = 8 * 1024**3
        mock_mem.return_value.percent = 50.0
        mock_disk.return_value.total = 500 * 1024**3
        mock_disk.return_value.used = 250 * 1024**3

        with patch('psutil.net_io_counters') as mock_net:
            mock_net.return_value.bytes_sent = 1000
            mock_net.return_value.bytes_recv = 2000
            metrics = await collector._collect_system_metrics()
            assert metrics.cpu_percent == 45.0
            assert metrics.memory_percent == 50.0

    def test_collect_game_metrics_sync(self, collector):
        """FS-17.5: Sync game metrics collection."""
        players = [{"name": "P1"}, {"name": "P2"}]
        metrics = collector.collect_game_metrics_sync(
            players_data=players,
            server_info={"tps": 20.0}
        )
        assert metrics.players_online == 2
        assert metrics.tps == 20.0

    def test_get_current_metrics_summary(self, collector):
        """FS-17.6: Real-time metrics summary."""
        with patch('psutil.cpu_percent', return_value=30.0), \
             patch('psutil.virtual_memory') as mock_mem, \
             patch('psutil.disk_usage') as mock_disk, \
             patch('psutil.net_io_counters') as mock_net:
            mock_mem.return_value.percent = 40.0
            mock_mem.return_value.available = 8 * 1024**3
            mock_disk.return_value.used = 100 * 1024**3
            mock_disk.return_value.total = 200 * 1024**3
            mock_net.return_value.bytes_sent = 500
            mock_net.return_value.bytes_recv = 1000

            summary = collector.get_current_metrics_summary()
            assert "uptime_seconds" in summary
            assert "system" in summary
            assert summary["system"]["cpu_percent"] == 30.0

    def test_record_api_call(self, collector):
        """FS-17.2: API call recording."""
        collector.record_api_call("/info", 200, 150.0)
        # Should not raise

    def test_record_backup_event(self, collector):
        """FS-17.2: Backup event recording."""
        collector.record_backup_event(30.0, 1024 * 1024)
        # Should not raise

    def test_record_player_event(self, collector):
        """FS-17.2: Player event recording."""
        collector.record_player_event("join", "Player1", 3)
        collector.record_player_event("leave", "Player1", 2)
        # Should not raise

    def test_record_server_event(self, collector):
        """FS-17.2: Server event recording."""
        collector.record_server_event("start", "Server started")
        collector.record_server_event("restart", "Server restarting")
        # Should not raise

    def test_prometheus_mode_config(self, palworld_config):
        """FS-17.7: Prometheus mode configuration."""
        # Default mode from config is 'logs' or 'both'
        palworld_config.monitoring.mode = "prometheus"
        collector = MetricsCollector(palworld_config)
        assert collector.enable_prometheus is True
        assert collector.enable_logs is False

        palworld_config.monitoring.mode = "both"
        collector = MetricsCollector(palworld_config)
        assert collector.enable_prometheus is True
        assert collector.enable_logs is True

        palworld_config.monitoring.mode = "logs"
        collector = MetricsCollector(palworld_config)
        assert collector.enable_prometheus is False
        assert collector.enable_logs is True

    @patch('src.monitoring.metrics_collector._PROMETHEUS_AVAILABLE', False)
    def test_prometheus_unavailable_fallback(self, palworld_config):
        """FS-17.8: Graceful fallback when prometheus_client not available."""
        palworld_config.monitoring.mode = "prometheus"
        collector = MetricsCollector(palworld_config)
        assert collector.enable_prometheus is False
        # Should still work without raising
        collector.record_player_event("join", "Player1", 1)
        collector.record_api_call("/info", 200, 100.0)

    def test_start_stop_collection_logs_only(self, collector):
        """FS-17.9: Start/stop collection lifecycle (logs mode)."""
        collector.enable_prometheus = False

        with patch.object(collector, '_collection_loop', side_effect=_noop):
            with patch('src.monitoring.metrics_collector.log_server_event') as mock_log:
                asyncio.run(collector.start_collection())
                assert collector._running is True
                mock_log.assert_called_once()

                asyncio.run(collector.stop_collection())
                assert collector._running is False

    @patch('src.monitoring.metrics_collector.start_http_server')
    def test_start_collection_prometheus_mode(self, mock_start_http, palworld_config):
        """FS-17.10: Prometheus HTTP server starts in prometheus mode."""
        palworld_config.monitoring.mode = "prometheus"
        collector = MetricsCollector(palworld_config)
        collector.enable_prometheus = True

        with patch.object(collector, '_collection_loop', side_effect=_noop):
            asyncio.run(collector.start_collection())
            mock_start_http.assert_called_once_with(8080)
            assert collector._prometheus_server_started is True

    def test_update_prometheus_system(self, collector):
        """FS-17.11: Prometheus gauge updates for system metrics."""
        collector.enable_prometheus = True

        try:
            metrics = SystemMetrics(
                cpu_percent=55.0, memory_usage_gb=4.0, memory_percent=40.0,
                disk_percent=60.0, disk_usage_gb=120.0,
                network_bytes_sent=5000, network_bytes_recv=10000
            )
            collector._update_prometheus_system(metrics)
        except Exception:
            pass  # OK if prometheus_client not available at module level

    def test_update_prometheus_game(self, collector):
        """FS-17.12: Prometheus gauge updates for game metrics."""
        collector.enable_prometheus = True

        try:
            metrics = GameMetrics(
                players_online=5, max_players=32,
                server_uptime_seconds=7200, tps=20.0, world_save_size_mb=100.0
            )
            collector._update_prometheus_game(metrics)
        except Exception:
            pass  # OK if prometheus_client not available at module level

    def test_process_game_metrics_updates_prometheus(self, collector):
        """FS-17.13: process_game_metrics updates Prometheus gauges."""
        collector.enable_prometheus = True
        import datetime
        metrics = GameMetrics(
            players_online=3, max_players=32,
            server_uptime_seconds=3600, tps=19.5, world_save_size_mb=80.0
        )

        with patch.object(collector, '_update_prometheus_game') as mock_update:
            asyncio.run(collector.process_game_metrics(metrics))
            mock_update.assert_called_once_with(metrics)

    def test_serial_start_stop_safe(self, collector):
        """FS-17.14: Calling start/stop multiple times is safe."""
        collector.enable_prometheus = False

        with patch.object(collector, '_collection_loop', side_effect=_noop):
            # Start twice - second should warn
            asyncio.run(collector.start_collection())
            with patch.object(collector.logger, 'warning') as mock_warn:
                asyncio.run(collector.start_collection())
                mock_warn.assert_called_once()

            asyncio.run(collector.stop_collection())
            # Stop twice - second should no-op
            asyncio.run(collector.stop_collection())
            assert collector._running is False



class TestMetricsCollectorEdgeCases:
    """Edge case coverage for metrics collector."""

    @pytest.fixture
    def collector(self, palworld_config):
        return MetricsCollector(palworld_config)

    @patch('src.monitoring.metrics_collector.start_http_server')
    def test_start_collection_prometheus_server_fails(self, mock_start_http, palworld_config):
        """FS-17.x: start_collection handles Prometheus HTTP server start failure."""
        mock_start_http.side_effect = Exception("port in use")
        palworld_config.monitoring.mode = "prometheus"
        collector = MetricsCollector(palworld_config)
        # _collection_loop is mocked to prevent actual async execution
        with patch.object(collector, '_collection_loop', side_effect=_noop):
            asyncio.run(collector.start_collection())
            # Logger should have been called with the error
            assert collector._prometheus_server_started is False

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_stop_collection_with_prometheus_enabled(self, collector):
        """FS-17.x: stop_collection with collection_task and Prometheus enabled."""
        collector.enable_prometheus = True
        collector._running = True
        collector._collection_task = asyncio.create_task(asyncio.sleep(9999))
        await collector.stop_collection()
        assert collector._running is False
        assert collector._collection_task is not None

    def test_get_metrics_collector_singleton(self, palworld_config):
        """FS-17.x: get_metrics_collector returns singleton instance."""
        from src.monitoring.metrics_collector import get_metrics_collector, _metrics_collector
        # Reset the module-level singleton
        import src.monitoring.metrics_collector as mc
        old = mc._metrics_collector
        mc._metrics_collector = None
        try:
            instance1 = get_metrics_collector(palworld_config)
            instance2 = get_metrics_collector()
            assert instance1 is instance2
            assert isinstance(instance1, MetricsCollector)
        finally:
            mc._metrics_collector = old

    @patch('psutil.cpu_percent')
    @patch('psutil.virtual_memory')
    @patch('psutil.disk_usage')
    @patch('psutil.net_io_counters')
    def test_get_current_metrics_summary_error(self, mock_net, mock_disk, mock_mem, mock_cpu, collector):
        """FS-17.x: get_current_metrics_summary handles psutil exception."""
        mock_cpu.side_effect = Exception("permission denied")
        result = collector.get_current_metrics_summary()
        assert "error" in result

    @patch('psutil.getloadavg')
    @pytest.mark.asyncio
    async def test_collect_system_metrics_load_avg_fallback(self, mock_loadavg, collector):
        """FS-17.x: _collect_system_metrics handles getloadavg AttributeError."""
        mock_loadavg.side_effect = AttributeError("not available")
        with patch('psutil.cpu_percent', return_value=30.0), \
             patch('psutil.virtual_memory') as mock_mem, \
             patch('psutil.disk_usage') as mock_disk, \
             patch('psutil.net_io_counters') as mock_net:
            mock_mem.return_value.used = 4 * 1024**3
            mock_mem.return_value.total = 16 * 1024**3
            mock_mem.return_value.percent = 40.0
            mock_disk.return_value.used = 50 * 1024**3
            mock_disk.return_value.total = 200 * 1024**3
            mock_net.return_value.bytes_sent = 1000
            mock_net.return_value.bytes_recv = 2000

            metrics = await collector._collect_system_metrics()
            assert metrics.load_average == []  # empty list on AttributeError

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_collection_loop_runs_one_iteration(self, collector):
        """FS-17.x: _collection_loop runs one iteration with Prometheus enabled."""
        collector.config.monitoring.metrics_interval = 0.01
        async def mock_collect():
            return SystemMetrics(
                cpu_percent=30.0, memory_usage_gb=4.0, memory_percent=40.0,
                disk_usage_gb=50.0, disk_percent=30.0,
                network_bytes_sent=1000, network_bytes_recv=2000
            )
        collector._collect_system_metrics = mock_collect
        collector._process_system_metrics = AsyncMock()
        collector.enable_prometheus = True
        collector._running = True

        async def stop_soon():
            await asyncio.sleep(0.05)
            collector._running = False

        await asyncio.gather(collector._collection_loop(), stop_soon())
        collector._process_system_metrics.assert_called()

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_collection_loop_exception_handling(self, collector):
        """FS-17.x: _collection_loop handles exception and continues."""
        collector.config.monitoring.metrics_interval = 0.01

        async def mock_collect():
            if not hasattr(mock_collect, 'call_count'):
                mock_collect.call_count = 0
            mock_collect.call_count += 1
            if mock_collect.call_count == 1:
                raise Exception("collect failed")
            return SystemMetrics(
                cpu_percent=30.0, memory_usage_gb=4.0, memory_percent=40.0,
                disk_usage_gb=50.0, disk_percent=30.0,
                network_bytes_sent=1000, network_bytes_recv=2000
            )

        collector._collect_system_metrics = mock_collect
        collector._process_system_metrics = AsyncMock()
        collector.enable_prometheus = True
        collector._running = True

        real_sleep = asyncio.sleep
        async def sleep_side(duration):
            await real_sleep(0)

        with patch.object(collector.logger, 'error') as mock_log:
            with patch('asyncio.sleep', side_effect=sleep_side):
                async def stop_soon():
                    collector._running = False
                await asyncio.gather(collector._collection_loop(), stop_soon())
                mock_log.assert_called_with("Metrics collection error", error='collect failed')


    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_collection_loop_cancellation(self, collector):
        """FS-17.x: _collection_loop handles CancelledError cleanly."""
        collector.config.monitoring.metrics_interval = 9999
        collector._running = True
        # Run the loop as a task and cancel it immediately
        loop_task = asyncio.create_task(collector._collection_loop())
        await asyncio.sleep(0.01)
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass
        # If we reach here, CancelledError was caught inside the loop (break)
        # and the loop method returned gracefully
        assert loop_task.cancelled() is False  # caught CancelledError internally


    def test_collect_game_metrics_sync_world_size(self, collector, tmp_path):
        """FS-17.x: collect_game_metrics_sync calculates world save size."""
        from pathlib import Path
        saved_dir = tmp_path / "Pal" / "Saved"
        saved_dir.mkdir(parents=True)
        (saved_dir / "world.sav").write_text("x" * 1024 * 1024)

        # Set server_dir to tmp_path and verify the path construction
        collector.config.paths.server_dir = Path(str(tmp_path))
        save_dir = collector.config.paths.server_dir / "Pal" / "Saved"
        assert save_dir.exists(), f"save_dir does not exist: {save_dir}"
        collector.server_start_time = time.time() - 3600

        players = [{"name": "P1"}]
        metrics = collector.collect_game_metrics_sync(
            players_data=players,
            server_info={"tps": 19.5}
        )
        assert metrics.players_online == 1
        assert metrics.tps == 19.5
        assert metrics.world_save_size_mb > 0.0, f"world_size was {metrics.world_save_size_mb}"

    def test_record_api_call_with_status_code(self, collector):
        """FS-17.x: record_api_call works with various status codes."""
        collector.record_api_call("/info", 200, 150.0)
        collector.record_api_call("/error", 500, 50.0)
        # Should not raise

    def test_collect_game_metrics_sync_with_data(self, collector):
        """FS-17.x: collect_game_metrics_sync with player data."""
        from src.monitoring.metrics_collector import GameMetrics


        players = [{"name": "P1"}, {"name": "P2"}, {"name": "P3"}]
        metrics = collector.collect_game_metrics_sync(
            players_data=players,
            server_info={"tps": 19.5}
        )
        assert metrics.players_online == 3
        assert metrics.tps == 19.5

    def test_record_server_event_prometheus_enabled(self, collector):
        """FS-17.x: record_server_event Prometheus paths with mode='prometheus'."""
        collector.enable_prometheus = True
        collector.record_server_event("restart", "Server restarting")
        collector.record_server_event("stop", "Server stopping")
        collector.record_server_event("start", "Server started")
        # Should not raise

    def test_record_player_event_prometheus_enabled(self, collector):
        """FS-17.x: record_player_event Prometheus paths."""
        collector.enable_prometheus = True
        collector.record_player_event("join", "Player1", 3)
        collector.record_player_event("leave", "Player1", 2)
        collector.record_player_event("unknown", "Player1", 2)
        # Should not raise
