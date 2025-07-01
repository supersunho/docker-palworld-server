#!/bin/bash
set -euo pipefail

source /app/scripts/color_output.sh

declare -g SERVER_PID=""
declare -g SHUTDOWN_INITIATED=false

validate_environment() {
    print_info "Validating environment variables..."
    
    local required_vars=(
        "SERVER_NAME"
        "ADMIN_PASSWORD"
        "MAX_PLAYERS"
        "SERVER_PORT"
        "REST_API_PORT"
    )
    
    for var in "${required_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            print_error "Required environment variable $var is not set"
            exit 1
        fi
    done
    
    if [[ $SERVER_PORT -lt 1024 || $SERVER_PORT -gt 65535 ]]; then
        print_error "SERVER_PORT must be between 1024 and 65535"
        exit 1
    fi
    
    if [[ $REST_API_PORT -lt 1024 || $REST_API_PORT -gt 65535 ]]; then
        print_error "REST_API_PORT must be between 1024 and 65535"
        exit 1
    fi
    
    if [[ $MAX_PLAYERS -lt 1 || $MAX_PLAYERS -gt 32 ]]; then
        print_error "MAX_PLAYERS must be between 1 and 32"
        exit 1
    fi
    
    print_success "Environment validation completed"
}

setup_permissions() {
    print_info "Setting up directory permissions..."
    
    local directories=(
        "/home/steam/palworld_server"
        "/home/steam/backups"
        "/home/steam/logs/palworld"
        "/home/steam/palworld_server/Pal/Saved"
        "/home/steam/palworld_server/Pal/Saved/Config"
        "/home/steam/palworld_server/Pal/Saved/Config/LinuxServer"
    )
    
    for dir in "${directories[@]}"; do
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir"
        fi
        
        if [[ $EUID -eq 0 ]]; then
            local current_owner=$(stat -c "%u:%g" "$dir" 2>/dev/null || echo "0:0")
            if [[ "$current_owner" != "steam:steam" ]]; then
                chown -R "steam:steam" "$dir"
            fi
        fi
    done
    
    print_success "Directory permissions configured"
}

optimize_fex_environment() {
    print_info "Optimizing FEX environment for ARM64..."
    
    export FEX_ENABLE_JIT_CACHE=1
    export FEX_JIT_CACHE_SIZE=1024
    export FEX_ENABLE_VIXL_SIMULATOR=0
    export FEX_ENABLE_VIXL_DISASSEMBLER=0
    export FEX_ENABLE_LAZY_MEMORY_DELETION=1
    export FEX_ENABLE_STATIC_REGISTER_ALLOCATION=1
    
    print_success "FEX optimization applied"
}

initialize_backup_system() {
    if [[ "${BACKUP_ENABLED:-true}" == "true" ]]; then
        print_info "Initializing backup system..."
        mkdir -p /home/steam/backups/automatic /home/steam/backups/manual
        print_success "Backup system initialized"
    else
        print_warn "Backup system disabled"
    fi
}

setup_monitoring() {
    print_info "Configuring monitoring system..."
    
    local monitoring_mode=${MONITORING_MODE:-both}
    case $monitoring_mode in
        "logs"|"prometheus"|"both")
            print_success "Monitoring mode set to: $monitoring_mode"
            ;;
        *)
            print_warn "Invalid monitoring mode '$monitoring_mode', defaulting to 'both'"
            export MONITORING_MODE="both"
            ;;
    esac
}

setup_signal_handlers() {
    graceful_shutdown() {
        if [[ "$SHUTDOWN_INITIATED" == "true" ]]; then
            return
        fi
        
        SHUTDOWN_INITIATED=true
        print_warn "Graceful shutdown initiated..."
        
        if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
            print_info "Stopping server process (PID: $SERVER_PID)..."
            kill -TERM "$SERVER_PID" 2>/dev/null || true
            
            local count=0
            while kill -0 "$SERVER_PID" 2>/dev/null && [[ $count -lt 30 ]]; do
                sleep 1
                ((count++))
            done
            
            if kill -0 "$SERVER_PID" 2>/dev/null; then
                print_warn "Force killing server process..."
                kill -KILL "$SERVER_PID" 2>/dev/null || true
            fi
            
            print_success "Server shutdown completed"
        fi
        
        exit 0
    }
    
    trap graceful_shutdown SIGTERM SIGINT SIGQUIT
}

run_server() {
    cd /app
    print_info "Starting server with mode: ${1:---start-server}"
    
    case "${1:---start-server}" in
        "--start-server")
            print_info "Launching Palworld server manager..."
            python -m src.server_manager &
            SERVER_PID=$!
            print_success "Server started with PID: $SERVER_PID"
            wait $SERVER_PID
            local exit_code=$?
            print_info "Server exited with code: $exit_code"
            exit $exit_code
            ;;
        "--backup-only")
            print_info "Starting backup-only mode..."
            python -m src.backup.backup_manager &
            SERVER_PID=$!
            wait $SERVER_PID
            ;;
        "--health-check")
            print_info "Running health check..."
            exec python /usr/local/bin/healthcheck
            ;;
        "--shell")
            print_info "Starting interactive shell..."
            exec /bin/bash
            ;;
        "--supervisor")
            print_info "Starting supervisor mode..."
            exec supervisord -c /etc/supervisor/conf.d/supervisord.conf
            ;;
        *)
            print_info "Starting server with custom arguments: $*"
            python -m src.server_manager "$@" &
            SERVER_PID=$!
            wait $SERVER_PID
            ;;
    esac
}

main() {
    print_info "=== Palworld Server Entrypoint ==="
    print_info "Architecture: $(uname -m)"
    print_info "Server Name: ${SERVER_NAME}"
    print_info "Max Players: ${MAX_PLAYERS}"
    print_info "Ports: Game=${SERVER_PORT}, API=${REST_API_PORT}"
    
    validate_environment
    setup_permissions
    optimize_fex_environment
    initialize_backup_system
    setup_monitoring
    setup_signal_handlers
    
    print_success "Initialization completed successfully"
    run_server "$@"
}

main "$@"
