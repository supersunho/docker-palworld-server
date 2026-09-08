"""Comprehensive tests for scripts/healthcheck.py

Covers enums, dataclasses, status logic, report generation, and
the sync entry point — without network/subprocess dependencies.
"""

import asyncio
import json
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

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
        result = sync_main([])
        assert result == 0
        mock_async.assert_called_once_with(format_json=False)

    @patch("scripts.healthcheck.async_main")
    def test_main_passes_json_flag_and_exit_code(self, mock_async):
        mock_async.return_value = 1

        result = sync_main(["--json"])

        assert result == 1
        mock_async.assert_called_once_with(format_json=True)

    @patch("scripts.healthcheck.HealthChecker")
    def test_help_exits_before_health_checks(self, mock_checker, capsys):
        with pytest.raises(SystemExit) as exc_info:
            sync_main(["--help"])

        assert exc_info.value.code == 0
        output = capsys.readouterr().out
        assert "usage:" in output
        assert "--json" in output
        mock_checker.assert_not_called()


@pytest.mark.unit
class TestRconCommandProbe:
    """_test_rcon_command must not use --password-stdin (unsupported by the
    bundled rcon-cli); the secret travels via RCON_PASSWORD env instead."""

    def _checker(self):
        with patch.dict(os.environ, {"ADMIN_PASSWORD": "probe-secret"}, clear=True):
            return HealthChecker()

    def _mock_process(self, returncode=0, stdout=b"", stderr=b""):
        process = MagicMock()
        process.returncode = returncode
        process.communicate = AsyncMock(return_value=(stdout, stderr))
        process.kill = MagicMock()
        process.wait = AsyncMock(return_value=None)
        return process

    @pytest.mark.asyncio
    async def test_success_passes_password_via_env(self):
        checker = self._checker()
        process = self._mock_process(returncode=0, stdout=b"Welcome to Pal Server")
        with patch(
            "asyncio.create_subprocess_exec", AsyncMock(return_value=process)
        ) as mock_exec:
            result = await checker._test_rcon_command()

        assert result["success"] is True
        assert result["error"] is None
        argv = list(mock_exec.call_args[0])
        assert "--password-stdin" not in argv
        assert argv[-1] == "Info"
        assert mock_exec.call_args[1]["env"]["RCON_PASSWORD"] == "probe-secret"
        # Base environment is preserved, not replaced.
        assert mock_exec.call_args[1]["env"]["PATH"] == os.environ["PATH"]

    @pytest.mark.asyncio
    async def test_failure_reports_stderr(self):
        checker = self._checker()
        process = self._mock_process(returncode=255, stderr=b"unknown flag")
        with patch(
            "asyncio.create_subprocess_exec", AsyncMock(return_value=process)
        ):
            result = await checker._test_rcon_command()

        assert result["success"] is False
        assert "unknown flag" in result["error"]

    @pytest.mark.asyncio
    async def test_timeout_kills_process(self):
        checker = self._checker()
        process = self._mock_process()
        process.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        with patch(
            "asyncio.create_subprocess_exec", AsyncMock(return_value=process)
        ):
            result = await checker._test_rcon_command()

        assert result["success"] is False
        assert result["error"] == "RCON command timeout"
        process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_binary_falls_back_to_port_check(self):
        checker = self._checker()
        with patch(
            "asyncio.create_subprocess_exec", AsyncMock(side_effect=FileNotFoundError())
        ):
            result = await checker._test_rcon_command()

        assert result["success"] is True
        assert "port check only" in result["response"]
