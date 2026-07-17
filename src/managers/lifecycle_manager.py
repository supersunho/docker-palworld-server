#!/usr/bin/env python3
"""
Server lifecycle management for Palworld server
Handles server start, stop, restart, and startup verification
"""

import asyncio
import time
from typing import Optional, Any

from ..config_loader import PalworldConfig
from .process_manager import ProcessManager
from ..logging_setup import get_logger, log_server_event


async def verify_server_startup(process_manager, max_wait_time: int = 30) -> bool:
    """Verify that the Palworld server process is running and stable"""
    logger = get_logger("palworld.startup_verification")

    logger.info("Verifying server process startup...")

    if not process_manager.is_server_running():
        logger.error("Server process is not running")
        return False

    stability_check_duration = min(10, max_wait_time)
    logger.info(f"Checking process stability for {stability_check_duration} seconds...")

    start_time = time.time()
    while (time.time() - start_time) < stability_check_duration:
        if not process_manager.is_server_running():
            logger.error("Server process crashed during stability check")
            return False
        await asyncio.sleep(1)

    logger.info("Server process is running and stable")
    return True


class ServerLifecycleManager:
    """Server process lifecycle management with startup verification"""

    def __init__(
        self, config: PalworldConfig, logger=None, process_manager: Optional[ProcessManager] = None
    ):
        self.config = config
        self.logger = logger or get_logger("palworld.lifecycle")
        self.process_manager = process_manager or ProcessManager(config, self.logger)

    async def start(self) -> bool:
        """Start Palworld server with verification"""
        success = await self.process_manager.start_server()
        if not success:
            self.logger.error("Failed to start server process")
            return False

        self.logger.info("Server process started, verifying startup...")

        process_stable = await verify_server_startup(self.process_manager, max_wait_time=30)
        if not process_stable:
            self.logger.error("Server process is not stable")
            return False

        self.logger.info("Server started successfully and is stable")
        return True

    async def stop(self, graceful: bool = True, message: str = "Server is shutting down") -> bool:
        """Stop Palworld server"""
        if not self.process_manager.is_server_running():
            self.logger.info("Server is already stopped")
            return True

        if graceful:
            return await self.process_manager.stop_server(message)
        else:
            # Force stop without graceful shutdown
            import os
            import signal

            if self.process_manager.server_process:
                try:
                    os.killpg(self.process_manager.server_process.pid, signal.SIGTERM)
                    try:
                        self.process_manager.server_process.wait(timeout=10)
                    except asyncio.TimeoutError:
                        os.killpg(self.process_manager.server_process.pid, signal.SIGKILL)
                        self.process_manager.server_process.wait()

                    # Clean up zombie process
                    try:
                        self.process_manager.server_process.communicate(timeout=2)
                    except Exception:
                        pass

                    self.logger.info("Server force stopped successfully")
                    return True
                except Exception as e:
                    self.logger.error(f"Failed to force stop server: {e}")
                    return False
            else:
                self.logger.error("No server process to stop")
                return False

    async def restart(self) -> bool:
        """Restart Palworld server"""
        self.logger.info("Restarting server...")

        # Stop the server first
        stop_success = await self.stop(graceful=True, message="Server restarting")
        if not stop_success:
            self.logger.error("Failed to stop server for restart")
            return False

        # Wait a bit before starting again
        await asyncio.sleep(5)

        # Start the server
        start_success = await self.start()
        if not start_success:
            self.logger.error("Failed to start server after restart")
            return False

        self.logger.info("Server restarted successfully")
        return True

    async def verify_startup(self) -> bool:
        """Verify server startup and stability"""
        return await verify_server_startup(self.process_manager, max_wait_time=30)

    def get_server_status(self) -> dict:
        """Get server process status"""
        return self.process_manager.get_server_status()
