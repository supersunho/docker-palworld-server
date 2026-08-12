#!/bin/bash
# Phase 4 runtime verification runner.
# Runs one scenario against the ARM64 image with the controlled SteamCMD /
# PalServer drivers mounted in, then asserts RUNTIME-01..03 observable
# contracts (manager events, process exit, container healthcheck).
#
# Usage:  tests/runtime/run_scenario.sh <scenario>
#   scenario ∈ retry_success | valid_fallback | missing_fatal | unrelated_failure
#
# Each scenario lives in tests/runtime/scenarios/<scenario>/run.conf with:
#   STEAMCMD_SCENARIO=<driver branch>   (what the steamcmd stub emits)
#   PALWORLD_STUB=healthy|absent        (serve REST readiness, or no server)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd -P)"             # tests/runtime
REPO="$(cd "$(dirname "$0")/../.." && pwd -P)"       # project root
SCENARIO="${1:?usage: run_scenario.sh <scenario>}"
# Constrain scenario to a plain basename. Prevents path traversal via the
# $ROOT/scenarios/$SCENARIO/run.conf source below (an untrusted arg must never
# escape the scenarios/ dir or relocate mktemp outside ${TMPDIR}).
if [[ ! "$SCENARIO" =~ ^[A-Za-z0-9_-]+$ ]]; then
    echo "invalid scenario name '$SCENARIO' (must match ^[A-Za-z0-9_-]+\$)" >&2; exit 2
fi
CONF="$ROOT/scenarios/$SCENARIO/run.conf"
[ -f "$CONF" ] || { echo "no scenario $SCENARIO ($CONF)"; exit 2; }

IMAGE="${RUNTIME_IMAGE:-supersunho/palworld-server:test}"
NAME="pal-runtime-$SCENARIO"
CONTAINER="palrt-$SCENARIO-$$"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/palrt-$SCENARIO.XXXXXX")"
# Clean up the detached test container and scratch dir on ANY exit path
# (normal completion, fatal exit, SIGINT/TERM). Prevents leaked containers /
# stale temp roots after an abnormal termination.
cleanup() {
    [ -n "${CONTAINER:-}" ] && docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    [ -n "${WORK:-}" ] && rm -rf "$WORK"
}
trap cleanup EXIT
SERVER_DIR="$WORK/server"
LOG="$WORK/manager.log"
RESULT="$WORK/result.txt"

# ---- load scenario config
set -a; . "$CONF"; set +a
PALWORLD_STUB="${PALWORLD_STUB:-healthy}"

rm -f "$RESULT"
exec > >(tee "$WORK/run.log") 2>&1

# ---- seed the detached server_dir volume with protected data + recoverable
# metadata target (an appmanifest a real SteamCMD would have left behind).
mkdir -p "$SERVER_DIR/Pal/Saved/SaveGames/0/00000001" "$SERVER_DIR/steamapps"
printf '%s\n' "runtime seed config"    > "$SERVER_DIR/Pal/Config.txt"
printf '%s\n' 'RUNTIME_LEVEL_SEED_01'  > "$SERVER_DIR/Pal/Saved/SaveGames/0/00000001/level.sav"
printf '%s\n' 'APPMANIFEST_2394010_01' > "$SERVER_DIR/steamapps/appmanifest_2394010.acf"
if [ "$PALWORLD_STUB" = healthy ]; then
    cp "$ROOT/drivers/palworld/PalServer.sh" "$SERVER_DIR/PalServer.sh"
    chmod +x "$SERVER_DIR/PalServer.sh"
fi
# Seed a value the server writes on boot (world/"protected" install data).
printf '%s\n' 'RUNTIME_PAL_SERVER_SH' > "$SERVER_DIR/Pal/PalServer.sh.seed"
SEED_MANIFEST='APPMANIFEST_2394010_01'
echo "$SEED_MANIFEST" > "$WORK/manifest.orig"

# Protected-file baseline hashes (world/config only; the SteamCMD manifest is
# a *recoverable* target that 0x6 recovery legitimately moves into a snapshot).
PROTECTED=( "Pal/Config.txt" "Pal/Saved/SaveGames/0/00000001/level.sav" "Pal/PalServer.sh.seed" )
: > "$WORK/protected.before"
for rel in "${PROTECTED[@]}"; do
    sha256sum "$SERVER_DIR/$rel" >> "$WORK/protected.before"
