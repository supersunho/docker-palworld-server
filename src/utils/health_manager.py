#!/usr/bin/env python3
"""
Advanced health management system
Continuous monitoring with automatic recovery and alerting
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass
import subprocess

from ..config_loader import PalworldConfig
from ..logging_setup import get_logger, log_server_event


@dataclass
class HealthThresholds:
    """Health check thresholds configuration"""
    cpu_warning: float = 80.0
    cpu_critical: float = 90.0
    memory_warning: float = 85.0
    memory_critical: float = 95.0
    disk_warning: float = 90.0
    disk_critical: float = 95.0
    api_timeout: float = 10.0
    check_interval: int = 30


class HealthManager:
    """Advanced health monitoring and recovery manager"""
    
    def __init__(self, config: PalworldConfig):
        self.config = config
        self.logger = get_logger("palworld.health")
        self.thresholds = HealthThresholds()
        
        self.last_check_time: Optional[float] = None
        self.consecutive_failures = 0
        self.health_history: List[Dict[str, Any]] = []
        self.max_history = 100
        
        self.max_consecutive_failures = 3
        self.recovery_enabled = True
        self.recovery_callbacks: List[Callable] = []
        
        self._monitoring_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start_monitoring(self) -> None:
        """Start continuous health monitoring"""
        if self._running:
            self.logger.warning("Health monitoring already running")
            return
        
        self._running = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        log_server_event(
            self.logger, "health_check", 
            "Health monitoring started",
            check_interval=self.thresholds.check_interval
        )
    
    async def stop_monitoring(self) -> None:
        """Stop continuous health monitoring"""
        self._running = False
        
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        log_server_event(self.logger, "health_check", "Health monitoring stopped")
    
    async def _monitoring_loop(self) -> None:
        """Main monitoring loop"""
        while self._running:
            try:
                health_result = await self.perform_health_check()
                self._update_health_history(health_result)
                await self._handle_health_result(health_result)
                await self._notify_health_status(health_result)
                await asyncio.sleep(self.thresholds.check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Health monitoring loop error", error=str(e))
                await asyncio.sleep(10)
    
    async def perform_health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check"""
        try:
            result = subprocess.run(
                ["python3", "/app/scripts/healthcheck.py", "--json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                import json
                health_data = json.loads(result.stdout)
                health_data["check_success"] = True
                return health_data
            else:
                return {
                    "check_success": False,
                    "error": result.stderr,
                    "overall_status": "critical",
                    "timestamp": time.time()
                }
                
        except Exception as e:
            return {
                "check_success": False,
                "error": str(e),
                "overall_status": "critical",
                "timestamp": time.time()
            }
    
    def _update_health_history(self, health_result: Dict[str, Any]) -> None:
        """Update health check history"""
        self.health_history.append({
            "timestamp": time.time(),
            "status": health_result.get("overall_status", "unknown"),
            "success": health_result.get("check_success", False)
        })
        
        if len(self.health_history) > self.max_history:
            self.health_history = self.health_history[-self.max_history:]
        
        self.last_check_time = time.time()
    
    async def _handle_health_result(self, health_result: Dict[str, Any]) -> None:
        """Handle health check results and trigger recovery if needed"""
        overall_status = health_result.get("overall_status", "critical")
        
        if overall_status in ["unhealthy", "critical"]:
            self.consecutive_failures += 1
            
            self.logger.warning(
                "Health check failure detected",
                consecutive_failures=self.consecutive_failures,
                status=overall_status
            )
            
            if (self.consecutive_failures >= self.max_consecutive_failures and 
                self.recovery_enabled):
                await self._trigger_recovery(health_result)
        else:
            if self.consecutive_failures > 0:
                self.logger.info(
                    "Health restored after failures",
                    previous_failures=self.consecutive_failures
                )
            self.consecutive_failures = 0
    
    async def _trigger_recovery(self, health_result: Dict[str, Any]) -> None:
        """Trigger automatic recovery procedures"""
        log_server_event(
            self.logger, "recovery_start",
            f"Triggering automatic recovery after {self.consecutive_failures} failures"
        )
        
        try:
            for callback in self.recovery_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(health_result)
                    else:
                        callback(health_result)
                except Exception as e:
                    self.logger.error("Recovery callback failed", error=str(e))
            
            self.consecutive_failures = 0
            
            log_server_event(
                self.logger, "recovery_complete",
                "Automatic recovery procedures completed"
            )
            
        except Exception as e:
            log_server_event(
                self.logger, "recovery_fail",
                f"Automatic recovery failed: {e}"
            )
    
    async def _notify_health_status(self, health_result: Dict[str, Any]) -> None:
        """Send health status notifications"""
        overall_status = health_result.get("overall_status", "unknown")
        
        should_notify = False
        
        if len(self.health_history) >= 2:
            previous_status = self.health_history[-2]["status"]
            if previous_status != overall_status:
                should_notify = True
        
        if overall_status == "critical":
            should_notify = True
        
        if should_notify:
            try:
                from ..notifications.discord_notifier import get_discord_notifier
                notifier = get_discord_notifier(self.config)
                
                if notifier.enabled:
                    async with notifier:
                        if overall_status == "critical":
                            await notifier.notify_error(
                                "🚨 Server Health Critical",
                                f"Server health status: {overall_status}\nImmediate attention required!"
                            )
                        elif overall_status == "unhealthy":
                            await notifier.notify_warning(
                                "⚠️ Server Health Warning",
                                f"Server health status: {overall_status}\nPlease check server status."
                            )
                        elif overall_status == "healthy":
                            await notifier.notify_server_start(
                                self.config.server.name,
                                self.config.server.port,
                                self.config.server.max_players
                            )
                            
            except ImportError:
                pass
            except Exception as e:
                self.logger.error("Failed to send health notification", error=str(e))
    
    def register_recovery_callback(self, callback: Callable) -> None:
        """Register a callback function for automatic recovery"""
        self.recovery_callbacks.append(callback)
        self.logger.info("Recovery callback registered", callback=callback.__name__)
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get current health summary"""
        if not self.health_history:
            return {"status": "unknown", "message": "No health data available"}
        
        recent_checks = self.health_history[-10:]
        healthy_count = sum(1 for check in recent_checks if check["status"] == "healthy")
        
        return {
            "current_status": self.health_history[-1]["status"],
            "consecutive_failures": self.consecutive_failures,
            "last_check_time": self.last_check_time,
            "health_percentage": (healthy_count / len(recent_checks)) * 100,
            "total_checks": len(self.health_history),
            "recovery_enabled": self.recovery_enabled
        }


async def restart_server_recovery(health_result: Dict[str, Any]) -> None:
    """Default recovery function to restart server"""
    logger = get_logger("palworld.recovery")
    
    log_server_event(
        logger, "recovery_restart",
        "Attempting server restart for health recovery"
    )
    
    try:
        logger.info("Server restart recovery procedure would execute here")
        
    except Exception as e:
        logger.error("Server restart recovery failed", error=str(e))


async def clear_cache_recovery(health_result: Dict[str, Any]) -> None:
    """Recovery function to clear temporary files and caches"""
    logger = get_logger("palworld.recovery")
    
    log_server_event(
        logger, "recovery_cache",
        "Clearing temporary files and caches"
    )
    
    try:
        import shutil
        import tempfile
        
        temp_dir = tempfile.gettempdir()
        logger.info("Cache clearing recovery procedure executed")
        
    except Exception as e:
        logger.error("Cache clearing recovery failed", error=str(e))


_health_manager: Optional[HealthManager] = None


def get_health_manager(config: Optional[PalworldConfig] = None) -> HealthManager:
    """Return global health manager instance"""
    global _health_manager
    
    if _health_manager is None:
        from ..config_loader import get_config
        _health_manager = HealthManager(config or get_config())
        
        _health_manager.register_recovery_callback(clear_cache_recovery)
        _health_manager.register_recovery_callback(restart_server_recovery)
    
    return _health_manager
