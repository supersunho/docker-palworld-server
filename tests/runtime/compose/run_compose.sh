#!/bin/bash
# Compose-driven Issue #25 runtime reproduction (RUNTIME-02).
#
# Everything runs in an isolated temp root (mktemp) mounted into the compose
# service via PALRUNTIME_* overrides — the production ./palworld_data* dirs are
# never created or touched. The SteamCMD driver is injected (retry_success) and
# the protected world/config tree is SHA-256 hashed as a whole before and after.
#
# Asserts: the bounded 0x6 scenario recovers into a stable HEALTHY state (no
# restart loop — RestartCount stays exactly 0), the recovery snapshot is
# retained in the data root, and the protected tree is byte-identical.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd -P)"
cd "$REPO"

DRV=tests/runtime/drivers
CNAME=palworld-server
COMPOSE_ARGS=(-f docker-compose.yml -f tests/runtime/compose/override.yml)

ROOT="$(mktemp -d "${TMPDIR:-/tmp}/palrt-compose.XXXXXX")"
DATA="$ROOT/data"
BACKUP="$ROOT/backups"
LOGS="$ROOT/logs"
mkdir -p "$DATA" "$BACKUP" "$LOGS"
LOG="$ROOT/compose.log"
echo "isolated_root=$ROOT"

cleanup() {
    docker compose "${COMPOSE_ARGS[@]}" down >/dev/null 2>&1 || true
}
trap cleanup EXIT

# ---- seed the isolated data root idempotently (fresh each run)
mkdir -p "$DATA/Pal/Saved/SaveGames/0/00000001" "$DATA/steamapps"
printf '%s\n' "runtime compose seed config"   > "$DATA/Pal/Config.txt"
printf '%s\n' 'RUNTIME_COMPOSE_LEVEL_01'      > "$DATA/Pal/Saved/SaveGames/0/00000001/level.sav"
printf '%s\n' 'APPMANIFEST_COMPOSE_2394010_01' > "$DATA/steamapps/appmanifest_2394010.acf"
cp "$DRV/palworld/PalServer.sh" "$DATA/PalServer.sh"
chmod +x "$DATA/PalServer.sh"

# whole protected Pal tree hash, captured BEFORE the run. The manager legitimately
# generates new settings files under Pal/ at startup, so the invariant is: every
# seeded file must persist byte-identical (no modification/deletion) afterwards.
hash_pal() { (cd "$DATA" && find Pal -type f -print0 | sort -z | xargs -0 sha256sum); }
PROTECTED_BEFORE="$(hash_pal)"
echo "$PROTECTED_BEFORE" > "$ROOT/protected.before"

# ---- bring the stack up (isolated mounts) and wait for HEALTHY
export PALRUNTIME_DATA_DIR="$DATA" PALRUNTIME_BACKUP_DIR="$BACKUP" PALRUNTIME_LOG_DIR="$LOGS"
docker compose "${COMPOSE_ARGS[@]}" up -d --remove-orphans >/dev/null

DEADLINE=$((SECONDS + 180))
STATUS=starting
while [ "$SECONDS" -lt "$DEADLINE" ]; do
    STATUS="$(docker inspect -f '{{.State.Health.Status}}' "$CNAME" 2>/dev/null || echo gone)"
    [ "$STATUS" = healthy ] && break
    [ "$STATUS" = gone ] && break
    sleep 3
done
echo "health_status=$STATUS (elapsed=${SECONDS}s)"

# ---- stability probe: RestartCount must stay exactly 0 (no restart loop)
RC1="$(docker inspect -f '{{.RestartCount}}' "$CNAME" 2>/dev/null || echo NA)"
sleep 25
RC2="$(docker inspect -f '{{.RestartCount}}' "$CNAME" 2>/dev/null || echo NA)"
echo "restart_count_window=${RC1}->${RC2}"
RUNNING="$(docker inspect -f '{{.State.Running}}' "$CNAME" 2>/dev/null || echo false)"

docker logs "$CNAME" > "$LOG" 2>&1 || true
echo "===== compose log (download/recovery) ====="
grep -F -e 'SteamCMD' -e 'state is 0x6' -e 'recovery' -e 'Server file download' -e 'fully installed' "$LOG" | tail -20 || true
echo "===== snapshot in data root ====="
find "$DATA/.steamcmd-recovery" -name 'appmanifest_2394010.acf' 2>/dev/null | sort || true
echo "===== protected data in data root ====="
find "$DATA/Pal" -type f 2>/dev/null | sort || true

# ---- assertions
FAIL=0
fail() { echo "ASSERT-FAIL: $*"; FAIL=1; }

[ "$STATUS" = healthy ] || fail "compose service not healthy (status=$STATUS)"
[ "$RUNNING" = true ] || fail "container not running"
[ "$RC1" = 0 ] && [ "$RC2" = 0 ] || fail "restart loop detected (RestartCount ${RC1}->${RC2}, expected 0->0)"
grep -qF "SteamCMD state 0x6 metadata recovery attempted" "$LOG" || fail "missing steamcmd_recovery"
grep -qF "Server file download completed" "$LOG" || fail "missing server_download_complete"
find "$DATA/.steamcmd-recovery" -name 'appmanifest_2394010.acf' 2>/dev/null | grep -q . \
    || fail "recovery snapshot not retained in data root"
# manifest must have moved out of steamapps (recovered) 
[ ! -e "$DATA/steamapps/appmanifest_2394010.acf" ] || fail "recovered manifest still in steamapps"
# every seeded Pal file persists byte-identical (new server-generated settings
# files may appear; seeded protected data may not change or vanish)
while read -r h path; do
    cur="$(sha256sum "$DATA/$path" 2>/dev/null | awk '{print $1}')"
    [ "$cur" = "$h" ] || fail "protected file changed/deleted: $path"
done < "$ROOT/protected.before"

if [ "$FAIL" -eq 0 ]; then echo "RESULT: PASS (compose issue#25)"; exit 0; fi
echo "RESULT: FAIL (compose issue#25)"; exit 1