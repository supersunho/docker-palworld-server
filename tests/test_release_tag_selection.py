"""Regression tests for selecting the previous release tag."""

import os
import subprocess
from pathlib import Path
import pytest

pytestmark = pytest.mark.unit


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "find_previous_release_tag.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _create_tagged_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Release Test")
    _git(repo, "config", "user.email", "release-test@example.invalid")

    for index, tag in enumerate(("v1.1.0", "1.1.1-build-41", "1.1.2", "1.1.3")):
        (repo / f"commit-{index}").write_text(f"commit {index}\n", encoding="utf-8")
        _git(repo, "add", ".")
        _git(repo, "commit", "-q", "-m", f"commit {index}")
        _git(repo, "tag", tag)

    # This must not be treated as a release tag.
    _git(repo, "tag", "latest")
    return repo


def _previous_tag(repo: Path, current_tag: str, *extra: str) -> str:
    env = {**os.environ, "LC_ALL": "C"}
    result = subprocess.run(
        [str(SCRIPT), current_tag, *extra],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.stdout.strip()


def test_previous_release_excludes_current_tag_and_non_release_tags(tmp_path):
    repo = _create_tagged_repo(tmp_path)

    assert _previous_tag(repo, "1.1.3") == "1.1.2"
    assert _previous_tag(repo, "v1.1.3") == "1.1.2"
    assert _previous_tag(repo, "latest") == "1.1.3"


def _create_tiered_repo(tmp_path: Path) -> Path:
    """Tags: stable 2.0.0, beta chain, rc, and a stable 2.1.0 tip."""
    repo = tmp_path / "tiered"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Release Test")
    _git(repo, "config", "user.email", "release-test@example.invalid")

    for index, tag in enumerate(
        ("2.0.0", "2.1.0-beta.1", "2.1.0-beta.2", "2.1.0-beta.3", "2.1.0-rc.1", "2.1.0")
    ):
        (repo / f"commit-{index}").write_text(f"commit {index}\n", encoding="utf-8")
        _git(repo, "add", ".")
        _git(repo, "commit", "-q", "-m", f"commit {index}")
        _git(repo, "tag", tag)
    return repo


def test_prerelease_resolves_same_base_chain(tmp_path):
    repo = _create_tiered_repo(tmp_path)

    assert _previous_tag(repo, "2.1.0-rc.1") == "2.1.0-beta.3"
    assert _previous_tag(repo, "2.1.0-beta.2") == "2.1.0-beta.1"


def test_stable_skips_same_base_prereleases(tmp_path):
    repo = _create_tiered_repo(tmp_path)

    # Stable 2.1.0 must span the whole cycle back to 2.0.0, not beta.3/rc.1.
    assert _previous_tag(repo, "2.1.0") == "2.0.0"


def test_first_prerelease_falls_back_to_previous_stable(tmp_path):
    repo = _create_tiered_repo(tmp_path)

    assert _previous_tag(repo, "2.1.0-beta.1") == "2.0.0"


def test_explicit_prerelease_flag_overrides_suffix_detection(tmp_path):
    repo = _create_tiered_repo(tmp_path)

    # Forced prerelease on a stable spelling still walks the same-base chain.
    assert _previous_tag(repo, "2.1.0", "true") == "2.1.0-rc.1"
    # Forced stable on a prerelease spelling skips Tier 1 entirely.
    assert _previous_tag(repo, "2.1.0-beta.2", "false") == "2.0.0"


def test_non_release_current_prefers_stable_over_same_base_prerelease(tmp_path):
    repo = tmp_path / "legacypre"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Release Test")
    _git(repo, "config", "user.email", "release-test@example.invalid")

    for index, tag in enumerate(("2.0.0-beta.1", "2.0.0")):
        (repo / f"commit-{index}").write_text(f"commit {index}\n", encoding="utf-8")
        _git(repo, "add", ".")
        _git(repo, "commit", "-q", "-m", f"commit {index}")
        _git(repo, "tag", tag)

    assert _previous_tag(repo, "latest") == "2.0.0"
