#!/usr/bin/env python3
"""
Color output utilities for consistent terminal formatting
"""

import sys
from enum import Enum


class Color(Enum):
    """ANSI color codes"""
    RESET = '\033[0m'
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[0;33m'
    BLUE = '\033[0;34m'
    MAGENTA = '\033[0;35m'
    CYAN = '\033[0;36m'
    WHITE = '\033[0;37m'
    BOLD_RED = '\033[1;31m'
    BOLD_GREEN = '\033[1;32m'
    BOLD_YELLOW = '\033[1;33m'


def print_info(message: str) -> None:
    """Print info message with green color"""
    print(f"{Color.GREEN.value}[INFO]{Color.RESET.value} {message}")


def print_warn(message: str) -> None:
    """Print warning message with yellow color"""
    print(f"{Color.YELLOW.value}[WARN]{Color.RESET.value} {message}")


def print_error(message: str) -> None:
    """Print error message with red color"""
    print(f"{Color.RED.value}[ERROR]{Color.RESET.value} {message}", file=sys.stderr)


def print_success(message: str) -> None:
    """Print success message with bold green color"""
    print(f"{Color.BOLD_GREEN.value}[SUCCESS]{Color.RESET.value} {message}")


def print_debug(message: str) -> None:
    """Print debug message with cyan color"""
    print(f"{Color.CYAN.value}[DEBUG]{Color.RESET.value} {message}")


def colorize(text: str, color: Color) -> str:
    """Colorize text with specified color"""
    return f"{color.value}{text}{Color.RESET.value}"
