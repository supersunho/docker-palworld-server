"""Tests for utility helper functions."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch
from unittest.mock import AsyncMock, MagicMock
from src.utils.helpers import (
    ensure_directory,
    get_file_size_mb,
    format_bytes,
    format_duration,
    retry_async,
)

pytestmark = pytest.mark.unit


class TestHelpers:
    """FS-22.x: Helper functions."""

    def test_ensure_directory_creates(self, tmp_path):
        """FS-22: Creates directory."""
        new_dir = tmp_path / "new" / "nested" / "dir"
        result = ensure_directory(new_dir)
        assert result == new_dir
        assert new_dir.exists()

    def test_ensure_directory_exists(self, tmp_path):
        """FS-22: Existing directory works."""
        result = ensure_directory(tmp_path)
        assert result == tmp_path

    def test_get_file_size_mb(self, tmp_path):
        """FS-22: Returns size in MB."""
        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"x" * 1024 * 1024)
        size = get_file_size_mb(test_file)
        assert 0.99 < size < 1.01

    def test_get_file_size_mb_not_found(self):
        """FS-22: Returns 0 for missing file."""
        assert get_file_size_mb("/nonexistent/file") == 0.0

    def test_format_bytes(self):
        """FS-22: Human-readable byte sizes."""
        assert format_bytes(500) == "500.0 B"
        assert format_bytes(2048) == "2.0 KB"
        assert format_bytes(3 * 1024 * 1024) == "3.0 MB"
        assert format_bytes(2 * 1024 * 1024 * 1024) == "2.0 GB"
        assert format_bytes(1024**4) == "1.0 TB"
        assert format_bytes(1024**5) == "1.0 PB"

    def test_format_duration(self):
        """FS-22: Human-readable durations."""
        assert format_duration(30) == "30.0s"
        assert format_duration(150) == "2m 30s"
        assert format_duration(7500) == "2h 5m 0s"
        assert format_duration(999999) == "277h 46m 39s"

    @pytest.mark.asyncio
    async def test_retry_async_success_first(self):
        """FS-22: Retry succeeds on first try."""
        mock_fn = AsyncMock(return_value="success")
        decorated = retry_async(max_retries=3, delay=0.01)(mock_fn)
        result = await decorated()
        assert result == "success"
        assert mock_fn.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_async_succeeds_after_retry(self):
        """FS-22: Retry succeeds after failures."""
        mock_fn = AsyncMock(side_effect=[ValueError("fail"), "success"])
        decorated = retry_async(max_retries=3, delay=0.01)(mock_fn)
        result = await decorated()
        assert result == "success"
        assert mock_fn.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_async_exhausted(self):
        """FS-22: Retry exhausts and raises."""
        mock_fn = AsyncMock(side_effect=ValueError("always fail"))
        decorated = retry_async(max_retries=2, delay=0.01)(mock_fn)
        with pytest.raises(ValueError):
            await decorated()
        assert mock_fn.call_count == 3  # max_retries + 1

    # ---- Additional helpers coverage ----

    def test_validate_port_valid_range(self):
        """FS-22: Valid port numbers."""
        from src.utils.helpers import validate_port

        assert validate_port(1024) is True
        assert validate_port(25575) is True
        assert validate_port(65535) is True

    def test_validate_port_invalid_range(self):
        """FS-22: Invalid port numbers."""
        from src.utils.helpers import validate_port

        assert validate_port(0) is False
        assert validate_port(1023) is False
        assert validate_port(65536) is False
        assert validate_port(-1) is False

    def test_sanitize_filename(self):
        """FS-22: Removes or replaces illegal filename characters."""
        from src.utils.helpers import sanitize_filename

        assert sanitize_filename("simple.txt") == "simple.txt"
        assert "<" not in sanitize_filename("bad<file")
        assert ":" not in sanitize_filename("bad:file")
        assert "/" not in sanitize_filename("bad/file")
        assert sanitize_filename("___leading") == "leading"
        assert sanitize_filename("trailing...") == "trailing"
        assert "__" not in sanitize_filename("a__b")

    @patch("src.utils.helpers.open", side_effect=FileNotFoundError)
    def test_get_container_id_not_in_container(self, mock_open):
        """FS-22: Returns 'host' when cgroup not found."""
        from src.utils.helpers import get_container_id

        assert get_container_id() == "host"

    @patch("src.utils.helpers.open", side_effect=PermissionError)
    def test_get_container_id_permission_denied(self, mock_open):
        """FS-22: Returns 'host' on permission error."""
        from src.utils.helpers import get_container_id
        from src.utils.helpers import get_environment_info, validate_port

        assert get_container_id() == "host"
        info = get_environment_info()
        assert info["container_id"] == "host"
        assert validate_port(8080) is True
        assert validate_port(80) is False
        assert validate_port(70000) is False

    @pytest.mark.asyncio
    async def test_safe_cleanup_async_success(self):
        """FS-22: Calls and awaits async cleanup."""
        from src.utils.helpers import safe_cleanup

        mock_fn = AsyncMock()
        await safe_cleanup(mock_fn)
        mock_fn.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_safe_cleanup_sync_success(self):
        """FS-22: Calls sync cleanup."""
        from src.utils.helpers import safe_cleanup

        mock_fn = MagicMock()
        await safe_cleanup(mock_fn)
        mock_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_safe_cleanup_error_swallowed(self):
        """FS-22: Errors during cleanup are logged, not raised."""
        from src.utils.helpers import safe_cleanup

        async def failing_cleanup():
            raise ValueError("inner")

        await safe_cleanup(failing_cleanup)

    @pytest.mark.asyncio
    async def test_async_context_manager_base_start_stop(self):
        """Cover the pass stubs in AsyncContextManager."""
        from src.utils.helpers import AsyncContextManager

        cm = AsyncContextManager()
        await cm.start()
        await cm.stop()

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """FS-22: AsyncContextManager calls start/stop."""
        from src.utils.helpers import AsyncContextManager

        start_called = False
        stop_called = False

        class TestCM(AsyncContextManager):
            async def start(self):
                nonlocal start_called
                start_called = True

            async def stop(self):
                nonlocal stop_called
                stop_called = True

        async with TestCM():
            assert start_called is True
            assert stop_called is False

        assert stop_called is True

    def test_get_environment_info(self):
        """FS-22: Returns dict with expected keys."""
        from src.utils.helpers import get_environment_info

        info = get_environment_info()
        assert "container_id" in info
        assert "python_version" in info
        assert "platform" in info
        assert "working_directory" in info
