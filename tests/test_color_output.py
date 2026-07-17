"""Tests for color output utilities."""

import pytest
from io import StringIO
from src.utils.color_output import (
    Color,
    print_info,
    print_warn,
    print_error,
    print_success,
    print_debug,
    colorize,
)

pytestmark = pytest.mark.unit


class TestColorOutput:
    """FS-23.x: Color output behavior."""

    def test_color_enum_values(self):
        """FS-23: ANSI codes defined."""
        assert Color.RED.value == "\033[0;31m"
        assert Color.GREEN.value == "\033[0;32m"
        assert Color.RESET.value == "\033[0m"

    def test_print_info(self, capsys):
        """FS-23: Info format."""
        print_info("test message")
        captured = capsys.readouterr()
        assert "[INFO]" in captured.out
        assert "test message" in captured.out

    def test_print_warn(self, capsys):
        """FS-23: Warning format."""
        print_warn("warning")
        captured = capsys.readouterr()
        assert "[WARN]" in captured.out
        assert "warning" in captured.out

    def test_print_error(self, capsys):
        """FS-23: Error format."""
        print_error("error msg")
        captured = capsys.readouterr()
        assert "[ERROR]" in captured.err
        assert "error msg" in captured.err

    def test_print_success(self, capsys):
        """FS-23: Success format."""
        print_success("success!")
        captured = capsys.readouterr()
        assert "[SUCCESS]" in captured.out

    def test_print_debug(self, capsys):
        """FS-23: Debug format."""
        print_debug("debug info")
        captured = capsys.readouterr()
        assert "[DEBUG]" in captured.out

    def test_colorize(self):
        """FS-23: Colorize wraps with ANSI."""
        result = colorize("hello", Color.RED)
        assert "\033[0;31m" in result
        assert "\033[0m" in result
        assert "hello" in result
