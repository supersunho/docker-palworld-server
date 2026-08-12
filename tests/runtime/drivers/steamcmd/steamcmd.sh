#!/bin/bash
# Controlled SteamCMD driver for Phase 4 ARM64/FEX runtime verification.
# Invoked by the manager as:  FEXBash -c '<this script> +force_install_dir ... +app_update <app> [validate] +quit'
# and for the warm-up as:      FEXBash -c '<this script> +login anonymous +quit'
# We only script the real update command (+app_update). The warm-up just
# prints SteamCMD-like greeting and exits 0, and does NOT modify this file
# (the manager's _ensure_updated digest check requires stable content).
#
# Output is sequence-driven by a monotonic counter file so the first real
# command (initial) and the second (post-recovery retry) differ per scenario.
# Scenario selected by STEAMCMD_SCENARIO (retry_success | valid_fallback |
# missing_fatal | unrelated_failure).
set +e

# Warm-up path: no +app_update -> greeting, exit 0. Do not touch the counter
# (warm-up must never advance the real-update sequence).
if [[ "$*" != *"+app_update"* ]]; then
    echo "Redirecting stderr to '/home/steam/Steam/logs/stderr.txt'"
    echo "Logging directory: '/home/steam/Steam/logs'"
    exit 0
fi

# Real update command: a monotonic counter (initial = 1, post-recovery retry = 2).
STATE_FILE="${STEAMCMD_STATE_FILE:-/home/steam/run_state}"
COUNT=0
[ -f "$STATE_FILE" ] && COUNT="$(cat "$STATE_FILE" 2>/dev/null)"
COUNT=$((COUNT + 1))
echo "$COUNT" > "$STATE_FILE"

SCENARIO="${STEAMCMD_SCENARIO:-retry_success}"
case "$SCENARIO" in
    retry_success)
        if [ "$COUNT" -eq 1 ]; then
            echo "Update state (0x5) verifying, progress: 0.99 (238 / 240)"
            echo "App '2394010' state is 0x6 after update job."
            exit 1
        fi
        echo "Success! App '2394010' fully installed."
        exit 0
        ;;
    valid_fallback | missing_fatal)
        if [ "$COUNT" -eq 1 ]; then
            echo "Update state (0x5) verifying, progress: 0.99 (238 / 240)"
            echo "App '2394010' state is 0x6 after update job."
            exit 1
        fi
        echo "Download failed: app not found"
        echo "ERROR! Failed to install app '2394010'."
        exit 1
        ;;
    unrelated_failure)
        echo "Download failed: disk full"
        echo "ERROR! Failed to install app '2394010'."
        exit 1
        ;;
    *)
        echo "ERROR! Unknown STEAMCMD_SCENARIO '$SCENARIO'"
        exit 1
        ;;
esac