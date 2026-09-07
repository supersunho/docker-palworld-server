#!/usr/bin/env python3
"""
Common utility functions
Helper functions used across the Palworld server management system
"""

import os
import asyncio
import inspect
import functools
from typing import Any, Callable, TypeVar, Union
from pathlib import Path
import logging

T = TypeVar("T")


def ensure_directory(path: Union[str, Path]) -> Path:
    """
    Ensure directory exists, create if it doesn't

    Args:
        path: Directory path

    Returns:
        Path object
    """
    path_obj = Path(path)
    path_obj.mkdir(parents=True, exist_ok=True)
    return path_obj


def get_file_size_mb(file_path: Union[str, Path]) -> float:
    """
    Get file size in megabytes

    Args:
        file_path: Path to file

    Returns:
        File size in MB
    """
    try:
        size_bytes = Path(file_path).stat().st_size
        return size_bytes / (1024 * 1024)
    except (FileNotFoundError, OSError):
        return 0.0


def format_bytes(bytes_value: int) -> str:
    """
    Format bytes to human readable string

    Args:
        bytes_value: Size in bytes

    Returns:
        Formatted string (e.g., "1.5 GB")
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} PB"


def format_duration(seconds: float) -> str:
    """
    Format duration in seconds to human readable string

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted string (e.g., "2h 30m 15s")
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        remaining_seconds = int(seconds % 60)
        return f"{minutes}m {remaining_seconds}s"
    else:
        hours = int(seconds // 3600)
        remaining_minutes = int((seconds % 3600) // 60)
        remaining_seconds = int(seconds % 60)
        return f"{hours}h {remaining_minutes}m {remaining_seconds}s"


def retry_async(max_retries: int = 3, delay: float = 1.0):
    """
    Decorator for async function retry logic.

    On final failure the last exception is re-raised with the full attempt
    chain attached via :class:`BaseExceptionGroup` (Python3.11+) so callers
    can inspect every failure, not just the most recent one. On older
    Python the chain is attached via ``raise ... from`` on the final
    exception with the prior attempts appended to ``__cause_chain__``.

    Args:
        max_retries: Maximum number of retry attempts
        delay: Delay between retries in seconds
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            exceptions: list[BaseException] = []
            backoff_cap = 30.0  # matches RconClient; prevents unbounded growth

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    exceptions.append(e)
                    if attempt < max_retries:
                        sleep_for = min(delay * (2**attempt), backoff_cap)
                        await asyncio.sleep(sleep_for)
                    else:
                        break

            if not exceptions:
                # Should not happen, but keep the type-checker honest.
                raise RuntimeError("retry_async exhausted with no captured exception")

            last_exception = exceptions[-1]
            if len(exceptions) > 1:
                # Attach the full chain for diagnostics. ``raise ... from``
                # hides the last exception's implicit context, so prefer
                # ExceptionGroup where available (3.11+).
                try:
                    raise BaseExceptionGroup(
                        f"{func.__name__} failed after {len(exceptions)} attempts",
                        exceptions,
                    ) from last_exception
                except NameError:
                    # Python < 3.11 — fall back to manual chaining.
                    chain = "\n".join(
                        f"  attempt {i + 1}: {type(e).__name__}: {e}"
                        for i, e in enumerate(exceptions)
                    )
                    raise RuntimeError(
                        f"{func.__name__} failed after {len(exceptions)} attempts:\n{chain}"
                    ) from last_exception
            raise last_exception

        return wrapper

    return decorator


def validate_port(port: int) -> bool:
    """
    Validate if port number is in valid range

    Args:
        port: Port number to validate

    Returns:
        True if valid, False otherwise
    """
    return 1024 <= port <= 65535


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename for cross-platform compatibility

    Args:
        filename: Original filename

    Returns:
        Sanitized filename
    """
    import re

    # Remove or replace invalid characters
    sanitized = re.sub(r'[<>:"/\\|?*]', "_", filename)
    # Remove consecutive underscores
    sanitized = re.sub(r"_+", "_", sanitized)
    # Remove leading/trailing underscores and dots
    sanitized = sanitized.strip("_.")
    return sanitized


def get_container_id() -> str:
    """
    Get current Docker container ID if running in container

    Returns:
        Container ID or 'host' if not in container
    """
    try:
        with open("/proc/self/cgroup", "r") as f:
            for line in f:
                if "docker" in line:
                    # Extract container ID from cgroup path
                    parts = line.strip().split("/")
                    for part in parts:
                        if len(part) == 64 and part.isalnum():
                            return part[:12]  # Short container ID
        return "host"
    except (FileNotFoundError, PermissionError):
        return "host"


async def safe_cleanup(coro_or_func: Union[Callable, Any], *args, **kwargs) -> None:
    """
    Safely call cleanup function/coroutine with error handling

    Args:
        coro_or_func: Function or coroutine to call
        *args: Arguments to pass
        **kwargs: Keyword arguments to pass
    """
    try:
        if inspect.iscoroutinefunction(coro_or_func):
            await coro_or_func(*args, **kwargs)
        else:
            coro_or_func(*args, **kwargs)
    except Exception as e:
        # Log the error but don't raise it during cleanup
        logger = logging.getLogger("palworld.helpers")
        logger.warning(f"Cleanup error in {coro_or_func.__name__}: {e}")


class AsyncContextManager:
    """
    Base class for async context managers with proper cleanup
    """

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await safe_cleanup(self.stop)

    async def start(self):
        """Override in subclasses"""
        pass

    async def stop(self):
        """Override in subclasses"""
        pass


def get_environment_info() -> dict:
    """
    Get environment information for debugging

    Returns:
        Dictionary with environment info
    """
    return {
        "container_id": get_container_id(),
        "python_version": f"{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}",
        "platform": os.name,
        "working_directory": str(Path.cwd()),
        "user_id": os.getuid() if hasattr(os, "getuid") else "unknown",
        "group_id": os.getgid() if hasattr(os, "getgid") else "unknown",
    }


# Export commonly used functions
__all__ = [
    "ensure_directory",
    "get_file_size_mb",
    "format_bytes",
    "format_duration",
    "retry_async",
    "validate_port",
    "sanitize_filename",
    "get_container_id",
    "safe_cleanup",
    "AsyncContextManager",
    "get_environment_info",
]
