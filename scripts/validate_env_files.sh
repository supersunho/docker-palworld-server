#!/usr/bin/env bash
set -euo pipefail

palworld_file="$1"

fail() {
    echo "env validation failed: $1" >&2
    exit 1
}

require_file() {
    local file="$1"
    [[ -f "$file" ]] || fail "missing env file $file"
}

require_non_empty_key() {
    local file="$1"
    local key="$2"
    local line=""
    local value=""

    line="$(grep -E "^$key=" "$file" | tail -n 1 || true)"
    [[ -n "$line" ]] || fail "missing required variable $key in $file"
    value="$(printf '%s\n' "$line" | cut -d= -f2-)"
    [[ -n "$value" ]] || fail "required variable $key is empty in $file"
}

require_file "$palworld_file"

for key in SERVER_NAME ADMIN_PASSWORD MAX_PLAYERS SERVER_PORT REST_API_PORT; do
    require_non_empty_key "$palworld_file" "$key"
done

echo "Environment file validated: $palworld_file"
