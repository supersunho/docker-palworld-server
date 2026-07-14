import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
COMPOSE_FILE = ROOT / "docker-compose.yml"
VALIDATOR = ROOT / "scripts" / "validate_env_files.sh"


def tracked_paths() -> list[str]:
    output = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True)
    return output.splitlines()


def write_env_files(tmp_path: Path, *, admin_password: str = "ci-admin-secret") -> None:
    (tmp_path / ".env.palworld").write_text(
        "\n".join(
            [
                "SERVER_NAME=ci-test",
                f"ADMIN_PASSWORD={admin_password}",
                "MAX_PLAYERS=16",
                "SERVER_PORT=8211",
                "REST_API_PORT=8212",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / ".env.grafana").write_text(
        "GF_SECURITY_ADMIN_USER=admin\n"
        "GF_SECURITY_ADMIN_PASSWORD=ci-grafana-secret\n"
        "GF_INSTALL_PLUGINS=\n",
        encoding="utf-8",
    )


def run_validator(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(VALIDATOR), ".env.palworld", ".env.grafana"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )


def test_tracked_hidden_entries_are_repository_files_only() -> None:
    hidden_entries = {
        path.split("/", 1)[0] for path in tracked_paths() if path.startswith(".")
    }

    assert hidden_entries == {
        ".dockerignore",
        ".env.grafana.example",
        ".env.palworld.example",
        ".github",
        ".gitignore",
        ".pre-commit-config.yaml",
    }
    assert not any(
        path == "docs" or path.startswith("docs/") for path in tracked_paths()
    )


def test_compose_uses_isolated_env_files_without_inline_environment() -> None:
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))

    palworld = compose["services"]["palworld-server"]
    grafana = compose["services"]["grafana"]

    assert palworld["env_file"] == [".env.palworld"]
    assert grafana["env_file"] == [".env.grafana"]
    assert "environment" not in palworld
    assert "environment" not in grafana


def test_palworld_template_does_not_contain_grafana_credentials() -> None:
    lines = ROOT.joinpath(".env.palworld.example").read_text(
        encoding="utf-8"
    ).splitlines()

    assert not any(line.startswith(("GRAFANA_", "GF_")) for line in lines)


def test_grafana_template_uses_only_native_grafana_names() -> None:
    lines = ROOT.joinpath(".env.grafana.example").read_text(
        encoding="utf-8"
    ).splitlines()
    keys = {line.split("=", 1)[0] for line in lines if "=" in line}

    assert keys == {
        "GF_SECURITY_ADMIN_USER",
        "GF_SECURITY_ADMIN_PASSWORD",
        "GF_INSTALL_PLUGINS",
    }


def test_env_validator_accepts_complete_isolated_files(tmp_path: Path) -> None:
    write_env_files(tmp_path)

    result = run_validator(tmp_path)

    assert result.returncode == 0, result.stderr


def test_env_validator_rejects_missing_required_value_without_secret_output(
    tmp_path: Path,
) -> None:
    write_env_files(tmp_path)
    (tmp_path / ".env.palworld").write_text(
        "SERVER_NAME=ci-test\nMAX_PLAYERS=16\nSERVER_PORT=8211\nREST_API_PORT=8212\n",
        encoding="utf-8",
    )

    result = run_validator(tmp_path)

    assert result.returncode != 0
    assert "ADMIN_PASSWORD" in result.stderr
    assert "ci-admin-secret" not in result.stderr


def test_env_validator_rejects_missing_env_file(tmp_path: Path) -> None:
    (tmp_path / ".env.grafana").write_text(
        "GF_SECURITY_ADMIN_PASSWORD=ci-grafana-secret\n",
        encoding="utf-8",
    )

    result = run_validator(tmp_path)

    assert result.returncode != 0
    assert ".env.palworld" in result.stderr


def test_env_validator_rejects_grafana_keys_in_palworld_file(tmp_path: Path) -> None:
    write_env_files(tmp_path)
    with (tmp_path / ".env.palworld").open("a", encoding="utf-8") as file:
        file.write("GF_SECURITY_ADMIN_PASSWORD=ci-grafana-secret\n")

    result = run_validator(tmp_path)

    assert result.returncode != 0
    assert "GF_SECURITY_ADMIN_PASSWORD" in result.stderr
    assert "ci-grafana-secret" not in result.stderr
