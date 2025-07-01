#!/usr/bin/env python3
"""
Player monitoring system for Palworld server
Detects player join/leave events via API polling
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
        """Initialize player monitor"""
        self.config = config
        self.api_manager = api_manager
        self.logger = get_logger("palworld.monitoring.players")
        
        self._previous_players: Set[str] = set()
        self._first_check = True
        self._monitoring_active = False
        self._shutdown_event = asyncio.Event()
        
        self._event_callbacks: Dict[PlayerEventType, list] = {
            PlayerEventType.JOINED: [],
            PlayerEventType.LEFT: []
        }
        
        self._check_interval = 10
        self._retry_count = 3
        self._retry_delay = 5
        
        self._debug_cycle_count = 0
        self._successful_api_calls = 0
        self._failed_api_calls = 0
    
    def add_event_callback(self, event_type: PlayerEventType, callback: Callable[[PlayerEvent], Awaitable[None]]) -> None:
        """Add callback for player events"""
        self._event_callbacks[event_type].append(callback)
        self.logger.info(f"Added callback for {event_type.value} events. Total callbacks: {len(self._event_callbacks[event_type])}")
    
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
            self.logger.error(f"Player monitoring failed: {e}", exc_info=True)
        finally:
            self._monitoring_active = False
            self.logger.info(f"Player monitoring stopped. Stats: API calls successful={self._successful_api_calls}, failed={self._failed_api_calls}")
    
    async def stop_monitoring(self) -> None:
        """Stop player monitoring"""
        if not self._monitoring_active:
            return
        
        self.logger.info("Stopping player monitoring")
        self._shutdown_event.set()
    
    async def _monitoring_loop(self) -> None:
        """Main monitoring loop"""
        self.logger.info("Player monitoring loop started")
        
        while not self._shutdown_event.is_set():
            try:
                self._debug_cycle_count += 1
                cycle_start_time = time.time()
                
                if self._debug_cycle_count % 5 == 0:
                    self.logger.debug(f"Player monitoring cycle #{self._debug_cycle_count} - Active for {self._debug_cycle_count * 10} seconds")
                
                current_players = await self._get_current_players()
                
                if current_players is not None:
                    if self._first_check:
                        self.logger.info(f"First check completed. Found {len(current_players)} existing players: {list(current_players)}")
                        self._previous_players = current_players
                        self._first_check = False
                    else:
                        await self._process_player_changes(current_players)
                        self._previous_players = current_players
                
                if self._debug_cycle_count % 6 == 0:
                    success_rate = f"{self._successful_api_calls}/{self._successful_api_calls + self._failed_api_calls}" if (self._successful_api_calls + self._failed_api_calls) > 0 else "0/0"
                    self.logger.debug(f"Monitoring status: Tracking {len(self._previous_players)} players, API success rate: {success_rate}")
                
                cycle_time = (time.time() - cycle_start_time) * 1000
                if cycle_time > 1000:
                    self.logger.warning(f"Monitoring cycle took {cycle_time:.0f}ms - performance issue detected")
                
            except Exception as e:
                self.logger.error(f"Monitoring cycle #{self._debug_cycle_count} error: {e}", exc_info=True)
            
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(), 
                    timeout=self._check_interval
                )
                break
            except asyncio.TimeoutError:
                continue
    
    async def _get_current_players(self) -> Optional[Set[str]]:
        """Get current player list with retry logic"""
        for attempt in range(self._retry_count):
            try:
                api_start_time = time.time()
                players_response = await self.api_manager.api_get_players()
                api_time = (time.time() - api_start_time) * 1000
                
                self.logger.debug(f"API call completed in {api_time:.1f}ms (attempt {attempt + 1})")
                self.logger.debug(f"API response type: {type(players_response)}")
                
                if players_response is None:
                    self.logger.warning(f"API returned None (attempt {attempt + 1})")
                    self._failed_api_calls += 1
                    if attempt < self._retry_count - 1:
                        await asyncio.sleep(self._retry_delay)
                        continue
                    return None
                
                player_names = set()
                
                if isinstance(players_response, dict):
                    if 'players' in players_response:
                        players_list = players_response['players']
                    elif 'data' in players_response:
                        players_list = players_response['data']
                    else:
                        self.logger.warning(f"Unexpected response structure. Available keys: {list(players_response.keys())}")
                        players_list = []
                elif isinstance(players_response, list):
                    players_list = players_response
                else:
                    self.logger.error(f"Unexpected response type: {type(players_response)}")
                    self._failed_api_calls += 1
                    if attempt < self._retry_count - 1:
                        await asyncio.sleep(self._retry_delay)
                        continue
                    return None
                
                for i, player in enumerate(players_list):
                    if isinstance(player, dict):
                        name = (player.get('name') or 
                               player.get('playerName') or 
                               player.get('player_name') or 
                               player.get('username'))
                        
                        if name and isinstance(name, str) and name.strip():
                            player_names.add(name.strip())
                        else:
                            self.logger.warning(f"Player {i} has invalid name field: {player}")
                    else:
                        self.logger.warning(f"Player {i} is not a dictionary: {player}")
                
                self._successful_api_calls += 1
                self.logger.debug(f"Successfully extracted {len(player_names)} player names")
                return player_names
                
            except Exception as e:
                self.logger.error(f"API call exception (attempt {attempt + 1}): {e}", exc_info=True)
                self._failed_api_calls += 1
                if attempt < self._retry_count - 1:
                    await asyncio.sleep(self._retry_delay)
                else:
                    self.logger.error(f"All {self._retry_count} API attempts failed")
        
        return None
    
    async def _process_player_changes(self, current_players: Set[str]) -> None:
        """Process player join/leave events"""
        joined_players = current_players - self._previous_players
        left_players = self._previous_players - current_players
        
        current_count = len(current_players)
        timestamp = time.time()
        
        if joined_players or left_players:
            self.logger.info(f"Player changes detected - Joined: {list(joined_players)}, Left: {list(left_players)}")
        
        for player_name in joined_players:
            event = PlayerEvent(
                event_type=PlayerEventType.JOINED,
                player_name=player_name,
                player_count=current_count,
                timestamp=timestamp
            )
            
            self.logger.info(f"Player joined: {player_name} (total: {current_count})")
            
            callbacks = self._event_callbacks.get(PlayerEventType.JOINED, [])
            self.logger.debug(f"Triggering {len(callbacks)} join callbacks for {player_name}")
            
            await self._trigger_event_callbacks(event)
        
        for player_name in left_players:
            event = PlayerEvent(
                event_type=PlayerEventType.LEFT,
                player_name=player_name,
                player_count=current_count,
                timestamp=timestamp
            )
            
            self.logger.info(f"Player left: {player_name} (total: {current_count})")
            
            callbacks = self._event_callbacks.get(PlayerEventType.LEFT, [])
            self.logger.debug(f"Triggering {len(callbacks)} leave callbacks for {player_name}")
            
            await self._trigger_event_callbacks(event)
    
    async def _trigger_event_callbacks(self, event: PlayerEvent) -> None:
        """Trigger all registered callbacks for an event"""
        callbacks = self._event_callbacks.get(event.event_type, [])
        
        if not callbacks:
            self.logger.warning(f"No callbacks registered for {event.event_type.value} events!")
            return
        
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
        """Get debugging statistics"""
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
