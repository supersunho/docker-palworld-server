#!/usr/bin/env python3
"""
RCON client for Palworld server management
Handles server commands via RCON protocol using rcon-cli binary
"""

import asyncio
import os
import time
from typing import Optional

from ..config_loader import PalworldConfig
from ..logging_setup import log_server_event, log_api_call


class RconClient:
    """Palworld RCON client using rcon-cli binary"""

    # Reachability probe cadence. The probe fires at most once per window to
    # avoid hammering the server. Tuned for the typical monitor tick (30-60s)
    # so the availability flag stays fresh without added RCON load.
    _PROBE_INTERVAL_SECONDS = 60.0

    # Maximum sleep between retry attempts. Caps the exponential backoff so
    # a future tuning change (higher retry_count or _retry_delay) cannot
    # cause a single command to block for an unbounded amount of time.
    _MAX_BACKOFF_SECONDS = 30.0

    def __init__(self, config: PalworldConfig, logger):
        self.config = config
        self.logger = logger
        self.host = config.rcon.host
        self.port = config.rcon.port
        self.password = config.server.admin_password
        self._retry_count = 3
        self._retry_delay = 2.0
        self._is_connected = False
        # Reachability probe state. ``_last_probe_at`` is the wall-clock time
        # of the most recent probe; ``_last_probe_success`` records whether
        # that probe actually reached the RCON server (distinct from
        # ``_is_connected`` which only reflects rcon-cli availability).
        self._last_probe_at: float = 0.0
        self._last_probe_success: bool = False

    async def __aenter__(self):
        """Test rcon-cli availability and initialize connection"""
        if not self.config.rcon.enabled:
            self.logger.warning("RCON is not enabled in configuration")
            return self

        try:
            process = await asyncio.create_subprocess_exec(
                "rcon-cli", "--help", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            if process.returncode == 0:
                self._is_connected = True
                log_server_event(self.logger, "rcon_connect", "rcon-cli available and ready")
            else:
                self.logger.error("rcon-cli not available")
        except FileNotFoundError:
            self.logger.error("rcon-cli binary not found")

        return self

    async def probe_reachable(self, force: bool = False) -> bool:
        """Verify the RCON server is actually reachable, not just rcon-cli.

        The probe sends a lightweight ``Info`` command at most once per
        ``_PROBE_INTERVAL_SECONDS`` unless ``force=True``. Failures clear the
        cached success so callers (e.g. ``_is_rcon_available``) stop treating
        RCON as available until the next successful round-trip.
        """
        now = time.time()
        if (
            not force
            and self._last_probe_at != 0.0
            and (now - self._last_probe_at) < self._PROBE_INTERVAL_SECONDS
        ):
            return self._last_probe_success

        if not self._is_connected:
            return False

        result = await self._execute_command_with_retry("Info", retry_count=0)
        self._last_probe_at = now
        self._last_probe_success = result is not None
        if not self._last_probe_success:
            self.logger.debug("RCON reachability probe failed")
        return self._last_probe_success

    @property
    def last_probe_success(self) -> bool:
        """Whether the most recent reachability probe succeeded."""
        return self._last_probe_success

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close RCON client context"""
        if self._is_connected:
            log_server_event(self.logger, "rcon_disconnect", "RCON client context closed")
            self._is_connected = False

    async def _execute_command_with_retry(
        self, command: str, *args: str, retry_count: Optional[int] = None
    ) -> Optional[str]:
        """Execute RCON command with retry logic"""
        if not self._is_connected:
            self.logger.error("RCON not connected")
            return None

        if retry_count is None:
            retry_count = self._retry_count

        cmd = ["rcon-cli", "--host", self.host, "--port", str(self.port), command]
        cmd.extend(args)

        env = os.environ.copy()
        env["RCON_PASSWORD"] = self.password

        for attempt in range(retry_count + 1):
            try:
                start_time = time.time()

                process = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env
                )

                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)

                duration_ms = (time.time() - start_time) * 1000

                if process.returncode == 0:
                    response = stdout.decode("utf-8").strip()
                    log_api_call(
                        self.logger, f"rcon:{command}", 200, duration_ms, attempt=attempt + 1
                    )
                    return response
                else:
                    error_msg = stderr.decode("utf-8").strip()
                    log_api_call(
                        self.logger,
                        f"rcon:{command}",
                        process.returncode,
                        duration_ms,
                        attempt=attempt + 1,
                        error=error_msg,
                    )

                    if attempt < retry_count:
                        await asyncio.sleep(self._backoff_for(attempt))
                        continue
                    else:
                        return None

            except Exception as e:
                if attempt < retry_count:
                    await asyncio.sleep(self._backoff_for(attempt))
                    continue
                else:
                    self.logger.error("RCON command final failure", command=command, error=str(e))
                    return None

        return None

    def _backoff_for(self, attempt: int) -> float:
        """Compute the sleep duration for retry ``attempt``.

        Exponential growth (``_retry_delay * 2**attempt``) capped at
        :attr:`_MAX_BACKOFF_SECONDS` so a single command cannot block
        indefinitely even if a future tuning raises ``_retry_count``.
        """
        return min(self._retry_delay * (2**attempt), self._MAX_BACKOFF_SECONDS)

    async def get_server_info(self) -> Optional[str]:
        """Get server information"""
        return await self._execute_command_with_retry("Info")

    async def get_players(self) -> Optional[str]:
        """Get online player list"""
        return await self._execute_command_with_retry("ShowPlayers")

    async def announce_message(self, message: str) -> bool:
        """Announce message to all players"""
        result = await self._execute_command_with_retry("Broadcast", message)
        return result is not None

    async def kick_player(self, player_name: str) -> bool:
        """Kick player from server"""
        result = await self._execute_command_with_retry("KickPlayer", player_name)
        return result is not None

    async def ban_player(self, player_name: str) -> bool:
        """Ban player from server"""
        result = await self._execute_command_with_retry("BanPlayer", player_name)
        return result is not None

    async def save_world(self) -> bool:
        """Save world data"""
        result = await self._execute_command_with_retry("Save")
        return result is not None

    async def shutdown_server(self, waittime: int = 1, message: str = "Server shutdown") -> bool:
        """Shutdown server gracefully"""
        result = await self._execute_command_with_retry("Shutdown", str(waittime), message)
        return result is not None

    async def get_server_settings(self) -> Optional[str]:
        """Get server settings"""
        return await self._execute_command_with_retry("GetServerSettings")

    async def execute_custom_command(self, command: str, *args: str) -> Optional[str]:
        """Execute custom RCON command"""
        return await self._execute_command_with_retry(command, *args)
