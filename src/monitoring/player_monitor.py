#!/usr/bin/env python3
"""
Enhanced Player monitoring system with detailed debugging
Fixed logic issues for proper player detection  
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
        
        # Debug counters for tracking performance
        self._debug_cycle_count = 0
        self._successful_api_calls = 0
        self._failed_api_calls = 0
    
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
        self.logger.info(f"Added callback for {event_type.value} events. Total callbacks: {len(self._event_callbacks[event_type])}")
    
    async def start_monitoring(self) -> None:
        """Start player monitoring loop with enhanced error handling"""
        if self._monitoring_active:
            self.logger.warning("Player monitoring already active")
            return
        
        self._monitoring_active = True
        self._shutdown_event.clear()
        self.logger.info("Starting player monitoring with enhanced debugging")
        
        try:
            await self._monitoring_loop()
        except Exception as e:
            self.logger.error(f"Player monitoring failed: {e}", exc_info=True)
        finally:
            self._monitoring_active = False
            self.logger.info(f"Player monitoring stopped. Stats: API calls successful={self._successful_api_calls}, failed={self._failed_api_calls}")
    
    async def stop_monitoring(self) -> None:
        """Stop player monitoring gracefully"""
        if not self._monitoring_active:
            return
        
        self.logger.info("Stopping player monitoring")
        self._shutdown_event.set()
    
    async def _monitoring_loop(self) -> None:
        """Main monitoring loop with enhanced debugging and error handling"""
        self.logger.info("Player monitoring loop started")
        
        while not self._shutdown_event.is_set():
            try:
                self._debug_cycle_count += 1
                cycle_start_time = time.time()
                
                # Log monitoring activity every 5 cycles (50 seconds)
                if self._debug_cycle_count % 5 == 0:
                    self.logger.info(f"Player monitoring cycle #{self._debug_cycle_count} - Active for {self._debug_cycle_count * 10} seconds")
                
                # Get current players with enhanced debugging
                current_players = await self._get_current_players_with_debug()
                
                # FIXED: Process first check properly - initialize but don't trigger false join events
                if current_players is not None:
                    if self._first_check:
                        # First check: Initialize player list but don't trigger join events for existing players
                        self.logger.info(f"First check completed. Found {len(current_players)} existing players: {list(current_players)}")
                        self._previous_players = current_players
                        self._first_check = False
                    else:
                        # Normal monitoring: Process all player changes
                        await self._process_player_changes_with_debug(current_players)
                        self._previous_players = current_players
                
                # Log monitoring statistics periodically
                if self._debug_cycle_count % 6 == 0:  # Every minute
                    success_rate = f"{self._successful_api_calls}/{self._successful_api_calls + self._failed_api_calls}" if (self._successful_api_calls + self._failed_api_calls) > 0 else "0/0"
                    self.logger.info(f"Monitoring status: Tracking {len(self._previous_players)} players, API success rate: {success_rate}")
                
                # Warn if monitoring cycle takes too long
                cycle_time = (time.time() - cycle_start_time) * 1000
                if cycle_time > 1000:  # More than 1 second
                    self.logger.warning(f"Monitoring cycle took {cycle_time:.0f}ms - performance issue detected")
                
            except Exception as e:
                self.logger.error(f"Monitoring cycle #{self._debug_cycle_count} error: {e}", exc_info=True)
            
            # Wait before next check with proper shutdown handling
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(), 
                    timeout=self._check_interval
                )
                break  # Shutdown requested
            except asyncio.TimeoutError:
                continue  # Normal timeout, continue monitoring
    
    async def _get_current_players_with_debug(self) -> Optional[Set[str]]:
        """Get current player list with enhanced debugging and flexible response parsing"""
        for attempt in range(self._retry_count):
            try:
                api_start_time = time.time()
                players_response = await self.api_manager.api_get_players()
                api_time = (time.time() - api_start_time) * 1000
                
                # Enhanced API response analysis
                self.logger.debug(f"API call completed in {api_time:.1f}ms (attempt {attempt + 1})")
                self.logger.debug(f"API response type: {type(players_response)}")
                self.logger.debug(f"API response content: {players_response}")
                
                if players_response is None:
                    self.logger.warning(f"API returned None (attempt {attempt + 1})")
                    self._failed_api_calls += 1
                    if attempt < self._retry_count - 1:
                        await asyncio.sleep(self._retry_delay)
                        continue
                    return None
                
                # ENHANCED: Handle different API response structures
                player_names = set()
                
                if isinstance(players_response, dict):
                    # Check for standard structure: {"players": [...]}
                    if 'players' in players_response:
                        players_list = players_response['players']
                        self.logger.debug(f"Found 'players' key with {len(players_list)} items")
                    # Check for alternative structure: {"data": [...]}
                    elif 'data' in players_response:
                        players_list = players_response['data']
                        self.logger.debug(f"Found 'data' key with {len(players_list)} items")
                    # Handle unknown structure
                    else:
                        self.logger.warning(f"Unexpected response structure. Available keys: {list(players_response.keys())}")
                        players_list = []
                elif isinstance(players_response, list):
                    # Handle direct list response
                    players_list = players_response
                    self.logger.debug(f"Direct list response with {len(players_list)} items")
                else:
                    self.logger.error(f"Unexpected response type: {type(players_response)}")
                    self._failed_api_calls += 1
                    if attempt < self._retry_count - 1:
                        await asyncio.sleep(self._retry_delay)
                        continue
                    return None
                
                # ENHANCED: Extract player names with multiple fallback keys
                for i, player in enumerate(players_list):
                    if isinstance(player, dict):
                        # Try different possible name keys for compatibility
                        name = (player.get('name') or 
                               player.get('playerName') or 
                               player.get('player_name') or 
                               player.get('username'))
                        
                        if name and isinstance(name, str) and name.strip():
                            player_names.add(name.strip())
                            self.logger.debug(f"Extracted player name: '{name.strip()}'")
                        else:
                            self.logger.warning(f"Player {i} has invalid name field: {player}")
                    else:
                        self.logger.warning(f"Player {i} is not a dictionary: {player}")
                
                self._successful_api_calls += 1
                self.logger.debug(f"Successfully extracted {len(player_names)} player names: {list(player_names)}")
                return player_names
                
            except Exception as e:
                self.logger.error(f"API call exception (attempt {attempt + 1}): {e}", exc_info=True)
                self._failed_api_calls += 1
                if attempt < self._retry_count - 1:
                    await asyncio.sleep(self._retry_delay)
                else:
                    self.logger.error(f"All {self._retry_count} API attempts failed")
        
        return None
    
    async def _process_player_changes_with_debug(self, current_players: Set[str]) -> None:
        """Process player join/leave events with enhanced debugging"""
        # Detect player changes
        joined_players = current_players - self._previous_players
        left_players = self._previous_players - current_players
        
        current_count = len(current_players)
        timestamp = time.time()
        
        # Log any player changes detected
        if joined_players or left_players:
            self.logger.info(f"Player changes detected - Joined: {list(joined_players)}, Left: {list(left_players)}")
        
        # Process joined players with callback debugging
        for player_name in joined_players:
            event = PlayerEvent(
                event_type=PlayerEventType.JOINED,
                player_name=player_name,
                player_count=current_count,
                timestamp=timestamp
            )
            
            self.logger.info(f"Player joined: {player_name} (total: {current_count})")
            
            # Debug callback execution
            callbacks = self._event_callbacks.get(PlayerEventType.JOINED, [])
            self.logger.debug(f"Triggering {len(callbacks)} join callbacks for {player_name}")
            
            await self._trigger_event_callbacks_with_debug(event)
        
        # Process left players with callback debugging
        for player_name in left_players:
            event = PlayerEvent(
                event_type=PlayerEventType.LEFT,
                player_name=player_name,
                player_count=current_count,
                timestamp=timestamp
            )
            
            self.logger.info(f"Player left: {player_name} (total: {current_count})")
            
            # Debug callback execution
            callbacks = self._event_callbacks.get(PlayerEventType.LEFT, [])
            self.logger.debug(f"Triggering {len(callbacks)} leave callbacks for {player_name}")
            
            await self._trigger_event_callbacks_with_debug(event)
    
    async def _trigger_event_callbacks_with_debug(self, event: PlayerEvent) -> None:
        """Trigger all registered callbacks for an event with debugging"""
        callbacks = self._event_callbacks.get(event.event_type, [])
        
        if not callbacks:
            self.logger.warning(f"No callbacks registered for {event.event_type.value} events!")
            return
        
        # Execute each callback with performance monitoring
        for i, callback in enumerate(callbacks):
            try:
                callback_start_time = time.time()
                await callback(event)
                callback_time = (time.time() - callback_start_time) * 1000
                self.logger.debug(f"Callback {i+1} for {event.event_type.value} completed in {callback_time:.1f}ms")
            except Exception as e:
                self.logger.error(f"Event callback {i+1} error for {event.event_type.value}: {e}", exc_info=True)
    
    def get_current_player_count(self) -> int:
        """Get current player count"""
        return len(self._previous_players)
    
    def get_current_players(self) -> Set[str]:
        """Get current player names"""
        return self._previous_players.copy()
    
    def is_monitoring_active(self) -> bool:
        """Check if monitoring is currently active"""
        return self._monitoring_active
    
    def get_debug_stats(self) -> dict:
        """Get comprehensive debugging statistics"""
        return {
            "monitoring_active": self._monitoring_active,
            "debug_cycle_count": self._debug_cycle_count,
            "successful_api_calls": self._successful_api_calls,
            "failed_api_calls": self._failed_api_calls,
            "api_success_rate": f"{self._successful_api_calls}/{self._successful_api_calls + self._failed_api_calls}" if (self._successful_api_calls + self._failed_api_calls) > 0 else "0/0",
            "current_player_count": len(self._previous_players),
            "current_players": list(self._previous_players),
            "registered_callbacks": {
                event_type.value: len(callbacks) 
                for event_type, callbacks in self._event_callbacks.items()
            },
            "first_check_completed": not self._first_check,
            "check_interval_seconds": self._check_interval,
            "retry_configuration": {
                "retry_count": self._retry_count,
                "retry_delay_seconds": self._retry_delay
            }
        }
