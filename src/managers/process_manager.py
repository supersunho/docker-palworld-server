#!/usr/bin/env python3
"""
Process management for Palworld server
Handles server process lifecycle, monitoring, and signal delivery.
"""

import asyncio
import os
import signal
import shlex
import subprocess
import time
from typing import Any, List, Optional

from ..config_loader import PalworldConfig
from ..logging_setup import log_server_event
from ..protocols import IProcessManager


class ProcessManager(IProcessManager):
    """Server process lifecycle management"""

    def __init__(self, config: PalworldConfig, logger: Any):
        self.config = config
        self.logger = logger
        self.server_path = config.paths.server_dir
        self.server_process: Optional[subprocess.Popen] = None
        self._process_start_time: Optional[float] = None
        """Timestamp (time.time) when the server process was last started."""
        self._lifecycle_lock = asyncio.Lock()
        """Lock protecting start_server / stop_server concurrency."""

    def is_server_running(self) -> bool:
        """Check if server is currently running"""
        process = self.server_process
        if process is None:
            return False

        poll_result = process.poll()
        return poll_result is None

    def _build_startup_options(self) -> List[str]:
        """Build server startup options based on configuration"""
        options = []
        startup_cfg = self.config.server_startup

        if (
            startup_cfg.use_performance_threads
            and startup_cfg.disable_async_loading
            and startup_cfg.use_multithread_for_ds
        ):
            options.extend(["-useperfthreads", "-NoAsyncLoadingThread", "-UseMultithreadForDS"])

            if startup_cfg.worker_threads_count > 0:
                options.append(f"-NumberOfWorkerThreadsServer={startup_cfg.worker_threads_count}")

        # Pass the configured query port explicitly, including the engine's
        # historical default, so the effective server command is auditable.
        options.append(f"-queryport={startup_cfg.query_port}")

        if startup_cfg.enable_public_lobby:
            options.append("-publiclobby")

        if startup_cfg.log_format != "text":
            options.append(f"-logformat={startup_cfg.log_format}")

        if startup_cfg.additional_options:
            additional_opts = shlex.split(startup_cfg.additional_options.strip())
            options.extend(additional_opts)

        return options

    def _build_server_command(self) -> List[str]:
        """Build complete server command with dynamic options"""
        server_executable = self.server_path / "PalServer.sh"
        startup_options = self._build_startup_options()

        # Always shlex.join() to prevent shell injection from path or options
        command = shlex.join([str(server_executable), *startup_options])
        if startup_options:
            log_server_event(
                self.logger,
                "server_command_build",
                "Server command with options: " + shlex.join(startup_options),
            )
        else:
            log_server_event(
                self.logger, "server_command_build", "Server command without additional options"
            )

        return ["FEXBash", "-c", command]

    async def start_server(self) -> bool:
        """Start Palworld server with dynamic configuration options"""
        async with self._lifecycle_lock:
            # Double-check after acquiring lock — a concurrent stop_server
            # may have just cleared server_process.
            if self.is_server_running():
                log_server_event(self.logger, "server_start", "Server is already running")
                return True

            server_executable = self.server_path / "PalServer.sh"

            if not server_executable.exists():
                log_server_event(
                    self.logger,
                    "server_start_fail",
                    f"Server executable not found: {server_executable}",
                )
                return False

            try:
                log_server_event(
                    self.logger, "server_start", "Starting Palworld server with dynamic options"
                )

                full_cmd = self._build_server_command()

                # Inherit parent stdout/stderr to avoid pipe deadlock with long-running process.
                # Output is captured by Docker/Supervisor logging.
                self.server_process = subprocess.Popen(
                    full_cmd,
                    cwd=str(self.server_path),
                    stdout=None,
                    stderr=None,
                    text=True,
                    start_new_session=True,
                )
                self._process_start_time = time.time()

            except Exception as e:
                self.server_process = None
                self._process_start_time = None
                log_server_event(self.logger, "server_start_fail", f"Server start error: {e}")
                return False

        # Lock released — wait for startup without holding the lock so
        # concurrent stop_server can still stop the process on startup failure.
        await asyncio.sleep(10)

        if not self.is_server_running():
            self._process_start_time = None
            log_server_event(
                self.logger, "server_start_fail", "Server start failed - check logs for details"
            )
            return False

        log_server_event(
            self.logger,
            "server_start_complete",
            "Server started successfully with configured options",
            pid=self.server_process.pid,
        )
        return True

    async def stop_server(
        self,
        message: str = "Server is shutting down",
        api_client: Optional[Any] = None,
    ) -> bool:
        """Stop Palworld server gracefully and clean up zombie processes"""
        async with self._lifecycle_lock:
            if not self.is_server_running():
                log_server_event(self.logger, "server_stop", "Server is already stopped")
                return True

            # Capture and clear the process reference atomically under lock
            # to prevent a concurrent start_server from racing with cleanup.
            process = self.server_process
            self.server_process = None
            self._process_start_time = None

        # Lock released — the API wait is long, so don't hold the lock.
        try:
            if api_client and process is not None:
                try:
                    await api_client.announce_message(f"{message}. Shutting down in 30 seconds.")
                    await asyncio.sleep(30)
                    await api_client.shutdown_server(1, message)

                    for _ in range(60):
                        if process.poll() is not None:
                            break
                        await asyncio.sleep(1)
                except Exception as e:
                    self.logger.warning(f"API graceful shutdown failed: {e}")

            if process is not None and process.poll() is None:
                log_server_event(
                    self.logger,
                    "server_force_stop",
                    "Attempting force termination of entire process group",
                )

                # Kill the entire process group (FEXBash + all child processes)
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            pass
                except ProcessLookupError:
                    # Process group already terminated
                    pass

            # Clean up zombie process
            if process is not None:
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
                except Exception:
                    pass

            log_server_event(self.logger, "server_stop_complete", "Server stopped successfully")
            return True

        except Exception as e:
            log_server_event(self.logger, "server_stop_fail", f"Server stop error: {e}")
            return False

    async def send_signal(self, sig: int) -> bool:
        """Send a signal to the server process group.

        Args:
            sig: Signal number (e.g., signal.SIGHUP, signal.SIGTERM).

        Returns:
            True if signal was sent, False if server is not running.
        """
        if not self.is_server_running():
            self.logger.warning("Cannot send signal — server is not running")
            return False

        process = self.server_process
        if process is None:
            self.logger.warning("Cannot send signal — server process disappeared")
            return False

        try:
            pid = process.pid
            os.killpg(pid, sig)
            sig_name = signal.Signals(sig).name
            log_server_event(
                self.logger,
                "server_signal",
                f"Signal {sig_name} sent to process group",
                pid=pid,
                signal=sig_name,
            )
            return True
        except ProcessLookupError:
            self.logger.warning(f"Process group not found (pid={process.pid})")
            return False
        except Exception as e:
            self.logger.error(f"Failed to send signal: {e}")
            return False

    async def reload_config(self) -> bool:
        """Trigger configuration reload by sending SIGHUP to the server.

        Returns True if SIGHUP was sent, False otherwise.
        """
        result = await self.send_signal(signal.SIGHUP)
        if result:
            log_server_event(
                self.logger, "config_hot_reload", "SIGHUP sent to server for config reload"
            )
        else:
            log_server_event(
                self.logger, "config_hot_reload_fail", "Could not send SIGHUP — server not running"
            )
        return result

    async def pause_server(self) -> bool:
        """Pause the server process by sending SIGSTOP.

        The server binary is frozen in memory (CPU 0%) and can be
        instantly resumed with SIGCONT.

        Returns:
            True if SIGSTOP was sent, False otherwise.
        """
        return await self.send_signal(signal.SIGSTOP)

    async def resume_server(self) -> bool:
        """Resume a paused server process by sending SIGCONT.

        Returns:
            True if SIGCONT was sent, False otherwise.
        """
        return await self.send_signal(signal.SIGCONT)

    def get_server_status(self) -> dict[str, Any]:
        """Get detailed server process status"""
        process = self.server_process
        if process is None or process.poll() is not None or self._process_start_time is None:
            return {"running": False, "pid": None, "uptime": 0}

        return {
            "running": True,
            "pid": process.pid,
            "uptime": time.time() - self._process_start_time,
        }

    def get_startup_options_summary(self) -> dict:
        """Get summary of current startup options configuration"""
        startup_cfg = self.config.server_startup
        options = self._build_startup_options()

        return {
            "performance_optimization": (
                startup_cfg.use_performance_threads
                and startup_cfg.disable_async_loading
                and startup_cfg.use_multithread_for_ds
            ),
            "query_port": startup_cfg.query_port,
            "public_lobby": startup_cfg.enable_public_lobby,
            "log_format": startup_cfg.log_format,
            "worker_threads": startup_cfg.worker_threads_count,
            "additional_options": startup_cfg.additional_options,
            "generated_options": options,
            "options_count": len(options),
        }
