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


def test_builder_cleans_tmp_after_rcon_cli_install():
    """L-7: The builder stage must explicitly clean /tmp residue so the
    subsequent COPY --from=builder cannot leak the rcon-cli archive into
    the runtime image."""
    dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text()

    # Find the rcon-cli download block
    rcon_block_start = dockerfile.index("# Download rcon-cli in builder stage")
    rcon_block_end = dockerfile.index("# Build project wheel", rcon_block_start)
    rcon_block = dockerfile[rcon_block_start:rcon_block_end]

    # The cleanup statement must remove rcon-cli tarball + extracted dir.
    assert "/tmp/rcon-cli*" in rcon_block, (
        "Builder must remove /tmp/rcon-cli* after extracting the binary"
    )


def test_runtime_stage_does_not_copy_tmp_from_builder():
    """L-7: The runtime stage must not COPY --from=builder /tmp wholesale."""
    dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text()

    # Locate the runtime stage (after the second FROM).
    runtime_start = dockerfile.index("FROM supersunho/steamcmd-arm64:latest\n")
    runtime_block = dockerfile[runtime_start:]

    # Allowed: explicit, narrow copies from /tmp/wheels (which is then
    # installed and deleted). Disallowed: a wildcard /tmp copy.
    for line in runtime_block.splitlines():
        if "COPY --from=builder" in line and "/tmp" in line:
            # /tmp/wheels is the only permitted /tmp source.
            assert "/tmp/wheels" in line, (
                f"Unexpected /tmp COPY from builder: {line!r}"
            )
