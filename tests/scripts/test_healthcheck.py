"""Comprehensive tests for scripts/healthcheck.py

Covers enums, dataclasses, status logic, report generation, and
the sync entry point — without network/subprocess dependencies.
"""

import json
import os
import time
from unittest.mock import patch

import pytest

from scripts.healthcheck import (
    HealthChecker,
    HealthStatus,
    HealthCheckResult,
    main as sync_main,
)


@pytest.mark.unit
class TestHealthStatus:
    """HealthStatus enum correctness."""

    def test_values(self):
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.WARNING.value == "warning"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.CRITICAL.value == "critical"

    def test_ordering(self):
        """Ordinal order: healthy < warning < unhealthy < critical."""
        statuses = list(HealthStatus)
        assert statuses == [
            HealthStatus.HEALTHY,
            HealthStatus.WARNING,
            HealthStatus.UNHEALTHY,
            HealthStatus.CRITICAL,
        ]


@pytest.mark.unit
class TestHealthCheckResult:
    """HealthCheckResult dataclass construction."""

    def test_default_construction(self):
        now = time.time()
        result = HealthCheckResult(
            component="test",
            status=HealthStatus.HEALTHY,
            message="OK",
            details={"key": "val"},
            response_time_ms=1.5,
            timestamp=now,
        )
        assert result.component == "test"
        assert result.status == HealthStatus.HEALTHY
        assert result.message == "OK"
        assert result.details == {"key": "val"}
        assert result.response_time_ms == 1.5
        assert result.timestamp == now


@pytest.mark.unit
class TestHealthCheckerConstruction:
    """HealthChecker.__init__ with env var mocking."""

    @patch.dict(os.environ, {"ADMIN_PASSWORD": "secret123"}, clear=True)
    def test_init_with_password(self):
        checker = HealthChecker()
        assert checker.admin_password == "secret123"
        assert checker.rcon_password == "secret123"
        assert checker.rest_api_enabled is True
        assert checker.rest_api_host == "localhost"
        assert checker.rest_api_port == 8212
        assert checker.server_port == 8211
        assert checker.rcon_enabled is True
        assert checker.rcon_host == "localhost"
        assert checker.rcon_port == 25575

    @patch.dict(os.environ, {}, clear=True)
    def test_init_without_password(self):
        """Missing ADMIN_PASSWORD should set empty string, not crash."""
        checker = HealthChecker()
        assert checker.admin_password == ""

    @patch.dict(
        os.environ,
        {
            "ADMIN_PASSWORD": "pass",
            "REST_API_ENABLED": "false",
            "RCON_ENABLED": "false",
            "REST_API_PORT": "9999",
            "RCON_PORT": "12345",
        },
        clear=True,
    )
    def test_init_custom_env(self):
        checker = HealthChecker()
        assert checker.rest_api_enabled is False
        assert checker.rcon_enabled is False
        assert checker.rest_api_port == 9999
        assert checker.rcon_port == 12345


@pytest.mark.unit
class TestSkippedResult:
    """_skipped_result helper."""

    @pytest.mark.asyncio
    async def test_skipped_result(self):
        checker = HealthChecker()
        checker.admin_password = "test"
        result = await checker._skipped_result("rest_api", "disabled")
        assert result.component == "rest_api"
        assert result.status == HealthStatus.HEALTHY
        assert result.message == "disabled"
        assert result.details == {"skipped": True}
        assert result.response_time_ms == 0.0


@pytest.mark.unit
class TestOverallStatus:
    """get_overall_status logic — no I/O needed."""

    def _checker_with_results(self, statuses):
        checker = HealthChecker()
        checker.admin_password = "test"
        checker.results = [
            HealthCheckResult(
                component=f"c{i}",
                status=s,
                message="",
                details={},
                response_time_ms=0,
                timestamp=0,
            )
            for i, s in enumerate(statuses)
        ]
        return checker

    def test_empty_results_is_critical(self):
        c = HealthChecker()
        c.admin_password = "test"
        c.results = []
        assert c.get_overall_status() == HealthStatus.CRITICAL

    def test_all_healthy(self):
        c = self._checker_with_results([HealthStatus.HEALTHY, HealthStatus.HEALTHY])
        assert c.get_overall_status() == HealthStatus.HEALTHY

    def test_warning_overrides_healthy(self):
        c = self._checker_with_results([HealthStatus.HEALTHY, HealthStatus.WARNING])
        assert c.get_overall_status() == HealthStatus.WARNING

    def test_unhealthy_overrides_warning(self):
        c = self._checker_with_results([HealthStatus.WARNING, HealthStatus.UNHEALTHY])
        assert c.get_overall_status() == HealthStatus.UNHEALTHY

    def test_critical_overrides_all(self):
        c = self._checker_with_results(
            [
                HealthStatus.HEALTHY,
                HealthStatus.CRITICAL,
            ]
        )
        assert c.get_overall_status() == HealthStatus.CRITICAL


@pytest.mark.unit
class TestReportGeneration:
    """generate_report text/json output."""

    def _checker_with_results(self, statuses):
        checker = HealthChecker()
        checker.admin_password = "test"
        checker.results = [
            HealthCheckResult(
                component=f"c{i}",
                status=s,
                message="msg",
                details={"detail_key": "detail_val"},
                response_time_ms=12.3,
                timestamp=0,
            )
            for i, s in enumerate(statuses)
        ]
        return checker

    def test_text_report_includes_status(self):
        c = self._checker_with_results([HealthStatus.HEALTHY])
        report = c.generate_report("text")
        assert "HEALTHY" in report
        assert "c0" in report
        assert "detail_key: detail_val" in report

    def test_json_report_structure(self):
        c = self._checker_with_results([HealthStatus.WARNING])
        report = c.generate_report("json")
        data = json.loads(report)
        assert data["overall_status"] == "warning"
        assert len(data["checks"]) == 1
        assert data["checks"][0]["component"] == "c0"


@pytest.mark.unit
class TestMainEntryPoint:
    """Sync main() entry point."""

    @patch("scripts.healthcheck.async_main")
    def test_main_calls_async_main(self, mock_async):
        mock_async.return_value = 0
        result = sync_main()
        assert result == 0
        mock_async.assert_called_once()
