#!/usr/bin/env python3
"""
structlog + emoji logging system setup
Efficient logging implementation reflecting user's workflow optimization preferences
"""

import os
import sys
import logging
import logging.handlers
from pathlib import Path
from typing import Any, Dict, Optional, Union

import structlog
from structlog.types import EventDict, Processor
import colorama


# Log level emoji mapping
LEVEL_EMOJIS = {
    "DEBUG": "🔍",
    "INFO": "ℹ️",
    "WARNING": "⚠️",
    "ERROR": "❌",
    "CRITICAL": "🚨",
}

# Special event emoji mapping
EVENT_EMOJIS = {
    # Server related
    "server_start": "🚀",
    "server_stop": "🛑",
    "server_restart": "🔄",
    "server_crash": "💥",
    
    # Player related
    "player_join": "👤",
    "player_leave": "👋",
    "player_kick": "🦵",
    "player_ban": "🚫",
    
    # Backup related
    "backup_start": "💾",
    "backup_complete": "📦",
    "backup_fail": "💔",
    "backup_cleanup": "🗑️",
    
    # API related
    "api_call": "📡",
    "api_success": "✅",
    "api_fail": "🔴",
    
    # Monitoring related
    "metrics": "📊",
    "health_check": "🩺",
    "alert": "🔔",
    
    # SteamCMD related
    "steamcmd_start": "⬇️",
    "steamcmd_complete": "✅",
    "steamcmd_fail": "❌",
    
    # System related
    "startup": "🏁",
    "shutdown": "🔚",
    "config_load": "⚙️",
    "discord_send": "💬",
}


class EmojiEventProcessor:
    """Processor to add emojis based on events"""
    
    def __call__(self, logger: Any, name: str, event_dict: EventDict) -> EventDict:
        """
        Add emojis to event dictionary
        
        Args:
            logger: Logger instance
            name: Logger name
            event_dict: Event dictionary
            
        Returns:
            Event dictionary with emojis added
        """
        # Add level emoji
        level = event_dict.get("level", "info").upper()
        level_emoji = LEVEL_EMOJIS.get(level, "📝")
        
        # Find event type emoji
        event_emoji = ""
        event_type = event_dict.get("event_type")
        if event_type and event_type in EVENT_EMOJIS:
            event_emoji = EVENT_EMOJIS[event_type]
        else:
            # Find keywords in event message
            event_msg = event_dict.get("event", "").lower()
            for keyword, emoji in EVENT_EMOJIS.items():
                if keyword.replace("_", " ") in event_msg:
                    event_emoji = emoji
                    break
        
        # Combine emojis
        if event_emoji:
            emoji_prefix = f"{event_emoji} {level_emoji}"
        else:
            emoji_prefix = level_emoji
        
        # Add emojis to existing event message
        original_event = event_dict.get("event", "")
        event_dict["event"] = f"{emoji_prefix} {original_event}"
        
        return event_dict


class ContextProcessor:
    """Processor to add context information"""
    
    def __call__(self, logger: Any, name: str, event_dict: EventDict) -> EventDict:
        """
        Add context information to event
        
        Args:
            logger: Logger instance  
            name: Logger name
            event_dict: Event dictionary
            
        Returns:
            Event dictionary with context added
        """
        # Add process information
        event_dict["pid"] = os.getpid()
        
        # Add logger name (module information)
        event_dict["logger"] = name
        
        # Docker container information (if available)
        container_name = os.getenv("HOSTNAME")
        if container_name:
            event_dict["container"] = container_name
        
        return event_dict


def setup_logging(
    log_level: str = "INFO",
    log_dir: Optional[Union[str, Path]] = None,
    enable_console: bool = True,
    enable_file: bool = True,
    enable_json: bool = False,
) -> None:
    """
    Setup structlog logging system
    
    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Log file storage directory
        enable_console: Enable console output
        enable_file: Enable file output  
        enable_json: Enable JSON format output (for production)
    """
    # Initialize colorama (Windows compatibility)
    colorama.init()
    
    # Set log level
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Standard logging setup
    logging.basicConfig(
        level=numeric_level,
        format="%(message)s",
        handlers=[]
    )
    
    # Handler list
    handlers = []
    
    # Console handler (development environment)
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        handlers.append(console_handler)
    
    # File handler (production environment)
    if enable_file and log_dir:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        
        # General log file
        file_handler = logging.handlers.RotatingFileHandler(
            log_path / "palworld.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(numeric_level)
        handlers.append(file_handler)
        
        # Error-only log file
        error_handler = logging.handlers.RotatingFileHandler(
            log_path / "palworld_error.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=3,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        handlers.append(error_handler)
    
    # Add handlers to root logger
    root_logger = logging.getLogger()
    root_logger.handlers = handlers
    
    # Configure structlog processors
    processors = [
        structlog.contextvars.merge_contextvars,
        ContextProcessor(),
        EmojiEventProcessor(),
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="ISO"),
    ]
    
    # Choose renderer based on environment
    if enable_json:
        # JSON renderer (production, for log analysis tools)
        processors.append(structlog.processors.JSONRenderer())
    else:
        # Console renderer (development, human-readable format)
        processors.append(
            structlog.dev.ConsoleRenderer(
                colors=enable_console and not os.getenv("NO_COLOR"),
                exception_formatter=structlog.dev.rich_traceback
            )
        )
    
    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Adjust third-party library log levels
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Return structured logger instance
    
    Args:
        name: Logger name (usually use __name__)
        
    Returns:
        structlog.BoundLogger instance
    """
    return structlog.get_logger(name)


# Convenience functions
def log_server_event(logger: structlog.BoundLogger, event_type: str, message: str, **kwargs) -> None:
    """Log server event"""
    logger.info(message, event_type=event_type, **kwargs)


def log_player_event(logger: structlog.BoundLogger, event_type: str, player_name: str, **kwargs) -> None:
    """Log player event"""
    logger.info(f"Player {event_type.replace('_', ' ')}", 
                event_type=event_type, 
                player_name=player_name, 
                **kwargs)


def log_api_call(logger: structlog.BoundLogger, endpoint: str, status_code: int, duration_ms: float, **kwargs) -> None:
    """Log API call"""
    event_type = "api_success" if 200 <= status_code < 300 else "api_fail"
    
    logger.info(f"API call completed", 
                event_type=event_type,
                endpoint=endpoint,
                status_code=status_code,
                duration_ms=duration_ms,
                **kwargs)


def log_backup_event(logger: structlog.BoundLogger, event_type: str, backup_file: Optional[str] = None, **kwargs) -> None:
    """Log backup event"""
    message = {
        "backup_start": "Backup started",
        "backup_complete": "Backup completed",
        "backup_fail": "Backup failed",
        "backup_cleanup": "Backup cleanup"
    }.get(event_type, "Backup event")
    
    logger.info(message, 
                event_type=event_type, 
                backup_file=backup_file, 
                **kwargs)


if __name__ == "__main__":
    # Test execution
    setup_logging(
        log_level="DEBUG",
        log_dir="/tmp/palworld_logs",
        enable_console=True,
        enable_file=True,
        enable_json=False
    )
    
    logger = get_logger("test")
    
    # Various log tests
    log_server_event(logger, "server_start", "Server started", port=8211)
    log_player_event(logger, "player_join", "TestPlayer", player_count=5)
    log_api_call(logger, "/v1/api/players", 200, 150.5)
    log_backup_event(logger, "backup_complete", "backup_20250627.tar.gz", size_mb=1024)
    
    logger.warning("Test warning message", test_param="value")
    logger.error("Test error message", error_code=500)
    
    print("✅ Logging system test complete!")
