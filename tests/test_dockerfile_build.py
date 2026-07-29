from pathlib import Path


def test_builder_installs_pep517_backend_before_no_build_isolation_commands():
    dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text()

    backend_install = dockerfile.index(
        '/opt/venv/bin/pip install --no-cache-dir "setuptools>=61.0" wheel'
    )
    package_install = dockerfile.index(
        "/opt/venv/bin/pip install --no-deps --no-build-isolation ."
    )
    wheel_build = dockerfile.index(
        "/opt/venv/bin/pip wheel --no-deps --no-build-isolation"
    )

    assert backend_install < package_install < wheel_build
