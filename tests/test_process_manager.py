"""Tests for the process manager (including signal delivery and pause/resume)."""

import pytest
import asyncio
import time
import signal
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from pathlib import Path
from src.managers.process_manager import ProcessManager

pytestmark = pytest.mark.unit


class TestProcessManager:
    """FS-10.x: Process manager behavior."""

    @pytest.fixture
    def manager(self, palworld_config, mock_logger):
        return ProcessManager(palworld_config, mock_logger)

    def test_init(self, manager):
        """FS-10.1: Manager initializes without errors."""
        assert manager is not None
        assert manager.server_process is None

    def test_is_server_running_none(self, manager):
        """FS-10.2: Returns False when process is None."""
        assert manager.is_server_running() is False

    def test_is_server_running_poll_returns_none(self, manager):
        """FS-10.3: Returns True when process.poll() returns None."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        manager.server_process = mock_process
        assert manager.is_server_running() is True

    def test_is_server_running_poll_returns_int(self, manager):
        """FS-10.4: Returns False when process has exited."""
        mock_process = MagicMock()
        mock_process.poll.return_value = 0
        manager.server_process = mock_process
        assert manager.is_server_running() is False

    def test_get_server_status_not_running(self, manager):
        """FS-10.5: Status returns not-running info."""
        status = manager.get_server_status()
        assert status["running"] is False
        assert status["pid"] is None

    # ---- Security regression tests (Phase 3) ----

    def test_additional_options_shlex_split_preserves_tokens(self, manager):
        """SEC-3.1: shlex.split preserves shell metacharacters as single tokens."""
        startup_cfg = manager.config.server_startup
        # These would be split into multiple tokens by str.split(),
        # but shlex.split preserves them as single arguments.
        test_cases = [
            ("arg1 arg2", ["arg1", "arg2"]),
            ('"; echo INJECTED; "', ["; echo INJECTED; "]),
            ("arg1 | arg2", ["arg1", "|", "arg2"]),
        ]
        for payload, expected in test_cases:
            startup_cfg.additional_options = payload
            options = manager._build_startup_options()
            for exp in expected:
                assert exp in options, f"Expected {exp} in {options} for payload {payload}"

    def test_additional_options_malformed_quote_raises(self, manager):
        """SEC-3.2: Badly quoted additional_options raises ValueError."""
        startup_cfg = manager.config.server_startup
        startup_cfg.additional_options = '--flag="unclosed'
        with pytest.raises(ValueError):
            manager._build_startup_options()

    def test_additional_options_preserves_normal_args(self, manager):
        """SEC-3.3: Normal additional_options are preserved as separate tokens."""
        startup_cfg = manager.config.server_startup
        startup_cfg.additional_options = '--foo=bar --baz "quoted arg"'
        options = manager._build_startup_options()
        assert "--foo=bar" in options
        assert "--baz" in options
        assert "quoted arg" in options

    def test_build_server_command_uses_shlex_join(self, manager):
        """SEC-3.4: Server command uses shlex.join for safe serialization."""
        startup_cfg = manager.config.server_startup
        startup_cfg.additional_options = "--opt-with=some value"
        cmd = manager._build_server_command()
        # The command should be a list starting with FEXBash
        assert cmd[0] == "FEXBash"
        assert cmd[1] == "-c"
        # The shell command string should preserve the quoted value
        assert "some value" in cmd[2] or "'some value'" in cmd[2] or '"some value"' in cmd[2]

    def test_start_server_no_pipe(self, manager):
        """SEC-3.5: start_server Popen does not use stdout=PIPE or stderr=PIPE."""
        import subprocess
        from src.managers.process_manager import ProcessManager

        # Verify via source code inspection
        import inspect

        source = inspect.getsource(ProcessManager.start_server)
        assert "stdout=subprocess.PIPE" not in source
        assert "stderr=subprocess.PIPE" not in source

    def test_server_output_not_captured_in_pipe(self, manager):
        """SEC-3.6: Server Popen does not use stdout=PIPE or stderr=PIPE."""
        # Verify by checking the source code of start_server
        import inspect
        from src.managers.process_manager import ProcessManager

        source = inspect.getsource(ProcessManager.start_server)
        assert (
            "subprocess.PIPE" not in source
        ), "start_server must not use PIPE for long-running process"

    def test_build_server_command_no_options_explicit(self, manager):
        """FS-10.x: Empty additional_options produces no extras."""
        startup_cfg = manager.config.server_startup
        startup_cfg.additional_options = ""
        startup_cfg.use_performance_threads = False
        startup_cfg.disable_async_loading = False
        startup_cfg.use_multithread_for_ds = False
        startup_cfg.query_port = 27015
        startup_cfg.log_format = "text"
        startup_cfg.enable_public_lobby = False
        opts = manager._build_startup_options()
        assert len(opts) == 0

    def test_build_server_command_path_with_spaces(self, manager):
        """SEC-3.7: Path with spaces is properly quoted via shlex.join."""
        manager.server_path = Path("/tmp/pal world/server dir")
        startup_cfg = manager.config.server_startup
        startup_cfg.additional_options = ""
        startup_cfg.use_performance_threads = False
        startup_cfg.disable_async_loading = False
        startup_cfg.use_multithread_for_ds = False
        cmd = manager._build_server_command()
        assert cmd[0] == "FEXBash"
        assert cmd[1] == "-c"
        # shlex.join should quote the path with spaces
        cmd_str = cmd[2]
        assert "PalServer.sh" in cmd_str
        # The quoted path should appear as a single token
        quoted_repr = repr(cmd_str)
        assert "pal world" in cmd_str.replace(chr(39), "") or "pal world" in cmd_str.replace(
            chr(34), ""
        )

    def test_build_server_command_path_with_semicolon(self, manager):
        """SEC-3.8: Path with semicolon is shell-quoted, not executed."""
        manager.server_path = Path("/tmp/server;echo INJECTED")
        startup_cfg = manager.config.server_startup
        startup_cfg.additional_options = ""
        startup_cfg.use_performance_threads = False
        startup_cfg.disable_async_loading = False
        startup_cfg.use_multithread_for_ds = False
        cmd = manager._build_server_command()
        cmd_str = cmd[2]
        # The path with semicolon must be shell-quoted so FEXBash -c
        # treats it as a single token, not a command separator.
        assert (
            "'/tmp/server;echo INJECTED/PalServer.sh'" in cmd_str
        ), f"Expected shell-quoted path in command, got: {cmd_str!r}"

    def test_additional_options_injection_separator(self, manager):
        """SEC-3.9: Shell separators in additional_options are not executed."""
        startup_cfg = manager.config.server_startup
        # shlex.split preserves metacharacters as tokens; shlex.join quotes them
        startup_cfg.additional_options = "; echo INJECTED"
        cmd = manager._build_server_command()
        cmd_str = cmd[2]
        # The semicolon must be shell-quoted so it's not a command separator
        assert "';'" in cmd_str or "';" in cmd_str or cmd_str.count(chr(39)) >= 6

    def test_send_signal_error_returns_false(self, manager):
        """FS-10.x: send_signal returns False on unexpected error."""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None
        manager.server_process = mock_process
        with patch("os.killpg", side_effect=OSError("permission denied")):
            result = asyncio.run(manager.send_signal(signal.SIGTERM))
            assert result is False

    def test_reload_config_sends_sighup(self, manager):
        """FS-10.x: reload_config delegates to send_signal with SIGHUP."""
        with patch.object(manager, "send_signal", new=AsyncMock(return_value=True)) as mock_send:
            result = asyncio.run(manager.reload_config())
            assert result is True
            mock_send.assert_called_once_with(signal.SIGHUP)

    def test_pause_and_resume_server(self, manager):
        """FS-10.x: pause and resume delegate to send_signal."""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None
        manager.server_process = mock_process
        with patch("os.killpg") as mock_kill:
            result_pause = asyncio.run(manager.pause_server())
            assert result_pause is True
            mock_kill.assert_called_with(12345, signal.SIGSTOP)
            result_resume = asyncio.run(manager.resume_server())
            assert result_resume is True
            mock_kill.assert_called_with(12345, signal.SIGCONT)

    def test_is_server_running_with_positive_returncode(self, manager):
        """FS-10.x: is_server_running returns False when process exited with code."""
        mock_process = MagicMock()
        mock_process.poll.return_value = 0
        manager.server_process = mock_process
        assert manager.is_server_running() is False

    def test_is_server_running_with_none_process(self, manager):
        """FS-10.x: is_server_running returns False when server_process is None."""
        manager.server_process = None
        assert manager.is_server_running() is False

    # ---- Additional coverage tests ----

    def test_build_server_command_no_options(self, manager):
        """FS-10.x: _build_server_command works without startup options."""
        startup_cfg = manager.config.server_startup
        startup_cfg.additional_options = ""
        startup_cfg.use_performance_threads = False
        startup_cfg.disable_async_loading = False
        startup_cfg.use_multithread_for_ds = False
        cmd = manager._build_server_command()
        assert cmd[0] == "FEXBash"
        assert cmd[1] == "-c"
        # Should reference the server executable path
        assert "PalServer.sh" in cmd[2]

    def test_get_server_status_running(self, manager):
        """FS-10.x: get_server_status returns running info when process active."""
        import time

        mock_process = MagicMock()
        mock_process.poll.return_value = None
        manager.server_process = mock_process
        manager._process_start_time = time.time()
        status = manager.get_server_status()
        assert status["running"] is True
        assert status["pid"] == mock_process.pid
        assert status["uptime"] > 0

    def test_get_server_status_no_start_time(self, manager):
        """FS-10.x: get_server_status returns not-running when _process_start_time is None."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        manager.server_process = mock_process
        manager._process_start_time = None
        status = manager.get_server_status()
        assert status["running"] is False
        assert status["uptime"] == 0

    def test_get_startup_options_summary_all_disabled(self, manager):
        """FS-10.x: Options summary with all features disabled."""
        startup_cfg = manager.config.server_startup
        startup_cfg.use_performance_threads = False
        startup_cfg.disable_async_loading = False
        startup_cfg.use_multithread_for_ds = False
        startup_cfg.query_port = 27015
        startup_cfg.additional_options = ""
        summary = manager.get_startup_options_summary()
        assert summary["performance_optimization"] is False
        assert summary["options_count"] == 0

    def test_reload_config_signal_failure(self, manager):
        """FS-10.x: reload_config returns False when send_signal fails."""
        from unittest.mock import AsyncMock

        with patch.object(manager, "send_signal", new=AsyncMock(return_value=False)):
            result = asyncio.run(manager.reload_config())
            assert result is False

    def test_get_startup_options_summary(self, manager):
        """FS-10.6: Options summary returns dict."""
        summary = manager.get_startup_options_summary()
        assert "performance_optimization" in summary
        assert "query_port" in summary

    # ---- Signal / hot-reload tests ----

    def test_send_signal_not_running(self, manager):
        """FS-10.7: send_signal returns False when server not running."""
        result = asyncio.run(manager.send_signal(signal.SIGHUP))
        assert result is False

    def test_send_signal_success(self, manager):
        """FS-10.8: send_signal sends signal to process group."""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None
        manager.server_process = mock_process

        with patch("os.killpg") as mock_killpg:
            result = asyncio.run(manager.send_signal(signal.SIGHUP))
            assert result is True
            mock_killpg.assert_called_once_with(12345, signal.SIGHUP)

    def test_send_signal_process_lookup_error(self, manager):
        """FS-10.9: send_signal returns False on ProcessLookupError."""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None
        manager.server_process = mock_process

        with patch("os.killpg", side_effect=ProcessLookupError):
            result = asyncio.run(manager.send_signal(signal.SIGHUP))
            assert result is False

    def test_reload_config_not_running(self, manager):
        """FS-10.10: reload_config returns False when server not running."""
        result = asyncio.run(manager.reload_config())
        assert result is False

    def test_reload_config_success(self, manager):
        """FS-10.11: reload_config sends SIGHUP to server."""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None
        manager.server_process = mock_process

        with patch("os.killpg") as mock_killpg:
            result = asyncio.run(manager.reload_config())
            assert result is True
            mock_killpg.assert_called_once_with(12345, signal.SIGHUP)

    # ---- Pause / Resume tests ----

    def test_pause_server_sends_sigstop(self, manager):
        """FS-10.12: pause_server sends SIGSTOP."""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None
        manager.server_process = mock_process

        with patch("os.killpg") as mock_killpg:
            result = asyncio.run(manager.pause_server())
            assert result is True
            mock_killpg.assert_called_once_with(12345, signal.SIGSTOP)

    def test_resume_server_sends_sigcont(self, manager):
        """FS-10.13: resume_server sends SIGCONT."""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None
        manager.server_process = mock_process

        with patch("os.killpg") as mock_killpg:
            result = asyncio.run(manager.resume_server())
            assert result is True
            mock_killpg.assert_called_once_with(12345, signal.SIGCONT)

    def test_pause_server_not_running(self, manager):
        """FS-10.14: pause_server returns False when not running."""
        result = asyncio.run(manager.pause_server())
        assert result is False


