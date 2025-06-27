#!/bin/bash
# Development entrypoint script for Palworld server
# Optimized for development workflow and debugging

set -euo pipefail

echo "🚀 Starting Palworld Server Development Environment"

# Function to print colored output
print_info() {
    echo -e "\033[0;36m[INFO]\033[0m $1"
}

print_error() {
    echo -e "\033[0;31m[ERROR]\033[0m $1"
}

print_success() {
    echo -e "\033[0;32m[SUCCESS]\033[0m $1"
}

print_warn() {
    echo -e "\033[0;33m[WARN]\033[0m $1"
}

# Validate development environment
validate_dev_environment() {
    print_info "Validating development environment..."
    
    # Check Python environment
    if ! python3 --version > /dev/null 2>&1; then
        print_error "Python3 not found"
        exit 1
    fi
    
    # Check source directory
    if [[ ! -d "/app/src" ]]; then
        print_error "Source directory not found at /app/src"
        exit 1
    fi
    
    # Check if configuration exists
    if [[ ! -f "/app/config/default.yaml" ]]; then
        print_error "Configuration file not found at /app/config/default.yaml"
        exit 1
    fi
    
    # Check Python dependencies
    if ! python3 -c "import aiohttp, structlog, yaml" 2>/dev/null; then
        print_warn "Some Python dependencies may be missing"
        print_info "Installing development dependencies..."
        pip install -r /app/requirements-dev.txt || true
    fi
    
    print_success "Development environment validation complete"
}

# Setup development permissions (optimized based on search result #5)
setup_dev_permissions() {
    print_info "Setting up development permissions..."
    
    local directories=(
        "/palworld_server"
        "/backups" 
        "/var/log"
        "/palworld_server/Pal/Saved"
    )
    
    for dir in "${directories[@]}"; do
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir"
        fi
        
        # Only change ownership if needed (avoiding Docker Desktop macOS issue)
        if [[ $EUID -eq 0 ]]; then
            # Use stat to check current ownership (search result #5 pattern)
            local current_owner=$(stat -c "%u:%g" "$dir" 2>/dev/null || echo "0:0")
            local target_owner="${PUID:-1000}:${PGID:-1000}"
            
            if [[ "$current_owner" != "$target_owner" ]]; then
                chown "$target_owner" "$dir"
                print_info "Set ownership for $dir"
            fi
        fi
    done
    
    print_success "Development permissions setup complete"
}

# Enhanced development mode execution
run_development_mode() {
    print_info "Running in development mode"
    
    # Set development-specific environment variables
    export PYTHONPATH="/app/src"
    export LOG_LEVEL="${LOG_LEVEL:-DEBUG}"
    export MONITORING_MODE="${MONITORING_MODE:-both}"
    export PYTHONUNBUFFERED=1
    export PYTHONDONTWRITEBYTECODE=1
    
    # Validate environment
    validate_dev_environment
    
    # Setup permissions
    setup_dev_permissions
    
    # Run development server with auto-reload capability
    print_info "Starting development server with auto-reload..."
    cd /app
    
    # Check if watchdog is available for auto-reload
    if python3 -c "import watchdog" 2>/dev/null; then
        print_info "Watchdog available - enabling auto-reload"
        exec python3 -m src.server_manager --dev --reload
    else
        print_info "Running in standard development mode"
        exec python3 -m src.server_manager --dev
    fi
}

# Production mode execution (search result #6 pattern)
run_production_mode() {
    print_info "Running in production mode"
    
    # Create necessary directories
    mkdir -p /palworld_server/Pal/Saved
    mkdir -p /backups
    mkdir -p /var/log
    
    # Set permissions following search result #5 guidance
    if [[ $EUID -eq 0 ]]; then
        local puid=${PUID:-1000}
        local pgid=${PGID:-1000}
        
        # Validate PUID/PGID (security best practice)
        if [[ "$puid" -eq 0 ]] || [[ "$pgid" -eq 0 ]]; then
            print_error "Running as root is not supported, please fix your PUID and PGID!"
            exit 1
        fi
        
        print_info "Setting ownership to $puid:$pgid"
        chown -R "$puid:$pgid" /palworld_server /backups /var/log 2>/dev/null || true
    fi
    
    # Start the main application
    cd /app
    export PYTHONPATH="/app/src"
    exec python3 -m src.server_manager "$@"
}

# Main execution logic (search result #8 pattern)
main() {
    # Check if running in development mode
    if [[ "${1:-}" == "--dev" ]]; then
        run_development_mode
    else
        run_production_mode "$@"
    fi
}

# Execute main function with all arguments
main "$@"
