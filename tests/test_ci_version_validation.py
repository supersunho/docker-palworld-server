"""Tests for scripts/validate_ci_versions.sh.

These tests invoke the validator script as a subprocess to verify
that version parsing, security gating, and output format work correctly.
"""

import subprocess
import sys
from pathlib import Path
import pytest

pytestmark = pytest.mark.integration




SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
VALIDATOR = SCRIPTS_DIR / "validate_ci_versions.sh"


def _run_validator(source_version="latest", build_version=""):
    """Run the validator and return (returncode, stdout, stderr)."""
    proc = subprocess.run(
        [str(VALIDATOR), source_version, build_version],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _parse_output(stdout):
    """Parse key=value lines from validator stdout into a dict."""
    result = {}
    for line in stdout.strip().splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


# ------------------------------------------------------------------
# Happy path — valid version strings
# ------------------------------------------------------------------

class TestValidVersions:
    def test_latest_default(self):
        """source=latest, build='' → both resolved to latest."""
        rc, out, err = _run_validator("latest", "")
        assert rc == 0, f"expected 0, got {rc}: {err}"
        parsed = _parse_output(out)
        assert parsed.get("source_version") == "latest"
        assert parsed.get("build_version") == "latest"

    def test_explicit_latest(self):
        """source=latest, build=latest → latest/latest."""
        rc, out, err = _run_validator("latest", "latest")
        assert rc == 0, f"expected 0, got {rc}: {err}"
        parsed = _parse_output(out)
        assert parsed.get("source_version") == "latest"
        assert parsed.get("build_version") == "latest"

    def test_semver_v1(self):
        """v1 → clean=v1, base=v1."""
        rc, out, err = _run_validator("v1", "")
        assert rc == 0, f"expected 0, got {rc}: {err}"
        parsed = _parse_output(out)
        assert parsed.get("source_version") == "v1"
        assert parsed.get("source_version_clean") == "1"

    def test_semver_v1_2_3(self):
        """v1.2.3 → clean=1.2.3, base=1.2.3."""
        rc, out, err = _run_validator("v1.2.3", "")
        assert rc == 0, f"expected 0, got {rc}: {err}"
        parsed = _parse_output(out)
        assert parsed.get("source_version") == "v1.2.3"
        assert parsed.get("source_version_clean") == "1.2.3"
        assert parsed.get("source_version_base") == "1.2.3"

    def test_suffix_rc(self):
        """1.0.0-rc1 → clean=1.0.0-rc1, base=1.0.0 (suffix stripped)."""
        rc, out, err = _run_validator("1.0.0-rc1", "")
        assert rc == 0, f"expected 0, got {rc}: {err}"
        parsed = _parse_output(out)
        assert parsed.get("source_version_clean") == "1.0.0-rc1"
        assert parsed.get("source_version_base") == "1.0.0"

    def test_custom_build_version(self):
        """source=v1, build=v2.0 → build overrides source."""
        rc, out, err = _run_validator("v1", "v2.0")
        assert rc == 0, f"expected 0, got {rc}: {err}"
        parsed = _parse_output(out)
        assert parsed.get("source_version") == "v1"
        assert parsed.get("build_version") == "v2.0"
        assert parsed.get("build_version_clean") == "2.0"


# ------------------------------------------------------------------
# Rejection — malicious or malformed inputs
# ------------------------------------------------------------------

class TestInvalidVersions:
    def test_sql_injection_attempt(self):
        """Values with semicolons and quotes are rejected."""
        rc, out, err = _run_validator('1.0.0"; id; #', "")
        assert rc != 0, "expected non-zero exit for injection attempt"

    def test_actual_newline_injection(self):
        """Actual newline character is rejected."""
        rc, out, err = _run_validator("1.0.0\nbeta", "")
        assert rc != 0, "expected non-zero exit for actual newline"

    def test_carriage_return_injection(self):
        """Carriage return is rejected."""
        rc, out, err = _run_validator("1.0.0\rbeta", "")
        assert rc != 0, "expected non-zero exit for CR"

    def test_spaces_in_version(self):
        """Values with spaces are rejected."""
        rc, out, err = _run_validator("1.0 0", "")
        assert rc != 0, "expected non-zero exit for space"

    def test_command_substitution(self):
        """$(...) syntax is rejected."""
        rc, out, err = _run_validator("$(id)", "")
        assert rc != 0, "expected non-zero exit for command substitution"

    def test_backtick(self):
        """Backtick commands are rejected."""
        rc, out, err = _run_validator("`id`", "")
        assert rc != 0, "expected non-zero exit for backtick"

    def test_ampersand_concat(self):
        """&& concatenation is rejected."""
        rc, out, err = _run_validator("a&&b", "")
        assert rc != 0, "expected non-zero exit for &&"

    def test_pipe(self):
        """Pipe chaining is rejected."""
        rc, out, err = _run_validator("a|b", "")
        assert rc != 0, "expected non-zero exit for pipe"

    def test_tab_injection(self):
        """Tab characters are rejected."""
        rc, out, err = _run_validator("1.0.0\tbeta", "")
        assert rc != 0, "expected non-zero exit for tab"


# ------------------------------------------------------------------
# Output format guarantees
# ------------------------------------------------------------------

class TestOutputFormat:
    def test_all_six_keys_present(self):
        """Stdout contains exactly the 6 expected keys."""
        rc, out, err = _run_validator("v1.2.3", "v2.0")
        assert rc == 0, f"expected 0, got {rc}: {err}"
        expected_keys = {
            "source_version", "source_version_clean", "source_version_base",
            "build_version", "build_version_clean", "build_version_base",
        }
        parsed = _parse_output(out)
        assert set(parsed.keys()) == expected_keys, (
            f"missing keys: {expected_keys - set(parsed.keys())}"
        )

    def test_single_line_values(self):
        """Each output value is a single line (no embedded newlines)."""
        rc, out, err = _run_validator("v1.2.3-rc1", "v2.0")
        assert rc == 0, f"expected 0, got {rc}: {err}"
        for line in out.strip().splitlines():
            _, _, value = line.partition("=")
            assert "\n" not in value, f"multi-line value in: {line}"
