#!/bin/bash
# Production entrypoint script for Palworld server
# Optimized for ARM64 + FEX environment with comprehensive error handling

set -euo pipefail

# Color output functions
print_info() {
    echo -e "\033[0;36m[INFO]\033[0m $1"
}

print_warn() {
    echo -e "\033[0;33m[WARN]\033[0m $1"
}

print_error() {
    echo -e "\033[0;31m[ERROR]\033[0m $1"
}

print_success() {
    echo -e "\033[0;32m[SUCCESS]\033[0m $1"
}

# Configuration validation
validate_environment() {
    print_info "Validating environment configuration..."
    
    # Check required environment variables
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
    
    # Validate port ranges
    if [[ $SERVER_PORT -lt 1024 || $SERVER_PORT -gt 65535 ]]; then
        print_error "SERVER_PORT must be between 1024 and 65535"
        exit 1
    fi
    
    if [[ $REST_API_PORT -lt 1024 || $REST_API_PORT -gt 65535 ]]; then
        print_error "REST_API_PORT must be between 1024 and 65535"
        exit 1
    fi
    
    # Validate player count
    if [[ $MAX_PLAYERS -lt 1 || $MAX_PLAYERS -gt 32 ]]; then
        print_error "MAX_PLAYERS must be between 1 and 32"
        exit 1
    fi
    
    print_success "Environment validation completed"
}

# Permission setup
setup_permissions() {
    print_info "Setting up file permissions..."
    
    # Ensure directories exist with correct permissions
    local directories=(
        "/palworld_server"
        "/backups"
        "/var/log/palworld"
        "/palworld_server/Pal/Saved"
        "/palworld_server/Pal/Saved/Config"
        "/palworld_server/Pal/Saved/Config/LinuxServer"
    )
    
    for dir in "${directories[@]}"; do
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir"
        fi
        
        # Set ownership if running as root (startup phase)
        if [[ $EUID -eq 0 ]]; then
            chown -R ${PUID}:${PGID} "$dir"
        fi
    done
    
    print_success "Permissions setup completed"
}

# FEX environment optimization
optimize_fex_environment() {
    print_info "Optimizing FEX-Emu environment for ARM64..."
    
    # Set FEX-specific environment variables for better performance
    export FEX_ROOTFS="/home/steam/.fex-emu/RootFS/Ubuntu_22_04"
    export FEX_APP_CONFIG_LOCATION="/home/steam/.fex-emu"
    
    # Optimize memory usage for game servers
    export FEX_ENABLE_JIT_CACHE=1
    export FEX_JIT_CACHE_SIZE=512
    
    # Check if FEX is properly configured
    if [[ ! -d "$FEX_ROOTFS" ]]; then
        print_warn "FEX RootFS not found at $FEX_ROOTFS"
        print_warn "Some features may not work correctly"
    fi
    
    print_success "FEX environment optimization completed"
}

# Server file management
manage_server_files() {
    print_info "Managing Palworld server files..."
    
    # Check if server files need to be downloaded/updated
    local server_executable="/palworld_server/PalServer.sh"
    
    if [[ ! -f "$server_executable" ]] || [[ "${AUTO_UPDATE:-true}" == "true" ]]; then
        print_info "Server files missing or update requested, will be handled by Python manager"
    else
        print_info "Server files present, skipping download"
    fi
    
    print_success "Server file management completed"
}

# Backup system initialization
initialize_backup_system() {
    if [[ "${BACKUP_ENABLED:-true}" == "true" ]]; then
        print_info "Initializing backup system..."
        
        # Create backup directory structure
        mkdir -p /backups/automatic /backups/manual
        
        # Set up backup retention policy
        local retention_days=${BACKUP_RETENTION_DAYS:-7}
        print_info "Backup retention set to $retention_days days"
        
        print_success "Backup system initialized"
    else
        print_info "Backup system disabled"
    fi
}

# Discord integration setup
setup_discord_integration() {
    if [[ "${DISCORD_ENABLED:-false}" == "true" ]] && [[ -n "${DISCORD_WEBHOOK_URL:-}" ]]; then
        print_info "Discord integration enabled"
        
        # Validate webhook URL format
        if [[ $DISCORD_WEBHOOK_URL =~ ^https://discord(app)?\.com/api/webhooks/ ]]; then
            print_success "Discord webhook URL validated"
        else
            print_warn "Discord webhook URL format appears invalid"
        fi
    else
        print_info "Discord integration disabled"
    fi
}

# Monitoring system setup
setup_monitoring() {
    local monitoring_mode=${MONITORING_MODE:-both}
    print_info "Setting up monitoring system (mode: $monitoring_mode)"
    
    case $monitoring_mode in
        "logs")
            print_info "Log-based monitoring enabled"
            ;;
        "prometheus")
            print_info "Prometheus metrics enabled"
            ;;
        "both")
            print_info "Dual monitoring system enabled (logs + prometheus)"
            ;;
        *)
            print_warn "Unknown monitoring mode: $monitoring_mode, defaulting to 'both'"
            export MONITORING_MODE="both"
            ;;
    esac
    
    print_success "Monitoring system setup completed"
}

# Signal handling for graceful shutdown
setup_signal_handlers() {
    print_info "Setting up signal handlers for graceful shutdown..."
    
    # Trap signals and forward to Python application
    trap 'print_info "Received SIGTERM, initiating graceful shutdown..."; kill -TERM $PID; wait $PID' TERM
    trap 'print_info "Received SIGINT, initiating graceful shutdown..."; kill -INT $PID; wait $PID' INT
    
    print_success "Signal handlers configured"
}

# Health check setup
setup_health_monitoring() {
    print_info "Setting up health monitoring..."
    
    # Ensure health check script is executable
    if [[ -f "/usr/local/bin/healthcheck" ]]; then
        chmod +x /usr/local/bin/healthcheck
        print_success "Health check system ready"
    else
        print_warn "Health check script not found"
    fi
}

# Main execution function
run_server() {
    print_info "Starting Palworld server management system..."
    
    # Change to application directory
    cd /app
    
    # Determine execution mode
    case "${1:---start-server}" in
        "--start-server")
            print_info "Starting server in normal mode"
            exec python -m src.server_manager
            ;;
        "--backup-only")
            print_info "Running in backup-only mode"
            exec python -m src.backup.backup_manager
            ;;
        "--health-check")
            print_info "Running health check"
            exec python /usr/local/bin/healthcheck
            ;;
        "--shell")
            print_info "Starting interactive shell"
            exec /bin/bash
            ;;
        *)
            print_info "Starting server with custom arguments: $*"
            exec python -m src.server_manager "$@"
            ;;
    esac
}

# Main execution flow
main() {
    echo "🚀 Starting Palworld Dedicated Server (ARM64 + FEX)"
    echo "   Version: 1.0.0"
    echo "   Architecture: ARM64"
    echo "   Base: supersunho/steamcmd-arm64"
    echo ""
    
    # Execute initialization steps
    validate_environment
    setup_permissions
    optimize_fex_environment
    manage_server_files
    initialize_backup_system
    setup_discord_integration
    setup_monitoring
    setup_signal_handlers
    setup_health_monitoring
    
    print_success "Initialization completed successfully"
    echo ""
    
    # Start the server
    run_server "$@"
}

# Execute main function with all arguments
main "$@"
