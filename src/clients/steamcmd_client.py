#!/usr/bin/env python3
"""
SteamCMD client for Palworld server management
Handles server file downloads and updates via SteamCMD
"""

import os
import subprocess
from pathlib import Path
from typing import List

from ..logging_setup import log_server_event


class SteamCMDManager:
    """SteamCMD dedicated management class"""
    
    def __init__(self, steamcmd_path: Path, logger):
        self.steamcmd_path = steamcmd_path
        self.logger = logger
        self.steamcmd_script = steamcmd_path / "steamcmd.sh"
    
    def validate_steamcmd(self) -> bool:
        """Check SteamCMD installation status"""
        if not self.steamcmd_script.exists():
            self.logger.error("SteamCMD executable not found", 
                            script_path=str(self.steamcmd_script))
            return False
        
        if not self.steamcmd_script.is_file():
            self.logger.error("SteamCMD path is not a file", 
                            script_path=str(self.steamcmd_script))
            return False
        
        # Check execute permission
        import stat
        mode = self.steamcmd_script.stat().st_mode
        if not (mode & stat.S_IEXEC):
            self.logger.warning("SteamCMD executable lacks execute permission, trying to set it")
            try:
                self.steamcmd_script.chmod(mode | stat.S_IEXEC)
            except PermissionError:
                self.logger.error("Failed to set execute permission for SteamCMD")
                return False
        
        return True
    
    def run_command(self, commands: List[str], timeout: int = 600) -> bool:
        """
        Run SteamCMD commands
        
        Args:
            commands: List of SteamCMD commands to run
            timeout: Timeout in seconds
            
        Returns:
            Success status
        """
        if not self.validate_steamcmd():
            return False
         
        steamcmd_command = " ".join([
            str(self.steamcmd_script),
            "+login", "anonymous"
        ] + commands + ["+quit"])
         
        full_cmd = ["FEXBash", "-c", steamcmd_command]
        
        log_server_event(self.logger, "steamcmd_start", 
                        f"Executing: FEXBash -c '{steamcmd_command}'")
        
        try:
            # Environment variables for FEX optimization
            env = {
                **dict(os.environ),
                "STEAM_COMPAT_DATA_PATH": str(self.steamcmd_path / "steam_compat"),
                "STEAM_COMPAT_CLIENT_INSTALL_PATH": str(self.steamcmd_path),
            }
            
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=str(self.steamcmd_path)
            )
            
            if result.returncode == 0:
                log_server_event(self.logger, "steamcmd_complete", 
                               "SteamCMD commands completed successfully", 
                               duration_seconds=timeout)
                return True
            else:
                log_server_event(self.logger, "steamcmd_fail", 
                               "SteamCMD commands failed", 
                               return_code=result.returncode,
                               stderr=result.stderr)
                return False
                
        except subprocess.TimeoutExpired:
            log_server_event(self.logger, "steamcmd_fail", 
                           f"SteamCMD timeout after {timeout} seconds")
            return False
        except Exception as e:
            log_server_event(self.logger, "steamcmd_fail", 
                           f"SteamCMD execution error: {e}")
            return False
