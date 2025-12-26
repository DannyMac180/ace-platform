#!/bin/bash
# =============================================================================
# ACE Platform - Redis Deployment Script for Fly.io (Upstash)
# =============================================================================
# This script creates an Upstash Redis database and configures it for the
# ACE Platform application on Fly.io.
#
# Prerequisites:
#   - flyctl installed (https://fly.io/docs/hands-on/install-flyctl/)
#   - Logged in to Fly.io (fly auth login)
#   - ACE Platform app created (fly launch --no-deploy)
#
# Usage:
#   ./scripts/deploy-redis.sh [options]
#
# Options:
#   --name NAME       Redis database name (default: ace-platform-redis)
#   --region REGION   Primary region (default: iad)
#   --plan PLAN       Pricing plan: free, pay-as-you-go (default: free)
#   --replicas        Comma-separated replica regions (optional)
#   --eviction        Enable eviction when memory is full (default: false)
#   --app APP         Application name to configure (default: ace-platform)
#   --help            Show this help message
# =============================================================================

set -e

# Default configuration
REDIS_NAME="${REDIS_NAME:-ace-platform-redis}"
REGION="${REGION:-iad}"
PLAN="${PLAN:-free}"
REPLICAS="${REPLICAS:-}"
EVICTION="${EVICTION:-false}"
APP_NAME="${APP_NAME:-ace-platform}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Show usage
show_help() {
    cat << 'EOF'
ACE Platform - Redis Deployment Script for Fly.io (Upstash)

Prerequisites:
  - flyctl installed (https://fly.io/docs/hands-on/install-flyctl/)
  - Logged in to Fly.io (fly auth login)
  - ACE Platform app created (fly launch --no-deploy)

Usage:
  ./scripts/deploy-redis.sh [options]

Options:
  --name NAME       Redis database name (default: ace-platform-redis)
  --region REGION   Primary region (default: iad)
  --plan PLAN       Pricing plan: free, pay-as-you-go (default: free)
  --replicas        Comma-separated replica regions (optional)
  --eviction        Enable eviction when memory is full (default: false)
  --app APP         Application name to configure (default: ace-platform)
  --help            Show this help message

Examples:
  # Basic deployment with defaults
  ./scripts/deploy-redis.sh

  # Deploy with replicas in multiple regions
  ./scripts/deploy-redis.sh --region iad --replicas lax,cdg

  # Deploy with pay-as-you-go plan and eviction enabled
  ./scripts/deploy-redis.sh --plan pay-as-you-go --eviction
EOF
    exit 0
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --name)
            REDIS_NAME="$2"
            shift 2
            ;;
        --region)
            REGION="$2"
            shift 2
            ;;
        --plan)
            PLAN="$2"
            shift 2
            ;;
        --replicas)
            REPLICAS="$2"
            shift 2
            ;;
        --eviction)
            EVICTION="true"
            shift
            ;;
        --app)
            APP_NAME="$2"
            shift 2
            ;;
        --help|-h)
            show_help
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            ;;
    esac
done

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check if flyctl is installed
    if ! command -v fly &> /dev/null; then
        log_error "flyctl is not installed. Install it from: https://fly.io/docs/hands-on/install-flyctl/"
        exit 1
    fi

    # Check if logged in
    if ! fly auth whoami &> /dev/null; then
        log_error "Not logged in to Fly.io. Run: fly auth login"
        exit 1
    fi

    log_success "Prerequisites check passed"
}

# Check if Redis database already exists
check_existing_redis() {
    log_info "Checking for existing Redis database..."

    if fly redis list 2>/dev/null | grep -q "$REDIS_NAME"; then
        log_warn "Redis database '$REDIS_NAME' already exists"

        # Get the connection URL
        REDIS_URL=$(fly redis status "$REDIS_NAME" 2>/dev/null | grep -i "private url" | awk '{print $NF}' || echo "")

        if [[ -n "$REDIS_URL" ]]; then
            log_info "Found existing Redis URL"
            read -p "Do you want to skip creation and just set the secret? (y/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                return 1  # Skip creation, proceed to set secret
            fi
        fi

        log_error "Aborting. Delete the existing database first or use a different name."
        log_info "To delete: fly redis destroy $REDIS_NAME"
        exit 1
    fi

    return 0  # Proceed with creation
}

# Create Redis database
create_redis() {
    log_info "Creating Upstash Redis database: $REDIS_NAME"
    log_info "  Primary Region: $REGION"
    log_info "  Plan: $PLAN"
    if [[ -n "$REPLICAS" ]]; then
        log_info "  Replicas: $REPLICAS"
    fi
    log_info "  Eviction: $EVICTION"

    # Build the command
    CMD="fly redis create --name $REDIS_NAME --region $REGION"

    if [[ "$PLAN" == "pay-as-you-go" ]]; then
        CMD="$CMD --no-replicas"  # Start without replicas, can add later
    fi

    if [[ "$EVICTION" == "true" ]]; then
        CMD="$CMD --enable-eviction"
    fi

    # Execute the command
    log_info "Running: $CMD"
    eval "$CMD"

    log_success "Redis database created successfully"
}

# Get Redis connection URL
get_redis_url() {
    log_info "Retrieving Redis connection URL..."

    # Get the status which includes the private URL
    local status_output
    status_output=$(fly redis status "$REDIS_NAME" 2>/dev/null)

    # Extract the private URL (for internal Fly.io access)
    REDIS_URL=$(echo "$status_output" | grep -i "private url" | awk '{print $NF}')

    if [[ -z "$REDIS_URL" ]]; then
        # Try alternative format
        REDIS_URL=$(echo "$status_output" | grep -i "redis://" | head -1 | awk '{print $NF}')
    fi

    if [[ -z "$REDIS_URL" ]]; then
        log_error "Could not retrieve Redis URL. Please check: fly redis status $REDIS_NAME"
        exit 1
    fi

    log_success "Retrieved Redis URL"
}

# Set Redis URL as secret
set_redis_secret() {
    log_info "Setting REDIS_URL secret for app: $APP_NAME"

    # Check if app exists
    if ! fly apps list 2>/dev/null | grep -q "$APP_NAME"; then
        log_error "Application '$APP_NAME' does not exist. Create it first with: fly launch --no-deploy"
        exit 1
    fi

    fly secrets set REDIS_URL="$REDIS_URL" --app "$APP_NAME"

    log_success "REDIS_URL secret set for $APP_NAME"
}

# Show connection information
show_connection_info() {
    log_info "Connection Information:"
    echo ""
    echo "  Redis Database: $REDIS_NAME"
    echo "  Primary Region: $REGION"
    echo ""
    echo "  Connect with redis-cli:"
    echo "    fly redis connect"
    echo ""
    echo "  View status:"
    echo "    fly redis status $REDIS_NAME"
    echo ""
    echo "  Open Upstash dashboard:"
    echo "    fly redis dashboard"
    echo ""
    echo "  View secrets (REDIS_URL):"
    echo "    fly secrets list -a $APP_NAME"
    echo ""
    echo "  Update settings (replicas, plan, eviction):"
    echo "    fly redis update $REDIS_NAME"
    echo ""
}

# Main execution
main() {
    echo "=============================================="
    echo "  ACE Platform - Redis Deployment (Upstash)"
    echo "=============================================="
    echo ""

    check_prerequisites

    if check_existing_redis; then
        create_redis
    fi

    get_redis_url
    set_redis_secret
    show_connection_info

    log_success "Redis deployment complete!"
}

main
