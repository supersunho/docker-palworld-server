#!/bin/bash

print_info() {
    echo -e "\033[0;32m[INFO]\033[0m $1"
}

print_warn() {
    echo -e "\033[0;33m[WARN]\033[0m $1"
}

print_error() {
    echo -e "\033[0;31m[ERROR]\033[0m $1"
}

print_success() {
    echo -e "\033[1;32m[SUCCESS]\033[0m $1"
}

print_debug() {
    echo -e "\033[0;36m[DEBUG]\033[0m $1"
}

colorize() {
    local text="$1"
    local color="$2"
    case "$color" in
        "red") echo -e "\033[0;31m${text}\033[0m" ;;
        "green") echo -e "\033[0;32m${text}\033[0m" ;;
        "yellow") echo -e "\033[0;33m${text}\033[0m" ;;
        "blue") echo -e "\033[0;34m${text}\033[0m" ;;
        "cyan") echo -e "\033[0;36m${text}\033[0m" ;;
        *) echo "$text" ;;
    esac
}
