# Phase 4 — ARM64 Docker / FEX Runtime Verification

Runtime verification of the ARM64 Palworld image (`supersunho/palworld-server:test`)
that runs the x86_64 SteamCMD and Palworld binaries through **FEX** (`FEXBash`)
in a **`localhost:dind` / `platform=linux/arm64`** container.

A real Palworld instance cannot be started here: the game is a paid Steam app
(`2394010`) that refuses anonymous download, which is exactly the recovery
scenario under test. This harness therefore drives the *real* container entry
points (manager, `FEXBash`, SteamCMD runner, `healthcheck`) against two
deterministic, scripted stand-ins:

- `drivers/steamcmd/steamcmd.sh` — replaces the image SteamCMD entry in-place
  (`-v …/steamcmd.sh:/home/steam/steamcmd/steamcmd.sh`). The manager's
  `validate_steamcmd` / `_ensure_updated` / `is_state_0x6_failure` gates all run
  unmodified against this file, so the exact Issue #25 recovery branch — not a
  mock — is exercised.
- `drivers/palworld/PalServer.sh` — a healthy PalServer stand-in that serves the
  REST readiness endpoint (`GET/POST /v1/api/info → 200`). The manager must use
  it to reach `wait_for_api_ready` (online, no restart loop), and the packaged
  `/usr/local/bin/healthcheck` must exit 0 against it.

## Why a steamcmd driver instead of a unit test

The recovery contract (RUNTIME-01..03) includes *process-level* behavior that a
`pytest` mock cannot observe: the manager launches SteamCMD under `FEXBash` as a
subprocess, streams its output, matches the 0x6 marker, moves `steamapps`
metadata into a retained snapshot, retries once, then either starts the server
(`server_download_complete` / `server_fallback`) or exits fatally
(`server_download_fail`). These runs use the **real built image** with only two
files overridden inside it — a minimal, transparent harness.

## Scenarios (RUNTIME-03)

| Scenario | steamcmd stub behavior | expected terminal state |
|---|---|---|
| `retry_success` | 1st call → `App '2394010' state is 0x6…` exit 1; 2nd → `Success!…fully installed.` exit 0 | **healthy** — `server_download_complete`, healthcheck 0, snapshot retained |
| `valid_fallback` | 1st → 0x6 exit 1; 2nd → `ERROR! Failed to install…` exit 1 | **healthy** — `server_fallback`, healthcheck 0, snapshot retained |
| `missing_fatal` | 1st → 0x6 exit 1; 2nd → `ERROR! Failed…` exit 1 | **fatal** — `server_download_fail`, manager exits (no restart loop) |
| `unrelated_failure` | 1st → `Download failed: disk full` exit 1 (no 0x6 marker) | **fatal** — download failure, **no** recovery, no snapshot |

The SteamCMD driver branches on `STEAMCMD_SCENARIO` and is sequence-driven by a
monotonic counter (`/home/steam/run_state`) so the first and second real update
commands differ. Warm-up invocations (no `+app_update`) are ignored by the
counter.

## Protected-data invariant (RUNTIME-02)

Each run seeds a detached `server` volume containing protected world/config data
(`Pal/Config.txt`, a `level.sav`, and the seeded `steamapps/appmanifest_2394010.acf`
that real SteamCMD would have left behind). The runner snapshots SHA-256 hashes
before the run and asserts byte-identity after: recovery may move the manifest
into `.steamcmd-recovery/` but must never alter or delete protected data.

## Run

```sh
# single scenario (needs: built image supersunho/palworld-server:test)
tests/runtime/run_scenario.sh retry_success
tests/runtime/run_scenario.sh valid_fallback
tests/runtime/run_scenario.sh missing_fatal
tests/runtime/run_scenario.sh unrelated_failure
# each exits 0 on PASS

# or all four
for s in retry_success valid_fallback missing_fatal unrelated_failure; do
  RUNTIME_IMAGE=supersunho/palworld-server:test tests/runtime/run_scenario.sh "$s" && echo "$s: PASS" || echo "$s: FAIL"
done
```

The `palworld_data` directory used by `docker-compose.yml` serves as the
detached `server` volume for these runs, so a compose issue-#25 reproduction is
only a restart of the same container stack (see Task 4).

## Compose reproduction (RUNTIME-02)

The bounded 0x6 recovery under `docker compose` (Issue #25) is exercised by
`compose/run_compose.sh`, backed by `compose/override.yml`:

```sh
tests/runtime/compose/run_compose.sh
```

It seeds `./palworld_data` (a writable `PalServer.sh` stand-in plus protected
world data and a recoverable `steamapps/appmanifest_2394010.acf`), brings the
stack up with the SteamCMD driver injected (`retry_success`), then asserts:

- the service reaches **HEALTHY** (healthcheck exit 0) and stays running;
- **no restart loop** — `RestartCount` holds exactly `0` across a stability
  window;
- the manager logs `steamcmd_recovery` and `server_download_complete`;
- `.steamcmd-recovery/app-2394010-*/` snapshot is retained **in the
  `palworld_data` volume**, inspectable beside the intact protected data.

## Acceptance notes

- RUNTIME-01 — image builds, boots `aarch64`, manager starts SteamCMD under
  `FEXBash`; a successful update (`retry_success`) or a valid fallback
  (`valid_fallback`) reaches a healthy Palworld stand-in.
- RUNTIME-02 — the bounded 0x6 scenario (compose) recovers into a stable state
  (no restart loop) with the snapshot and protected data inspectable in the
  volume.
- RUNTIME-03 — the four outputs are distinguished by manager event + exit +
  healthcheck; unrelated failures do **not** trigger the wide recovery sweep.