done

# ---- launch detached so we can observe both steady-state (healthy) and exit (fatal)
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$CONTAINER" \
    -e SERVER_NAME="pal-runtime-$SCENARIO" \
    -e ADMIN_PASSWORD="hashed_11223344556677889900aabbccddeeff11223344556677889900aabbccddeeff" \
    -e MAX_PLAYERS=8 -e SERVER_PORT=8211 -e REST_API_PORT=8212 \
    -e REST_API_ENABLED=true -e RCON_ENABLED=true \
    -e STEAMCMD_SCENARIO="$STEAMCMD_SCENARIO" \
    -e STEAMCMD_STATE_FILE=/home/steam/run_state \
    -e RCON_ENABLED=false \
    -v "$ROOT/drivers/steamcmd/steamcmd.sh:/home/steam/steamcmd/steamcmd.sh:ro" \
    -v "$SERVER_DIR:/home/steam/palworld_server" \
    "$IMAGE" --start-server >/dev/null
echo "container=$CONTAINER work=$WORK"

# ---- terminal log message per healthy scenario (console drops event_type;
# log_server_event renders only the message text).
case "$SCENARIO" in
    retry_success)      TERMINAL_MSG="Server file download completed" ;;
    valid_fallback)     TERMINAL_MSG="SteamCMD recovery failed; starting existing server build" ;;
    *)                  TERMINAL_MSG="" ;;
esac

# ---- poll for terminal state (healthy+terminal-msg, or container exited)
DEADLINE=$((SECONDS + 240))
HEALTH_RC=99
while [ "$SECONDS" -lt "$DEADLINE" ]; do
    if docker ps -q --filter name="$CONTAINER" | grep -q .; then
        # still running -> try healthcheck (authoritative readiness)
        HEALTH_RC=0
        docker exec "$CONTAINER" /usr/local/bin/healthcheck </dev/null >"$WORK/healthcheck.out" 2>&1 || HEALTH_RC=$?
        if [ "$HEALTH_RC" -eq 0 ]; then
            # healthy: for the recover-then-serve scenarios also wait for the
            # terminal log message so post-loop asserts see the full outcome.
            if [ -z "$TERMINAL_MSG" ] || grep -qF "$TERMINAL_MSG" "$WORK/manager.log" 2>/dev/null; then
                echo "state=healthy healthcheck_rc=0" | tee "$RESULT"; break
            fi
        fi
    else
        echo "state=exited healthcheck_rc=$HEALTH_RC" | tee "$RESULT"; break
    fi
    docker logs "$CONTAINER" > "$WORK/manager.log" 2>&1 || true
    sleep 3
done
[ -f "$RESULT" ] || { echo "state=timeout healthcheck_rc=$HEALTH_RC" | tee "$RESULT"; }
docker logs "$CONTAINER" > "$LOG" 2>&1 || true
echo "state=$(cat "$RESULT" 2>/dev/null)"
# grace for recovery/snapshot to settle after healthy
[ "$(grep -o 'state=healthy' "$RESULT" 2>/dev/null)" ] && sleep 8

echo "===== manager log ====="
sed -n '1,200p' "$LOG"
echo "===== protected after ===="
sha256sum "$SERVER_DIR"/Pal/Config.txt "$SERVER_DIR"/Pal/Saved/SaveGames/0/00000001/level.sav "$SERVER_DIR"/steamapps/appmanifest_2394010.acf 2>&1 || true
echo "===== snapshot dir ====="
find "$SERVER_DIR/.steamcmd-recovery" -maxdepth 4 2>/dev/null | sort || true

# ---- assertions (console logs render message text only; log_server_event's
# event_type is not printed by the custom console renderer)
FAIL=0
fail() { echo "ASSERT-FAIL: $*"; FAIL=1; }

grep -qF "Starting Palworld server file download" "$LOG" \
    || fail "no server_download_start message"

