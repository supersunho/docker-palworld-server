#!/usr/bin/env python3
"""
SteamCMD client for Palworld server management
Handles server file downloads and updates via SteamCMD.
"""

import os
import threading
import shlex
import subprocess
import hashlib
from pathlib import Path
from typing import List

from ..logging_setup import log_server_event


class SteamCMDManager:
    """Manages SteamCMD operations for Palworld server"""

    def __init__(self, steamcmd_path: Path, logger):
        self.steamcmd_path = steamcmd_path
        self.logger = logger
        self.steamcmd_script = steamcmd_path / "steamcmd.sh"

    def _steamcmd_digest(self) -> str | None:
        """Return a hex digest of the steamcmd.sh entry point.

        Used by _ensure_updated to detect whether the SteamCMD
        self-updater actually touched the binary during warm-up.
        Returns None when the file cannot be read (the caller
        treats None as "unchanged").
        """
        try:
            return hashlib.sha256(
                self.steamcmd_script.read_bytes()
            ).hexdigest()
        except OSError:
            return None

    def validate_steamcmd(self) -> bool:
        """Check if SteamCMD executable exists and is executable"""
        if not self.steamcmd_script.exists():
            self.logger.error("SteamCMD executable not found", script_path=str(self.steamcmd_script))
            return False

        if not self.steamcmd_script.is_file():
            self.logger.error("SteamCMD path is not a file", script_path=str(self.steamcmd_script))
            return False

        import stat
        mode = self.steamcmd_script.stat().st_mode
        if not (mode & stat.S_IEXEC):
            self.logger.warning("SteamCMD executable lacks execute permission, attempting to set it")
            try:
                self.steamcmd_script.chmod(mode | stat.S_IEXEC)
            except PermissionError:
                self.logger.error("Failed to set execute permission for SteamCMD")
                return False

        return True

    def _run_and_stream(self, cmd: list, env: dict, cwd: str, timeout: int,
                        label: str = "SteamCMD") -> tuple[int, list[str]]:
        """Run a process and stream stdout/stderr line by line in real-time.

        Returns (returncode, all_output_lines). Raises on timeout.
        """
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
            cwd=cwd,
        )

        output_lines: list[str] = []
        lock = threading.Lock()

        def _reader(stream, label_prefix: str):
            for line in iter(stream.readline, ''):
                line = line.rstrip('\n\r')
                if line:
                    with lock:
                        output_lines.append(line)
                    self.logger.info(f"[{label}][{label_prefix}] {line}")
            stream.close()

        stdout_t = threading.Thread(target=_reader, args=(process.stdout, "out"))
        stderr_t = threading.Thread(target=_reader, args=(process.stderr, "err"))
        stdout_t.daemon = True
        stderr_t.daemon = True
        stdout_t.start()
        stderr_t.start()

        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            stdout_t.join(timeout=5)
            stderr_t.join(timeout=5)
            process.stdout.close()
            process.stderr.close()
            raise

        stdout_t.join()
        stderr_t.join()
        process.stdout.close()
        process.stderr.close()

        return returncode, output_lines

    def _ensure_updated(self) -> bool:
        """Lightweight warm-up to trigger any pending self-update.

        Returns True if it is safe to proceed with the main command.
        Returns False only when the binary was modified during a
        failed update -- a strong signal that SteamCMD would run a
        partially-overwritten (and likely broken) installation.

        All other outcomes (timeout, transient network error, update
        already applied, no update needed) return True because the
        binary remains in a known-good state.
        """
        if not self.validate_steamcmd():
            return False

        # Snapshot the binary before warming up so we can detect
        # whether the SteamCMD self-updater actually wrote to disk.
        before = self._steamcmd_digest()

        warmup_parts = [str(self.steamcmd_script), "+login", "anonymous", "+quit"]
        full_cmd = ["FEXBash", "-c", shlex.join(warmup_parts)]

        env = {
            **dict(os.environ),
            "STEAM_COMPAT_DATA_PATH": str(
                self.steamcmd_path / "steam_compat"
            ),
            "STEAM_COMPAT_CLIENT_INSTALL_PATH": str(
                self.steamcmd_path
            ),
        }
        (self.steamcmd_path / "steam_compat").mkdir(parents=True, exist_ok=True)

        self.logger.info(
            "Running SteamCMD warm-up to trigger any pending self-update",
            event_type="steamcmd_warmup",
        )
        try:
            rc, lines = self._run_and_stream(
                full_cmd,
                env,
                str(self.steamcmd_path),
                timeout=120,
                label="warmup",
            )
            if rc == 0:
                self.logger.info(
                    "SteamCMD warm-up completed successfully"
                )
                return True

            # Non-zero exit.  Check whether the binary changed -- a
            # changed binary means a partial self-update landed on
            # disk and likely corrupted the installation.
            after = self._steamcmd_digest()
            if after is not None and after != before:
                self.logger.error(
                    "SteamCMD warm-up failed and the binary was "
                    "modified. Refusing to proceed -- the installation "
                    "may be partially overwritten.",
                    event_type="steamcmd_warmup_corrupt",
                    return_code=rc,
                )
                return False

            self.logger.warning(
                "SteamCMD warm-up finished with a non-zero exit, "
                "but the binary is unchanged (may be normal -- "
                "continuing).",
                event_type="steamcmd_warmup",
                return_code=rc,
            )
            return True

        except subprocess.TimeoutExpired:
            self.logger.warning(
                "SteamCMD warm-up timed out (the main command has a "
                "longer timeout, so this may still work -- continuing)."
            )
            return True

    def run_command(self, commands: List[str], timeout: int = 600) -> bool:
        """Run SteamCMD commands with timeout"""
        if not self.validate_steamcmd():
            return False

        # Warm up steamcmd first to handle any pending self-update
        # before running the real command.  If the binary was corrupted
        # during the warm-up, abort immediately.
        if not self._ensure_updated():
            return False

        steamcmd_command = shlex.join([str(self.steamcmd_script)] + commands)
        full_cmd = ["FEXBash", "-c", steamcmd_command]

        log_server_event(self.logger, "steamcmd_start", f"Executing: FEXBash -c '{steamcmd_command}'")

        try:
            env = {
                **dict(os.environ),
                "STEAM_COMPAT_DATA_PATH": str(self.steamcmd_path / "steam_compat"),
                "STEAM_COMPAT_CLIENT_INSTALL_PATH": str(self.steamcmd_path),
            }

            rc, lines = self._run_and_stream(
                full_cmd, env, str(self.steamcmd_path), timeout=timeout, label="SteamCMD"
            )

            if rc == 0:
                log_server_event(self.logger, "steamcmd_complete",
                                 "SteamCMD commands completed successfully")
                return True
            else:
                fex_env_vars = {k: v for k, v in env.items()
                                if 'FEX' in k or 'STEAM_COMPAT' in k}
                self.logger.error(
                    "SteamCMD commands failed",
                    event_type="steamcmd_fail",
                    return_code=rc,
                    last_lines=lines[-100:],
                    env_vars=fex_env_vars,
                )
                return False

        except subprocess.TimeoutExpired:
            self.logger.error(f"SteamCMD timeout after {timeout} seconds", event_type="steamcmd_fail")
            return False
        except Exception as e:
            self.logger.error(f"SteamCMD execution error: {e}", event_type="steamcmd_fail")
            return False
