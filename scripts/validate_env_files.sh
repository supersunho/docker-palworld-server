#!/usr/bin/env bash
set -euo pipefail

palworld_file="$1"
grafana_file="$2"

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

reject_grafana_keys_from_palworld() {
    local key
    key="$(grep -E '^(GF_|GRAFANA_)' "$palworld_file" | cut -d= -f1 | head -n 1 || true)"
    [[ -z "$key" ]] || fail "Grafana variable $key must not be in $palworld_file"
}

reject_non_grafana_keys_from_grafana() {
    local key
    key="$(awk -F= '
        /^[[:space:]]*#/ || /^[[:space:]]*$/ { next }
        {
            key = $1
            if (key != "GF_SECURITY_ADMIN_USER" &&
                key != "GF_SECURITY_ADMIN_PASSWORD" &&
                key != "GF_INSTALL_PLUGINS") {
                print key
                exit
            }
        }
    ' "$grafana_file")"
    [[ -z "$key" ]] || fail "unexpected variable $key in $grafana_file"
}

require_file "$palworld_file"
require_file "$grafana_file"

for key in SERVER_NAME ADMIN_PASSWORD MAX_PLAYERS SERVER_PORT REST_API_PORT; do
    require_non_empty_key "$palworld_file" "$key"
done
require_non_empty_key "$grafana_file" GF_SECURITY_ADMIN_PASSWORD
reject_grafana_keys_from_palworld
reject_non_grafana_keys_from_grafana

echo "Environment files validated: $palworld_file, $grafana_file"