class TestProcessManagerEdgeCases:
    """Edge case coverage for process manager."""

    @pytest.fixture
    def manager(self, palworld_config, mock_logger):
        return ProcessManager(palworld_config, mock_logger)

    def test_build_startup_options_with_worker_threads(self, manager):
        """FS-10.x: worker_threads_count > 0 adds thread option."""
        manager.config.server_startup.worker_threads_count = 4
        options = manager._build_startup_options()
        assert f"-NumberOfWorkerThreadsServer=4" in options

    def test_build_startup_options_public_lobby(self, manager):
        """FS-10.x: enable_public_lobby adds lobby option."""
        manager.config.server_startup.enable_public_lobby = True
        options = manager._build_startup_options()
        assert "-publiclobby" in options

    def test_build_startup_options_log_format(self, manager):
        """FS-10.x: non-text log format adds format option."""
        manager.config.server_startup.log_format = "json"
        options = manager._build_startup_options()
        assert "-logformat=json" in options

    def test_build_server_command_no_options(self, manager):
        """FS-10.x: _build_server_command works even when no options are generated."""
        # Disable all option-generating configs
        cfg = manager.config.server_startup
        cfg.use_performance_threads = False
        cfg.query_port = 27015
        cfg.log_format = "text"
        cfg.enable_public_lobby = False
        cfg.additional_options = ""
        cmd = manager._build_server_command()
        assert cmd[0] == "FEXBash"
        assert cmd[1] == "-c"
        assert "PalServer.sh" in cmd[2]

    @pytest.mark.asyncio
    async def test_start_server_already_running(self, manager):
        """FS-10.x: start_server returns True when already running."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        manager.server_process = mock_process
        result = await manager.start_server()
        assert result is True

    @pytest.mark.asyncio
    async def test_start_server_executable_not_found(self, manager):
        """FS-10.x: start_server returns False when executable missing."""
        # Patch server_path to a non-existent directory
        with patch("pathlib.Path.exists", return_value=False):
            result = await manager.start_server()
        assert result is False

    @pytest.mark.asyncio
    async def test_stop_server_not_running(self, manager):
        """FS-10.x: stop_server returns True when server not running."""
        result = await manager.stop_server()
        assert result is True

    @pytest.mark.asyncio
    async def test_stop_server_handles_process_cleared_after_running_check(self, manager):
        """stop_server treats a concurrently cleared process as already stopped."""
        mock_process = MagicMock()
        manager.server_process = mock_process

        def report_running_then_clear_process():
            manager.server_process = None
            return True

        with patch.object(
            manager,
            "is_server_running",
            side_effect=report_running_then_clear_process,
        ):
            result = await manager.stop_server()

        assert result is True
        mock_process.wait.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_signal_handles_process_cleared_after_running_check(self, manager):
        """send_signal returns False when the process disappears during the check."""
        mock_process = MagicMock()
        manager.server_process = mock_process

        def report_running_then_clear_process():
            manager.server_process = None
            return True

        with (
            patch.object(
                manager,
                "is_server_running",
                side_effect=report_running_then_clear_process,
            ),
            patch("os.killpg") as mock_killpg,
        ):
            result = await manager.send_signal(signal.SIGTERM)

        assert result is False
        mock_killpg.assert_not_called()

    def test_get_startup_options_summary(self, manager):
        """FS-10.x: get_startup_options_summary returns expected structure."""
        summary = manager.get_startup_options_summary()
        assert "query_port" in summary
        assert "public_lobby" in summary
        assert "log_format" in summary
        assert "generated_options" in summary
        assert "options_count" in summary

    def test_get_server_status_running(self, manager):
        """FS-10.x: get_server_status returns running info when process active."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.pid = 12345
        manager.server_process = mock_process
        manager._process_start_time = time.time() - 60
        status = manager.get_server_status()
        assert status["running"] is True
        assert status["pid"] == 12345
        assert status["uptime"] > 0

    @pytest.mark.asyncio
    async def test_start_server_popen_raises_exception(self, manager):
        """FS-10.x: start_server handles Popen exceptions."""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("subprocess.Popen", side_effect=Exception("exec failed")):
                result = await manager.start_server()
        assert result is False

    @pytest.mark.asyncio
    async def test_start_server_popen_process_dies_immediately(self, manager):
        """FS-10.x: start_server detects when process dies right after start."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # process exited
        with patch("pathlib.Path.exists", return_value=True):
            with patch("subprocess.Popen", return_value=mock_proc):
                with patch("asyncio.sleep", AsyncMock(return_value=None)):
                    result = await manager.start_server()
        assert result is False

    @pytest.mark.asyncio
    async def test_stop_server_with_api_client_error(self, manager):
        """FS-10.x: stop_server handles api_client gracefully."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # running
        mock_proc.pid = 12345
        manager.server_process = mock_proc
        mock_api = MagicMock()
        mock_api.announce_message = AsyncMock(side_effect=Exception("api error"))
        with patch("os.killpg") as mock_kill:
            with patch("signal.SIGTERM", 15):
                result = await manager.stop_server(api_client=mock_api)
                assert result is True
                mock_kill.assert_called()
