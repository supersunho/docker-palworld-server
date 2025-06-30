#!/usr/bin/env python3
"""
Process management for Palworld server
Handles server process lifecycle and monitoring
"""

import asyncio
import subprocess
import time
from pathlib import Path
from typing import Optional

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
    
    def start_server(self) -> bool:
        """Start Palworld server"""
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
                           "Starting Palworld server")
            
            # Start server process with FEX emulation
            full_cmd = ["FEXBash", "-c", str(server_executable)]
            
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
                           "Server started successfully", 
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
