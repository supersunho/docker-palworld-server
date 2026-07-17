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


def _previous_tag(repo: Path, current_tag: str) -> str:
    env = {**os.environ, "LC_ALL": "C"}
    result = subprocess.run(
        [str(SCRIPT), current_tag],
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
