#!/usr/bin/env python3
"""
Process management for Palworld server
Handles server process lifecycle and monitoring
"""

import asyncio
import subprocess
import time
from pathlib import Path
from typing import Optional, List

from ..config_loader import PalworldConfig
from ..logging_setup import log_server_event


class ProcessManager:
    """Server process lifecycle management"""
    
    def __init__(self, config: PalworldConfig, logger):
        self.config = config
        self.logger = logger
        self.server_path = config.paths.server_dir
        self.server_process: Optional[subprocess.Popen] = None
    
    def is_server_running(self) -> bool:
        """Check if server is currently running"""
        if self.server_process is None:
            return False
        
        poll_result = self.server_process.poll()
        return poll_result is None
    
    def _build_startup_options(self) -> List[str]:
        """
        Build server startup options based on configuration
        
        Returns:
            List of command line options for PalServer.sh
        """
        options = []
        startup_cfg = self.config.server_startup
        
        # Performance optimization options (official documentation recommended)
        if (startup_cfg.use_performance_threads and 
            startup_cfg.disable_async_loading and 
            startup_cfg.use_multithread_for_ds):
            options.extend(["-useperfthreads", "-NoAsyncLoadingThread", "-UseMultithreadForDS"])
            
            # Advanced worker threads configuration
            if startup_cfg.worker_threads_count > 0:
                options.append(f"-NumberOfWorkerThreadsServer={startup_cfg.worker_threads_count}")
        
        # Network configuration - query port (resolve 27015 port conflict)
        if startup_cfg.query_port != 27015:
            options.append(f"-queryport={startup_cfg.query_port}")
        
        # Community server settings
        if startup_cfg.enable_public_lobby:
            options.append("-publiclobby")
        
        # Logging format configuration
        if startup_cfg.log_format != "text":
            options.append(f"-logformat={startup_cfg.log_format}")
        
        # Custom additional options from user configuration
        if startup_cfg.additional_options:
            additional_opts = startup_cfg.additional_options.strip().split()
            options.extend(additional_opts)
        
        return options
    
    def _build_server_command(self) -> List[str]:
        """
        Build complete server command with dynamic options
        
        Returns:
            Complete command list for subprocess execution
        """
        server_executable = self.server_path / "PalServer.sh"
        startup_options = self._build_startup_options()
        
        # Construct command with options
        if startup_options:
            command = f"{server_executable} {' '.join(startup_options)}"
            log_server_event(self.logger, "server_command_build", 
                           f"Server command with options: {' '.join(startup_options)}")
        else:
            command = str(server_executable)
            log_server_event(self.logger, "server_command_build", 
                           "Server command without additional options")
        
        return ["FEXBash", "-c", command]
    
    def start_server(self) -> bool:
        """Start Palworld server with dynamic configuration options"""
        if self.is_server_running():
            log_server_event(self.logger, "server_start", 
                           "Server is already running")
            return True
        
        server_executable = self.server_path / "PalServer.sh"
        
        if not server_executable.exists():
            log_server_event(self.logger, "server_start_fail", 
                           f"Server executable not found: {server_executable}")
            return False
        
        try:
            log_server_event(self.logger, "server_start", 
                           "Starting Palworld server with dynamic options")
            
            # Build server command with dynamic startup options
            full_cmd = self._build_server_command()
            
            self.server_process = subprocess.Popen(
                full_cmd,
                cwd=str(self.server_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Wait for startup stabilization
            time.sleep(10)
            
            if not self.is_server_running():
                stdout, stderr = self.server_process.communicate()
                log_server_event(self.logger, "server_start_fail", 
                               f"Server start failed: {stderr}")
                return False
            
            log_server_event(self.logger, "server_start_complete", 
                           "Server started successfully with configured options", 
                           pid=self.server_process.pid)
            return True
            
        except Exception as e:
            log_server_event(self.logger, "server_start_fail", 
                           f"Server start error: {e}")
            return False
    
    async def stop_server(self, message: str = "Server is shutting down", 
                         api_client=None) -> bool:
        """Stop Palworld server gracefully"""
        if not self.is_server_running():
            log_server_event(self.logger, "server_stop", 
                           "Server is already stopped")
            return True
        
        try:
            # Attempt graceful shutdown via API if available
            if api_client:
                try:
                    await api_client.announce_message(f"{message}. Shutting down in 30 seconds.")
                    await asyncio.sleep(30)
                    await api_client.shutdown_server(1, message)
                    
                    # Wait for graceful shutdown
                    for _ in range(60):
                        if not self.is_server_running():
                            break
                        await asyncio.sleep(1)
                except Exception as e:
                    self.logger.warning(f"API graceful shutdown failed: {e}")
            
            # Force terminate if still running
            if self.is_server_running():
                log_server_event(self.logger, "server_force_stop", 
                               "Attempting force termination")
                
                self.server_process.terminate()
                
                try:
                    self.server_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.server_process.kill()
                    self.server_process.wait()
            
            log_server_event(self.logger, "server_stop_complete", 
                           "Server stopped successfully")
            return True
            
        except Exception as e:
            log_server_event(self.logger, "server_stop_fail", 
                           f"Server stop error: {e}")
            return False
    
    def get_server_status(self) -> dict:
        """Get detailed server process status"""
        if not self.is_server_running():
            return {
                "running": False,
                "pid": None,
                "uptime": 0
            }
        
        return {
            "running": True,
            "pid": self.server_process.pid,
            "uptime": time.time() - self.server_process.create_time() if hasattr(self.server_process, 'create_time') else 0
        }
    
    def get_startup_options_summary(self) -> dict:
        """
        Get summary of current startup options configuration
        
        Returns:
            Dictionary containing startup options information
        """
        startup_cfg = self.config.server_startup
        options = self._build_startup_options()
        
        return {
            "performance_optimization": (
                startup_cfg.use_performance_threads and 
                startup_cfg.disable_async_loading and 
                startup_cfg.use_multithread_for_ds
            ),
            "query_port": startup_cfg.query_port,
            "public_lobby": startup_cfg.enable_public_lobby,
            "log_format": startup_cfg.log_format,
            "worker_threads": startup_cfg.worker_threads_count,
            "additional_options": startup_cfg.additional_options,
            "generated_options": options,
            "options_count": len(options)
        }
