#!/usr/bin/env python3
"""
Configuration file management for Palworld server
Handles file writing for PalWorldSettings.ini and Engine.ini.
All content generation is delegated to SettingsGenerator.
Supports hot-reload via file polling and SIGHUP forwarding.
"""

import asyncio
import hashlib
from pathlib import Path
from typing import Optional, Callable, Dict

from ..config_loader import PalworldConfig
from ..logging_setup import log_server_event
from .settings_generator import SettingsGenerator


class ConfigManager:
    """Server configuration file management

    Delegates all INI content generation to SettingsGenerator.
    Only handles directory creation and file writing.
    Supports hot-reload via polling-based file change detection.
    """

    def __init__(
        self, config: PalworldConfig, logger, generator: Optional[SettingsGenerator] = None
    ):
        self.config = config
        self.logger = logger
        self.generator = generator or SettingsGenerator(config, logger)
        self.server_path = config.paths.server_dir
        self.config_dir = self.server_path / "Pal" / "Saved" / "Config" / "LinuxServer"

        # Hot-reload state
        self._checksums: Dict[str, str] = {}
        self._watch_task: Optional[asyncio.Task] = None
        self._on_config_change: Optional[Callable] = None

    def generate_server_settings(self) -> bool:
        """Generate and write Palworld server settings file"""
        try:
            settings_file = self.config_dir / "PalWorldSettings.ini"
            self.config_dir.mkdir(parents=True, exist_ok=True)
            settings_content = self.generator.generate_server_settings()
            settings_file.write_text(settings_content, encoding="utf-8")
            self._update_checksum("server_settings", settings_content)
            log_server_event(
                self.logger,
                "config_generate",
                "Server settings file generated successfully",
                settings_file=str(settings_file),
            )
            return True
        except Exception as e:
            log_server_event(
                self.logger, "config_generate_fail", f"Failed to generate settings file: {e}"
            )
            return False

    def generate_engine_settings(self) -> bool:
        """Generate and write Palworld engine settings file"""
        try:
            engine_file = self.config_dir / "Engine.ini"
            self.config_dir.mkdir(parents=True, exist_ok=True)
            engine_content = self.generator.generate_engine_settings()
            engine_file.write_text(engine_content, encoding="utf-8")
            self._update_checksum("engine_settings", engine_content)
            log_server_event(
                self.logger,
                "config_generate",
                "Engine settings file generated successfully",
                engine_file=str(engine_file),
            )
            return True
        except Exception as e:
            log_server_event(
                self.logger, "config_generate_fail", f"Failed to generate engine settings file: {e}"
            )
            return False

    # ------------------------------------------------------------------
    # Hot-reload support
    # ------------------------------------------------------------------

    def _update_checksum(self, key: str, content: str) -> None:
        """Update internal checksum for change detection"""
        self._checksums[key] = hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _compute_checksums(self) -> Dict[str, str]:
        """Compute current checksums of managed config files"""
        result = {}
        for key, path in [
            ("server_settings", self.config_dir / "PalWorldSettings.ini"),
            ("engine_settings", self.config_dir / "Engine.ini"),
        ]:
            try:
                if path.exists():
                    content = path.read_text(encoding="utf-8")
                    result[key] = hashlib.sha256(content.encode("utf-8")).hexdigest()
                else:
                    result[key] = ""
            except Exception:
                result[key] = ""
        return result

    def _check_yaml_changed(self) -> bool:
        """Check if the source YAML config has changed since last generation"""
        config_path = Path("config/default.yaml")
        if not config_path.exists():
            return False
        try:
            content = config_path.read_text(encoding="utf-8")
            current_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            key = "yaml_config"
            if key not in self._checksums:
                self._checksums[key] = current_hash
                return False
            if self._checksums[key] != current_hash:
                self._checksums[key] = current_hash
                return True
        except Exception as e:
            self.logger.warning(
                "Failed to check YAML config for changes: %s",
                e,
            )
        return False

    def reload_and_apply(self) -> bool:
        """Regenerate both config files from current YAML config

        Returns True if files were regenerated, False on failure.
        """
        try:
            settings_ok = self.generate_server_settings()
            engine_ok = self.generate_engine_settings()

            if settings_ok or engine_ok:
                log_server_event(
                    self.logger,
                    "config_reload",
                    "Configuration reloaded from YAML source",
                    server_settings=settings_ok,
                    engine_settings=engine_ok,
                )
                return True

            log_server_event(
                self.logger,
                "config_reload_fail",
                "Configuration reload failed — neither file was regenerated",
            )
            return False
        except Exception as e:
            log_server_event(self.logger, "config_reload_fail", f"Configuration reload error: {e}")
            return False

    async def watch_config(
        self, check_interval: int = 30, on_change: Optional[Callable] = None
    ) -> None:
        """Poll YAML config for changes and regenerate INI files on change.

        When a change is detected, the INI files are regenerated and an
        optional callback (typically sending SIGHUP to the server) is invoked.

        Args:
            check_interval: Polling interval in seconds.
            on_change: Async callback invoked when config has changed.
                       Receives no arguments.
        """
        self._on_config_change = on_change

        log_server_event(
            self.logger,
            "config_watch_start",
            f"Config file watching started (interval={check_interval}s)",
        )

        while True:
            try:
                changed = self._check_yaml_changed()

                if changed:
                    self.logger.info("Configuration source changed, regenerating INI files")
                    success = self.reload_and_apply()

                    if success and self._on_config_change:
                        await self._on_config_change()

                await asyncio.sleep(check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Config watch error", error=str(e))
                await asyncio.sleep(5)

    async def start_watching(
        self, check_interval: int = 30, on_change: Optional[Callable] = None
    ) -> None:
        """Start the config watcher as a background task"""
        if self._watch_task is not None:
            self.logger.warning("Config watcher already running")
            return

        self._watch_task = asyncio.create_task(self.watch_config(check_interval, on_change))
        log_server_event(
            self.logger, "config_watch", f"Config file watcher started (interval={check_interval}s)"
        )

    async def stop_watching(self) -> None:
        """Stop the config watcher background task"""
        if self._watch_task is None:
            return

        self._watch_task.cancel()
        try:
            await self._watch_task
        except asyncio.CancelledError:
            pass
        self._watch_task = None
        log_server_event(self.logger, "config_watch_stop", "Config file watcher stopped")

    def is_watching(self) -> bool:
        """Check if config watcher is active"""
        return self._watch_task is not None and not self._watch_task.done()
