#!/usr/bin/env python3
"""
Player monitoring system for Palworld server
Detects player join/leave events and tracks player states
"""

import asyncio
import time
from typing import Set, Dict, Optional, Callable, Awaitable
from dataclasses import dataclass
from enum import Enum

from ..config_loader import PalworldConfig
from ..logging_setup import get_logger


class PlayerEventType(Enum):
    """Player event types"""
    JOINED = "joined"
    LEFT = "left"


@dataclass
class PlayerEvent:
    """Player event data structure"""
    event_type: PlayerEventType
    player_name: str
    player_count: int
    timestamp: float


class PlayerMonitor:
    """Monitor player join/leave events from Palworld server API"""
    
    def __init__(self, config: PalworldConfig, api_manager):
        """
        Initialize player monitor
        
        Args:
            config: Server configuration
            api_manager: API manager for server communication
        """
        self.config = config
        self.api_manager = api_manager
        self.logger = get_logger("palworld.monitoring.players")
        
        # Player tracking state
        self._previous_players: Set[str] = set()
        self._first_check = True
        self._monitoring_active = False
        self._shutdown_event = asyncio.Event()
        
        # Event callbacks
        self._event_callbacks: Dict[PlayerEventType, list] = {
            PlayerEventType.JOINED: [],
            PlayerEventType.LEFT: []
        }
        
        # Monitoring configuration
        self._check_interval = 10  # seconds
        self._retry_count = 3
        self._retry_delay = 5  # seconds
    
    def add_event_callback(
        self, 
        event_type: PlayerEventType, 
        callback: Callable[[PlayerEvent], Awaitable[None]]
    ) -> None:
        """
        Add callback for player events
        
        Args:
            event_type: Type of event to listen for
            callback: Async callback function
        """
        self._event_callbacks[event_type].append(callback)
        self.logger.debug(f"Added callback for {event_type.value} events")
    
    async def start_monitoring(self) -> None:
        """Start player monitoring loop"""
        if self._monitoring_active:
            self.logger.warning("Player monitoring already active")
            return
        
        self._monitoring_active = True
        self._shutdown_event.clear()
        self.logger.info("Starting player monitoring")
        
        try:
            await self._monitoring_loop()
        except Exception as e:
            self.logger.error(f"Player monitoring failed: {e}")
        finally:
            self._monitoring_active = False
            self.logger.info("Player monitoring stopped")
    
    async def stop_monitoring(self) -> None:
        """Stop player monitoring"""
        if not self._monitoring_active:
            return
        
        self.logger.info("Stopping player monitoring")
        self._shutdown_event.set()
    
    async def _monitoring_loop(self) -> None:
        """Main monitoring loop with error handling"""
        monitor_cycle = 0
        
        while not self._shutdown_event.is_set():
            try:
                monitor_cycle += 1
                
                # Log monitoring activity periodically
                if monitor_cycle % 30 == 0:  # Every 5 minutes
                    self.logger.info(f"Player monitoring active (cycle {monitor_cycle})")
                
                # Get current players with retry logic
                current_players = await self._get_current_players_with_retry()
                
                # Process player changes if not first check
                if not self._first_check and current_players is not None:
                    await self._process_player_changes(current_players)
                
                # Update tracking state
                if current_players is not None:
                    self._previous_players = current_players
                    self._first_check = False
                
                # Log current state periodically
                if monitor_cycle % 60 == 0:  # Every 10 minutes
                    self.logger.info(f"Currently tracking {len(self._previous_players)} players")
                
            except Exception as e:
                self.logger.error(f"Monitoring cycle error: {e}")
                # Continue monitoring despite errors
            
            # Wait before next check
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(), 
                    timeout=self._check_interval
                )
                break  # Shutdown requested
            except asyncio.TimeoutError:
                continue  # Normal timeout, continue monitoring
    
    async def _get_current_players_with_retry(self) -> Optional[Set[str]]:
        """Get current player list with retry logic"""
        for attempt in range(self._retry_count):
            try:
                players_response = await self.api_manager.api_get_players()
                
                if players_response and 'players' in players_response:
                    player_names = {
                        player.get('name', 'Unknown') 
                        for player in players_response['players']
                        if player.get('name')
                    }
                    return player_names
                elif players_response is not None:
                    # Valid response but no players
                    return set()
                else:
                    # API call failed
                    if attempt < self._retry_count - 1:
                        self.logger.warning(f"Player API call failed (attempt {attempt + 1})")
                        await asyncio.sleep(self._retry_delay)
                    else:
                        self.logger.error("Player API call failed after all retries")
                    continue
                    
            except Exception as e:
                if attempt < self._retry_count - 1:
                    self.logger.warning(f"Player API error (attempt {attempt + 1}): {e}")
                    await asyncio.sleep(self._retry_delay)
                else:
                    self.logger.error(f"Player API error after all retries: {e}")
                continue
        
        return None
    
    async def _process_player_changes(self, current_players: Set[str]) -> None:
        """Process player join/leave events"""
        # Detect joined players
        joined_players = current_players - self._previous_players
        # Detect left players
        left_players = self._previous_players - current_players
        
        current_count = len(current_players)
        timestamp = time.time()
        
        # Process joined players
        for player_name in joined_players:
            event = PlayerEvent(
                event_type=PlayerEventType.JOINED,
                player_name=player_name,
                player_count=current_count,
                timestamp=timestamp
            )
            await self._trigger_event_callbacks(event)
            self.logger.info(f"Player joined: {player_name} (total: {current_count})")
        
        # Process left players
        for player_name in left_players:
            event = PlayerEvent(
                event_type=PlayerEventType.LEFT,
                player_name=player_name,
                player_count=current_count,
                timestamp=timestamp
            )
            await self._trigger_event_callbacks(event)
            self.logger.info(f"Player left: {player_name} (total: {current_count})")
    
    async def _trigger_event_callbacks(self, event: PlayerEvent) -> None:
        """Trigger all registered callbacks for an event"""
        callbacks = self._event_callbacks.get(event.event_type, [])
        
        for callback in callbacks:
            try:
                await callback(event)
            except Exception as e:
                self.logger.error(f"Event callback error for {event.event_type.value}: {e}")
    
    def get_current_player_count(self) -> int:
        """Get current player count"""
        return len(self._previous_players)
    
    def get_current_players(self) -> Set[str]:
        """Get current player names"""
        return self._previous_players.copy()
    
    def is_monitoring_active(self) -> bool:
        """Check if monitoring is currently active"""
        return self._monitoring_active
