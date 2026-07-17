#!/usr/bin/env python3
"""
SteamCMD client for Palworld server management
Handles server file downloads and updates via SteamCMD.
"""

import os
import shlex
import hashlib
import asyncio
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
            return hashlib.sha256(self.steamcmd_script.read_bytes()).hexdigest()
        except OSError:
            return None

    def validate_steamcmd(self) -> bool:
        """Check if SteamCMD executable exists and is executable"""
        if not self.steamcmd_script.exists():
            self.logger.error(
                "SteamCMD executable not found", script_path=str(self.steamcmd_script)
            )
            return False

        if not self.steamcmd_script.is_file():
            self.logger.error("SteamCMD path is not a file", script_path=str(self.steamcmd_script))
            return False

        import stat

        mode = self.steamcmd_script.stat().st_mode
        if not (mode & stat.S_IEXEC):
            self.logger.warning(
                "SteamCMD executable lacks execute permission, attempting to set it"
            )
            try:
                self.steamcmd_script.chmod(mode | stat.S_IEXEC)
            except PermissionError:
                self.logger.error("Failed to set execute permission for SteamCMD")
                return False

        return True

    def _make_env(self) -> dict:
        """Build environment dict for SteamCMD subprocess."""
        env = {
            **dict(os.environ),
            "STEAM_COMPAT_DATA_PATH": str(self.steamcmd_path / "steam_compat"),
            "STEAM_COMPAT_CLIENT_INSTALL_PATH": str(self.steamcmd_path),
        }
        (self.steamcmd_path / "steam_compat").mkdir(parents=True, exist_ok=True)
        return env

    async def _run_and_stream(
        self, cmd: list, env: dict, cwd: str, timeout: int, label: str = "SteamCMD"
    ) -> tuple[int, list[str]]:
        """Run a process and stream stdout/stderr line by line in real-time.

        Returns (returncode, all_output_lines). Raises on timeout.
        Uses asyncio.create_subprocess_exec for non-blocking execution.
        """
        output_lines: list[str] = []

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=cwd,
        )

        async def _reader(stream, label_prefix: str):
            assert stream is not None
            while True:
                line = await stream.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip("\n\r")
                if decoded:
                    output_lines.append(decoded)
                    self.logger.info(f"[{label}][{label_prefix}] {decoded}")

        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(_reader(process.stdout, "out"))
                tg.create_task(_reader(process.stderr, "err"))

                try:
                    returncode = await asyncio.wait_for(process.wait(), timeout=timeout)
                except asyncio.TimeoutError:
                    process.kill()
                    raise

            return returncode, output_lines

        except* asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise
        except* subprocess.TimeoutExpired:
            process.kill()
            await process.wait()
            raise

    async def _ensure_updated(self) -> bool:
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

        before = self._steamcmd_digest()

        warmup_parts = [str(self.steamcmd_script), "+login", "anonymous", "+quit"]
        full_cmd = ["FEXBash", "-c", shlex.join(warmup_parts)]

        env = self._make_env()

        self.logger.info(
            "Running SteamCMD warm-up to trigger any pending self-update",
            event_type="steamcmd_warmup",
        )
        try:
            rc, lines = await self._run_and_stream(
                full_cmd,
                env,
                str(self.steamcmd_path),
                timeout=120,
                label="warmup",
            )
            if rc == 0:
                self.logger.info("SteamCMD warm-up completed successfully")
                return True

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

        except (asyncio.TimeoutError, subprocess.TimeoutExpired):
            self.logger.warning(
                "SteamCMD warm-up timed out (the main command has a "
                "longer timeout, so this may still work -- continuing)."
            )
            return True

    async def run_command(self, commands: List[str], timeout: int = 600) -> tuple[bool, list[str]]:
        """Run SteamCMD commands with timeout.

        Returns (success, output_lines).
        """
        if not self.validate_steamcmd():
            return False, []

        if not await self._ensure_updated():
            return False, []

        steamcmd_command = shlex.join([str(self.steamcmd_script)] + commands)
        full_cmd = ["FEXBash", "-c", steamcmd_command]

        log_server_event(
            self.logger, "steamcmd_start", f"Executing: FEXBash -c '{steamcmd_command}'"
        )

        try:
            env = self._make_env()

            rc, lines = await self._run_and_stream(
                full_cmd, env, str(self.steamcmd_path), timeout=timeout, label="SteamCMD"
            )

            if rc == 0:
                log_server_event(
                    self.logger, "steamcmd_complete", "SteamCMD commands completed successfully"
                )
                return True, lines
            else:
                fex_env_vars = {k: v for k, v in env.items() if "FEX" in k or "STEAM_COMPAT" in k}
                self.logger.error(
                    "SteamCMD commands failed",
                    event_type="steamcmd_fail",
                    return_code=rc,
                    last_lines=lines[-100:],
                    env_vars=fex_env_vars,
                )
                return False, lines

        except (asyncio.TimeoutError, subprocess.TimeoutExpired):
            self.logger.error(
                f"SteamCMD timeout after {timeout} seconds", event_type="steamcmd_fail"
            )
            return False, []
        except Exception as e:
            self.logger.error(f"SteamCMD execution error: {e}", event_type="steamcmd_fail")
            return False, []
