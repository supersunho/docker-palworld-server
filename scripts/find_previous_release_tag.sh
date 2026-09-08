#!/usr/bin/env bash
# Select the previous release tag for changelog generation.
#
# Usage:
#   find_previous_release_tag.sh <current_tag> [prerelease]
#
# Resolution is purely semantic-version based over ALL tags. Commit ancestry
# is deliberately ignored: history rewrites can orphan release commits even
# when two release lines contain patch-equivalent commits.
#   Tier 1 (prerelease current only): newest lower tag with the same
#     MAJOR.MINOR.PATCH base that is itself a prerelease.
#       2.1.0-beta.2 -> 2.1.0-beta.1 ; 2.1.0-rc.1 -> 2.1.0-beta.3
#     Stable releases skip this tier so e.g. 2.1.0 diffs against the
#     previous stable (2.0.0), covering the whole prerelease cycle.
#   Tier 2 (always): newest lower stable tag with a different version base.
#     First prerelease of a line (2.1.0-beta.1 -> 2.0.0) and stable releases
#     (2.1.0 -> 2.0.0) both resolve here when Tier 1 has no match.
#   Tier 3: no match -> print nothing (caller falls back to root commit).
#
# The optional second argument forces prerelease detection ("true"/"false").
# When omitted, a "-" suffix on the current tag implies a prerelease.
# A non-release current tag (e.g. "latest") returns the newest release tag,
# preferring the stable spelling when both exist for one version.
#
# Version comparison is implemented in pure bash so results are identical on
# every runner (system sort -V implementations disagree on prereleases).
# Non-release tags such as `latest` are never selected. A leading `v` is
# ignored while comparing versions, but the original tag spelling is returned.

set -euo pipefail

CURRENT_TAG="${1:-}"
PRERELEASE_ARG="${2:-auto}"

CURRENT_NORMALIZED="${CURRENT_TAG#[vV]}"
CURRENT_BASE="${CURRENT_NORMALIZED%%-*}"

is_release_tag() {
    [[ "$1" =~ ^[vV]?[0-9]+(\.[0-9]+){0,2}(-[0-9A-Za-z.-]+)?$ ]]
}

# vercmp <a> <b>: print -1 (a<b), 0 (a==b) or 1 (a>b) for normalized versions.
# Numeric MAJOR.MINOR.PATCH parts compare numerically; a stable version sorts
# above any prerelease of the same base; prerelease suffixes compare
# dot-field by dot-field (numeric-aware).
vercmp() {
    local a_base="${1%%-*}" b_base="${2%%-*}"
    local IFS=.
    local -a a_parts b_parts
    read -ra a_parts <<< "$a_base"
    read -ra b_parts <<< "$b_base"

    local i av bv
    for (( i = 0; i < 3; i++ )); do
        av="${a_parts[i]:-0}"
        bv="${b_parts[i]:-0}"
        if (( 10#$av < 10#$bv )); then echo -1; return; fi
        if (( 10#$av > 10#$bv )); then echo 1; return; fi
    done

    local a_pre= b_pre=
    [[ "$1" == *"-"* ]] && a_pre="${1#*-}"
    [[ "$2" == *"-"* ]] && b_pre="${2#*-}"
    if [ -z "$a_pre" ] && [ -z "$b_pre" ]; then echo 0; return; fi
    if [ -z "$a_pre" ]; then echo 1; return; fi
    if [ -z "$b_pre" ]; then echo -1; return; fi

    local -a a_fields b_fields
    IFS=. read -ra a_fields <<< "$a_pre"
    IFS=. read -ra b_fields <<< "$b_pre"
    local n="${#a_fields[@]}"
    if [ "${#b_fields[@]}" -gt "$n" ]; then n="${#b_fields[@]}"; fi

    local x y
    for (( i = 0; i < n; i++ )); do
        x="${a_fields[i]:-}"
        y="${b_fields[i]:-}"
        if [[ "$x" =~ ^[0-9]+$ ]] && [[ "$y" =~ ^[0-9]+$ ]]; then
            if (( 10#$x < 10#$y )); then echo -1; return; fi
            if (( 10#$x > 10#$y )); then echo 1; return; fi
        else
            if [[ "$x" < "$y" ]]; then echo -1; return; fi
            if [[ "$x" > "$y" ]]; then echo 1; return; fi
        fi
    done
    echo 0
}
# Non-release current tag: newest release tag overall (stable wins ties).
if ! is_release_tag "$CURRENT_TAG"; then
    BEST="" BEST_NORM=""
    while IFS= read -r tag; do
        is_release_tag "$tag" || continue
        normalized="${tag#[vV]}"
        if [ -z "$BEST" ]; then
            BEST="$tag" BEST_NORM="$normalized"
            continue
        fi
        cmp="$(vercmp "$normalized" "$BEST_NORM")"
        if [ "$cmp" = "1" ]; then
            BEST="$tag" BEST_NORM="$normalized"
        elif [ "$cmp" = "0" ] && [[ "$normalized" != *"-"* ]] && [[ "$BEST_NORM" == *"-"* ]]; then
            BEST="$tag" BEST_NORM="$normalized"
        fi
    done < <(git tag --list)
    [ -n "$BEST" ] && printf '%s\n' "$BEST"
    exit 0
fi

case "$PRERELEASE_ARG" in
    true) PRERELEASE=true ;;
    false) PRERELEASE=false ;;
    auto)
        if [[ "$CURRENT_NORMALIZED" == *"-"* ]]; then
            PRERELEASE=true
        else
            PRERELEASE=false
        fi
        ;;
    *)
        echo "ERROR: second argument must be 'true', 'false', or omitted (got '$PRERELEASE_ARG')" >&2
        exit 1
        ;;
esac

PREV_TAG=""

# Tier 1: same-base prerelease chain (prerelease current only).
if [ "$PRERELEASE" = true ]; then
    BEST="" BEST_NORM=""
    while IFS= read -r tag; do
        is_release_tag "$tag" || continue
        normalized="${tag#[vV]}"
        [ "$normalized" = "$CURRENT_NORMALIZED" ] && continue
        tag_base="${normalized%%-*}"
        [ "$tag_base" = "$CURRENT_BASE" ] || continue
        [[ "$normalized" == *"-"* ]] || continue
        [ "$(vercmp "$normalized" "$CURRENT_NORMALIZED")" = "-1" ] || continue
        if [ -z "$BEST" ] || [ "$(vercmp "$normalized" "$BEST_NORM")" = "1" ]; then
            BEST="$tag" BEST_NORM="$normalized"
        fi
    done < <(git tag --list)
    PREV_TAG="$BEST"
fi

# Tier 2: newest lower stable tag with a different version base.
if [ -z "$PREV_TAG" ]; then
    BEST="" BEST_NORM=""
    while IFS= read -r tag; do
        is_release_tag "$tag" || continue
        normalized="${tag#[vV]}"
        [ "$normalized" = "$CURRENT_NORMALIZED" ] && continue
        tag_base="${normalized%%-*}"
        [ "$tag_base" != "$CURRENT_BASE" ] || continue
        [[ "$normalized" != *"-"* ]] || continue
        [ "$(vercmp "$normalized" "$CURRENT_NORMALIZED")" = "-1" ] || continue
        if [ -z "$BEST" ] || [ "$(vercmp "$normalized" "$BEST_NORM")" = "1" ]; then
            BEST="$tag" BEST_NORM="$normalized"
        fi
    done < <(git tag --list)
    PREV_TAG="$BEST"
fi

if [ -n "$PREV_TAG" ]; then
    printf '%s\n' "$PREV_TAG"
fi
