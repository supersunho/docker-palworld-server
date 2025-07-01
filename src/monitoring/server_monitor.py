#!/usr/bin/env python3
"""
Server status monitoring system for Palworld server
Tracks server health, performance metrics, and status changes
"""

import asyncio
import time
from typing import Dict, Optional, Callable, Awaitable
from dataclasses import dataclass
from enum import Enum

from ..config_loader import PalworldConfig
from ..logging_setup import get_logger


class ServerEventType(Enum):
    """Server event types"""
    STATUS_CHANGED = "status_changed"
    HEALTH_WARNING = "health_warning"
    PERFORMANCE_ISSUE = "performance_issue"


@dataclass
class ServerEvent:
    """Server event data structure"""
    event_type: ServerEventType
    message: str
    details: Dict
    timestamp: float


@dataclass
class ServerStatus:
    """Server status data structure"""
    is_running: bool
    pid: Optional[int]
    uptime: float
    player_count: int
    last_check: float


class ServerMonitor:
    """Monitor Palworld server status and performance"""
    
    def __init__(self, config: PalworldConfig, process_manager, api_manager):
        """
        Initialize server monitor
        
        Args:
            config: Server configuration
            process_manager: Process manager for server control
            api_manager: API manager for server communication
        """
        self.config = config
        self.process_manager = process_manager
        self.api_manager = api_manager
        self.logger = get_logger("palworld.monitoring.server")
        
        # Monitoring state
        self._monitoring_active = False
        self._shutdown_event = asyncio.Event()
        self._last_status: Optional[ServerStatus] = None
        
        # Event callbacks
        self._event_callbacks: Dict[ServerEventType, list] = {
            ServerEventType.STATUS_CHANGED: [],
            ServerEventType.HEALTH_WARNING: [],
            ServerEventType.PERFORMANCE_ISSUE: []
        }
        
        # Monitoring configuration
        self._check_interval = 30  # seconds
        self._health_check_interval = 300  # 5 minutes
        self._last_health_check = 0
    
    def add_event_callback(
        self, 
        event_type: ServerEventType, 
        callback: Callable[[ServerEvent], Awaitable[None]]
    ) -> None:
        """
        Add callback for server events
        
        Args:
            event_type: Type of event to listen for
            callback: Async callback function
        """
        self._event_callbacks[event_type].append(callback)
        self.logger.debug(f"Added callback for {event_type.value} events")
    
    async def start_monitoring(self) -> None:
        """Start server status monitoring"""
        if self._monitoring_active:
            self.logger.warning("Server monitoring already active")
            return
        
        self._monitoring_active = True
        self._shutdown_event.clear()
        self.logger.info("Starting server status monitoring")
        
        try:
            await self._monitoring_loop()
        except Exception as e:
            self.logger.error(f"Server monitoring failed: {e}")
        finally:
            self._monitoring_active = False
            self.logger.info("Server status monitoring stopped")
    
    async def stop_monitoring(self) -> None:
        """Stop server monitoring"""
        if not self._monitoring_active:
            return
        
        self.logger.info("Stopping server monitoring")
        self._shutdown_event.set()
    
    async def _monitoring_loop(self) -> None:
        """Main server monitoring loop"""
        monitor_cycle = 0
        
        while not self._shutdown_event.is_set():
            try:
                monitor_cycle += 1
                current_time = time.time()
                
                # Get current server status
                current_status = await self._get_server_status()
                
                # Check for status changes
                if self._last_status:
                    await self._check_status_changes(current_status)
                
                # Periodic health checks
                if current_time - self._last_health_check > self._health_check_interval:
                    await self._perform_health_check(current_status)
                    self._last_health_check = current_time
                
                # Update tracking state
                self._last_status = current_status
                
                # Log status periodically
                if monitor_cycle % 6 == 0:  # Every 3 minutes
                    status_msg = "Running" if current_status.is_running else "Stopped"
                    self.logger.info(
                        f"Server status: {status_msg} "
                        f"(Players: {current_status.player_count}, "
                        f"PID: {current_status.pid})"
                    )
                
            except Exception as e:
                self.logger.error(f"Server monitoring cycle error: {e}")
            
            # Wait before next check
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(), 
                    timeout=self._check_interval
                )
                break  # Shutdown requested
            except asyncio.TimeoutError:
                continue  # Normal timeout, continue monitoring
    
    async def _get_server_status(self) -> ServerStatus:
        """Get current server status"""
        # Get process status
        process_status = self.process_manager.get_server_status()
        is_running = process_status.get('running', False)
        pid = process_status.get('pid')
        uptime = process_status.get('uptime', 0)
        
        # Get player count from API if available
        player_count = 0
        try:
            players_response = await self.api_manager.api_get_players()
            if players_response and 'players' in players_response:
                player_count = len(players_response['players'])
        except Exception as e:
            self.logger.debug(f"Could not get player count: {e}")
        
        return ServerStatus(
            is_running=is_running,
            pid=pid,
            uptime=uptime,
            player_count=player_count,
            last_check=time.time()
        )
    
    async def _check_status_changes(self, current_status: ServerStatus) -> None:
        """Check for significant status changes"""
        if not self._last_status:
            return
        
        # Check for server start/stop
        if current_status.is_running != self._last_status.is_running:
            if current_status.is_running:
                event = ServerEvent(
                    event_type=ServerEventType.STATUS_CHANGED,
                    message="Server started",
                    details={
                        "pid": current_status.pid,
                        "previous_status": "stopped"
                    },
                    timestamp=time.time()
                )
            else:
                event = ServerEvent(
                    event_type=ServerEventType.STATUS_CHANGED,
                    message="Server stopped",
                    details={
                        "previous_pid": self._last_status.pid,
                        "uptime": self._last_status.uptime
                    },
                    timestamp=time.time()
                )
            
            await self._trigger_event_callbacks(event)
        
        # Check for PID changes (unexpected restarts)
        elif (current_status.is_running and self._last_status.is_running and 
              current_status.pid != self._last_status.pid):
            event = ServerEvent(
                event_type=ServerEventType.STATUS_CHANGED,
                message="Server process restarted",
                details={
                    "old_pid": self._last_status.pid,
                    "new_pid": current_status.pid,
                    "restart_type": "unexpected"
                },
                timestamp=time.time()
            )
            await self._trigger_event_callbacks(event)
    
    async def _perform_health_check(self, current_status: ServerStatus) -> None:
        """Perform comprehensive health check"""
        if not current_status.is_running:
            return
        
        health_issues = []
        
        # Check API responsiveness
        try:
            start_time = time.time()
            server_info = await self.api_manager.api_get_server_info()
            response_time = (time.time() - start_time) * 1000
            
            if response_time > 5000:  # 5 seconds
                health_issues.append(f"Slow API response: {response_time:.0f}ms")
            elif server_info is None:
                health_issues.append("API not responding")
        except Exception as e:
            health_issues.append(f"API health check failed: {e}")
        
        # Check for long uptime without players (potential issue)
        if (current_status.uptime > 3600 and  # 1 hour
            current_status.player_count == 0):
            health_issues.append("Server running without players for over 1 hour")
        
        # Trigger health warning events if issues found
        if health_issues:
            event = ServerEvent(
                event_type=ServerEventType.HEALTH_WARNING,
                message="Server health issues detected",
                details={
                    "issues": health_issues,
                    "uptime": current_status.uptime,
                    "player_count": current_status.player_count
                },
                timestamp=time.time()
            )
            await self._trigger_event_callbacks(event)
    
    async def _trigger_event_callbacks(self, event: ServerEvent) -> None:
        """Trigger all registered callbacks for an event"""
        callbacks = self._event_callbacks.get(event.event_type, [])
        
        for callback in callbacks:
            try:
                await callback(event)
            except Exception as e:
                self.logger.error(f"Server event callback error for {event.event_type.value}: {e}")
    
    def get_last_status(self) -> Optional[ServerStatus]:
        """Get last known server status"""
        return self._last_status
    
    def is_monitoring_active(self) -> bool:
        """Check if monitoring is currently active"""
        return self._monitoring_active
