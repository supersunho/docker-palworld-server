#!/bin/bash
# Development entrypoint script for Palworld server
# Optimized for development workflow and debugging

set -e

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

# Check if running in development mode
if [[ "$1" == "--dev" ]]; then
    print_info "Running in development mode"
    
    # Set development-specific environment variables
    export PYTHONPATH="/app/src"
    export LOG_LEVEL="${LOG_LEVEL:-DEBUG}"
    export MONITORING_MODE="${MONITORING_MODE:-both}"
    
    # Validate development environment
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
    
    print_success "Development environment validation complete"
    
    # Run development server
    print_info "Starting development server..."
    cd /app
    exec python3 -m src.server_manager
    
else
    # Production mode
    print_info "Running in production mode"
    
    # Create necessary directories
    mkdir -p /palworld_server/Pal/Saved
    mkdir -p /backups
    mkdir -p /var/log
    
    # Set permissions
    chown -R palworld:palworld /palworld_server /backups /var/log
    
    # Start the main application
    cd /app
    exec python3 -m src.server_manager "$@"
fi
