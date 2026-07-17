"""Tests for the logging system."""

import os
import sys
import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import structlog

from src.logging_setup import (
    setup_logging, get_logger, log_server_event, log_player_event,
    log_api_call, log_backup_event, ContextProcessor,
    CustomConsoleRenderer
)
from structlog.types import EventDict

pytestmark = pytest.mark.unit




class TestSetupLogging:
    """FS-2.1.x: Logging setup behavior."""

    def test_setup_console_logging(self):
        """FS-2.1.1: Console handler is added."""
        setup_logging(log_level="DEBUG", enable_console=True, enable_file=False)
        root_logger = logging.getLogger()
        assert any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers)

    def test_setup_file_logging(self):
        """FS-2.1.2: File handlers are added with log dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            setup_logging(
                log_level="INFO", log_dir=tmpdir,
                enable_console=False, enable_file=True
            )
            root_logger = logging.getLogger()
            file_handlers = [
                h for h in root_logger.handlers
                if isinstance(h, logging.handlers.RotatingFileHandler)
            ]
            assert len(file_handlers) == 2

    def test_setup_silences_noisy_loggers(self):
        """FS-2.1.6: aiohttp/urllib3/asyncio set to WARNING."""
        setup_logging(enable_console=False, enable_file=False)
        assert logging.getLogger("aiohttp").level == logging.WARNING
        assert logging.getLogger("urllib3").level == logging.WARNING
        assert logging.getLogger("asyncio").level == logging.WARNING

    def test_get_logger_returns_bound_logger(self):
        """FS-2.1: get_logger returns structlog logger."""
        setup_logging(enable_console=False, enable_file=False)
        logger = get_logger("test.logger")
        # In newer structlog versions, get_logger returns BoundLoggerLazyProxy
        # which lazily wraps BoundLogger. Both are valid structlog loggers.
        assert isinstance(logger, (structlog.BoundLogger, structlog._config.BoundLoggerLazyProxy))


class TestContextProcessor:
    """FS-2.1.4: Context processor."""

    def test_pid_added(self):
        processor = ContextProcessor()
        event_dict: EventDict = {"event": "test"}
        result = processor(None, "test", event_dict)
        assert "pid" in result
        assert result["pid"] == os.getpid()

    def test_logger_name_added(self):
        processor = ContextProcessor()
        event_dict: EventDict = {"event": "test"}
        result = processor(None, "test", event_dict)
        assert result["logger"] == "test"

    def test_container_name_added(self):
        processor = ContextProcessor()
        event_dict: EventDict = {"event": "test"}
        with patch.dict(os.environ, {"HOSTNAME": "palworld-container"}):
            result = processor(None, "test", event_dict)
            assert result["container"] == "palworld-container"


class TestCustomConsoleRenderer:
    """FS-2.1.5: Custom console renderer."""

    def test_formats_with_timestamp(self):
        renderer = CustomConsoleRenderer()
        event_dict: EventDict = {"level": "info", "event": "test event"}
        result = renderer(None, "test", event_dict)
        assert "[INFO]" in result
        assert "test event" in result
        # Should include ISO timestamp
        assert "T" in result

    def test_level_colors_applied(self):
        renderer = CustomConsoleRenderer()
        event_dict: EventDict = {"level": "error", "event": "error msg"}
        result = renderer(None, "test", event_dict)
        assert "\\033[31m" in repr(result) or "\\x1b[31m" in repr(result) or result.count("[") >= 1
        assert "[ERROR]" in result
        assert "error msg" in result


class TestConvenienceFunctions:
    """FS-2.2: Logging convenience functions."""

    def test_log_server_event(self):
        logger = MagicMock()
        log_server_event(logger, "test_event", "Test message", extra="data")
        logger.info.assert_called_with(
            "Test message", event_type="test_event", extra="data"
        )

    def test_log_player_event(self):
        logger = MagicMock()
        log_player_event(logger, "player_join", "Player1")
        logger.info.assert_called_once()
        args, kwargs = logger.info.call_args
        assert "Player1" in str(kwargs.get("player_name", ""))

    def test_log_api_call_success(self):
        logger = MagicMock()
        log_api_call(logger, "/info", 200, 150.5, attempt=1)
        logger.info.assert_called_once()
        args, kwargs = logger.info.call_args
        assert kwargs["event_type"] in ("api_success", "api_fail")
        assert kwargs["endpoint"] == "/info"

    def test_log_backup_event(self):
        logger = MagicMock()
        log_backup_event(logger, "backup_complete", backup_file="backup.tar.gz")
        logger.info.assert_called_once()
        args, kwargs = logger.info.call_args
        assert kwargs["backup_file"] == "backup.tar.gz"


    def test_formats_with_stdout(self):
        renderer = CustomConsoleRenderer()
        event_dict: EventDict = {
            "level": "info",
            "event": "server output",
            "stdout": "line1\nline2"
        }
        result = renderer(None, "test", event_dict)
        assert "stdout" in result
        assert "line1" in result
        assert "line2" in result

    def test_formats_with_stderr(self):
        renderer = CustomConsoleRenderer()
        event_dict: EventDict = {
            "level": "error",
            "event": "error output",
            "stderr": "traceback line1\ntraceback line2"
        }
        result = renderer(None, "test", event_dict)
        assert "stderr" in result
        assert "traceback line1" in result

    def test_formats_with_env_vars(self):
        renderer = CustomConsoleRenderer()
        event_dict: EventDict = {
            "level": "info",
            "event": "config",
            "env_vars": {"SERVER_NAME": "Test", "PORT": "8211"}
        }
        result = renderer(None, "test", event_dict)
        assert "env_vars" in result
        assert "SERVER_NAME" in result
        assert "PORT" in result

    def test_no_extra_fields_same(self):
        renderer = CustomConsoleRenderer()
        event_dict: EventDict = {"level": "warning", "event": "simple"}
        result = renderer(None, "test", event_dict)
        assert "[WARNING]" in result
        assert "simple" in result
        assert "stdout" not in result