case "$SCENARIO" in
    retry_success)
        grep -qF "SteamCMD state 0x6 metadata recovery attempted" "$LOG" \
            || fail "missing steamcmd_recovery"
        grep -qF "SteamCMD retry after metadata recovery" "$LOG" \
            || fail "missing steamcmd_recovery_retry"
        grep -qF "Server file download completed" "$LOG" \
            || fail "missing server_download_complete"
        grep -q '^state=healthy' "$RESULT" || fail "expected healthy (healthcheck rc 0)"
        SNAP="$(find "$SERVER_DIR/.steamcmd-recovery" -name 'appmanifest_2394010.acf' 2>/dev/null | head -1)"
        [ -n "$SNAP" ] || fail "recovery snapshot not retained in server_dir"
        echo "$SEED_MANIFEST" > /dev/null # (manifest.orig written at seed time)
        [ ! -e "$SERVER_DIR/steamapps/appmanifest_2394010.acf" ] \
            || fail "recovered manifest still in original location"
        ;;
    valid_fallback)
        grep -qF "SteamCMD state 0x6 metadata recovery attempted" "$LOG" \
            || fail "missing steamcmd_recovery"
        grep -qF "SteamCMD retry after metadata recovery" "$LOG" \
            || fail "missing steamcmd_recovery_retry"
        grep -qF "SteamCMD recovery failed; starting existing server build" "$LOG" \
            || fail "missing server_fallback (valid deployment)"
        grep -q '^state=healthy' "$RESULT" || fail "expected healthy fallback (healthcheck rc 0)"
        find "$SERVER_DIR/.steamcmd-recovery" -name 'appmanifest_2394010.acf' 2>/dev/null | grep -q . \
            || fail "recovery snapshot not retained"
        ;;
    missing_fatal)
        grep -qF "SteamCMD state 0x6 metadata recovery attempted" "$LOG" \
            || fail "missing steamcmd_recovery"
        [ "$(grep -cF 'SteamCMD state 0x6 metadata recovery attempted' "$LOG")" -ge 1 ] \
            || fail "missing steamcmd_recovery"
        grep -qF "Server file download failed after recovery; no valid executable" "$LOG" \
            || fail "missing fatal-after-recovery message"
        grep -q '^state=exited' "$RESULT" || fail "expected fatal exit, not restart-loop"
        [ ! -e "$SERVER_DIR/PalServer.sh" ] || fail "PalServer.sh present in missing_fatal scenario"
        ;;
    unrelated_failure)
        grep -qF "Server file download failed" "$LOG" || fail "missing fatal download failure log"
        if grep -qF "SteamCMD state 0x6 metadata recovery attempted" "$LOG"; then
            fail "unrelated failure triggered recovery"
        fi
        grep -q '^state=exited' "$RESULT" || fail "container did not exit"
        [ -d "$SERVER_DIR/.steamcmd-recovery" ] && fail "snapshot created on unrelated failure"
        [ -f "$SERVER_DIR/steamapps/appmanifest_2394010.acf" ] || fail "manifest moved on unrelated failure"
        ;;
esac

# ---- protected data invariant: world/config bytes preserved on every path
for rel in "${PROTECTED[@]}"; do
    bef="$(awk -v r="$SERVER_DIR/$rel" '$2==r{print $1}' "$WORK/protected.before")"
    aft="$(sha256sum "$SERVER_DIR/$rel" | awk '{print $1}')"
    [ "$bef" = "$aft" ] || fail "protected data changed: $rel"
done
# recoverable manifest: byte-identical inside the retained snapshot
if [ -d "$SERVER_DIR/.steamcmd-recovery" ]; then
    for snap in $(find "$SERVER_DIR/.steamcmd-recovery" -name 'appmanifest_2394010.acf' 2>/dev/null); do
        orig="$(sha256sum "$WORK/manifest.orig" 2>/dev/null | awk '{print $1}')" # seeded bytes
        snapsha="$(sha256sum "$snap" | awk '{print $1}')"
        [ "$orig" = "$snapsha" ] || fail "moved manifest not byte-identical: $snap"
    done
fi

echo "===== healthcheck(after) ====="
[ -f "$WORK/healthcheck.out" ] && cat "$WORK/healthcheck.out" || true

docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
if [ "$FAIL" -eq 0 ]; then
    echo "RESULT: PASS ($SCENARIO)  [work=$WORK]"
    exit 0
else
    echo "RESULT: FAIL ($SCENARIO)  [work=$WORK]"
    exit 1
fi