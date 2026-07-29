"""Ensure scripts can be imported without errors (R2-P2-09)."""

import pytest


class TestHealthcheckImport:
    """Verify scripts/healthcheck.py can import its core types."""

    def test_import_healthcheck(self):
        from scripts.healthcheck import (
            HealthChecker,
            HealthStatus,
            HealthCheckResult,
        )
        assert HealthStatus is not None
        assert HealthCheckResult is not None
        checker = HealthChecker()
        assert checker is not None


class TestBackupManagerMain:
    """Verify backup_manager main wrappers work."""

    def test_import_backup_main(self):
        from src.backup.backup_manager import main
        assert callable(main)
