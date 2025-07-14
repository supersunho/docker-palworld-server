#!/usr/bin/env python3
"""
structlog + emoji logging system setup
Efficient logging implementation for Palworld server management
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


LEVEL_EMOJIS = {
    "DEBUG": "🔍",
    "INFO": "ℹ️",
    "WARNING": "⚠️",
    "ERROR": "❌",
    "CRITICAL": "🚨",
}

EVENT_EMOJIS = {
    "server_start": "🚀",
    "server_stop": "🛑",
    "server_restart": "🔄",
    "server_crash": "💥",
    "player_join": "👤",
    "player_leave": "👋",
    "player_kick": "🦵",
    "player_ban": "🚫",
    "backup_start": "💾",
    "backup_complete": "📦",
    "backup_fail": "💔",
    "backup_cleanup": "🗑️",
    "api_call": "📡",
    "api_success": "✅",
    "api_fail": "🔴",
    "metrics": "📊",
    "health_check": "🩺",
    "alert": "🔔",
    "steamcmd_start": "⬇️",
    "steamcmd_complete": "✅",
    "steamcmd_fail": "❌",
    "startup": "🏁",
    "shutdown": "🔚",
    "config_load": "⚙️",
    "discord_send": "💬",
    "idle_restart_init": "⏰",
    "rcon_connect": "🖥️",
}


class EmojiEventProcessor:
    """Processor to add emojis based on events"""
    
    def __call__(self, logger: Any, name: str, event_dict: EventDict) -> EventDict:
        """Add emojis to event dictionary"""
        level = event_dict.get("level", "info").upper()
        level_emoji = LEVEL_EMOJIS.get(level, "📝")
        
        event_emoji = ""
        event_type = event_dict.get("event_type")
        if event_type and event_type in EVENT_EMOJIS:
            event_emoji = EVENT_EMOJIS[event_type]
        else:
            event_msg = event_dict.get("event", "").lower()
            for keyword, emoji in EVENT_EMOJIS.items():
                if keyword.replace("_", " ") in event_msg:
                    event_emoji = emoji
                    break
        
        if event_emoji:
            emoji_prefix = f"{event_emoji}"
        else:
            emoji_prefix = level_emoji
        
        original_event = event_dict.get("event", "")
        event_dict["event"] = f"{emoji_prefix} {original_event}"
        
        return event_dict


class ContextProcessor:
    """Processor to add context information"""
    
    def __call__(self, logger: Any, name: str, event_dict: EventDict) -> EventDict:
        """Add context information to event"""
        event_dict["pid"] = os.getpid()
        event_dict["logger"] = name
        
        container_name = os.getenv("HOSTNAME")
        if container_name:
            event_dict["container"] = container_name
        
        return event_dict


class CustomConsoleRenderer:
    """Custom console renderer to match bash script format"""
    
    def __call__(self, logger, name, event_dict):
        """Render log entry in bash script format"""
        level = event_dict.get("level", "info").upper()
        event = event_dict.get("event", "")

        level_colors = {
            "DEBUG": "\033[36m",    # Cyan
            "INFO": "\033[34m",     # Blue  
            "WARNING": "\033[33m",  # Yellow
            "ERROR": "\033[31m",    # Red
            "CRITICAL": "\033[35m", # Magenta
        }
        
        reset_color = "\033[0m"
        color = level_colors.get(level, "")

        formatted_message = f"{color}[{level}]{reset_color} {event}"
        
        return formatted_message


def setup_logging(
    log_level: str = "INFO",
    log_dir: Optional[Union[str, Path]] = None,
    enable_console: bool = True,
    enable_file: bool = True,
    enable_json: bool = False,
    log_format_style: str = "simple",  
) -> None:
    """Setup structlog logging system"""
    colorama.init()
    
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    logging.basicConfig(
        level=numeric_level,
        format="%(message)s",
        handlers=[]
    )
    
    handlers = []
    
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        handlers.append(console_handler)
    
    if enable_file and log_dir:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.handlers.RotatingFileHandler(
            log_path / "palworld.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(numeric_level)
        handlers.append(file_handler)
        
        error_handler = logging.handlers.RotatingFileHandler(
            log_path / "palworld_error.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=3,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        handlers.append(error_handler)
    
    root_logger = logging.getLogger()
    root_logger.handlers = handlers
    
    processors = [
        structlog.contextvars.merge_contextvars,
        ContextProcessor(),
        EmojiEventProcessor(),
        structlog.processors.add_log_level,
    ]
    
    
    if log_format_style == "simple":
        processors.append(CustomConsoleRenderer())
    else:
        processors.append(structlog.processors.TimeStamper(fmt="ISO"))
        if enable_json:
            processors.append(structlog.processors.JSONRenderer())
        else:
            processors.append(
                structlog.dev.ConsoleRenderer(
                    colors=enable_console and not os.getenv("NO_COLOR"),
                    exception_formatter=structlog.dev.rich_traceback
                )
            )
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.BoundLogger:
    """Return structured logger instance"""
    return structlog.get_logger(name)


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
    
    logger.info(f"API call completed {endpoint}", 
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
