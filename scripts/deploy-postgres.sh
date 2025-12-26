#!/bin/bash
# =============================================================================
# ACE Platform - PostgreSQL Deployment Script for Fly.io
# =============================================================================
# This script creates and attaches a PostgreSQL database cluster to the
# ACE Platform application on Fly.io.
#
# Prerequisites:
#   - flyctl installed (https://fly.io/docs/hands-on/install-flyctl/)
#   - Logged in to Fly.io (fly auth login)
#   - ACE Platform app created (fly launch --no-deploy)
#
# Usage:
#   ./scripts/deploy-postgres.sh [options]
#
# Options:
#   --name NAME       PostgreSQL cluster name (default: ace-platform-db)
#   --region REGION   Deployment region (default: iad)
#   --vm-size SIZE    VM size: shared-cpu-1x, shared-cpu-2x, etc (default: shared-cpu-1x)
#   --volume-size GB  Initial volume size in GB (default: 10)
#   --app APP         Application name to attach (default: ace-platform)
#   --help            Show this help message
# =============================================================================

set -e

# Default configuration
DB_NAME="${DB_NAME:-ace-platform-db}"
REGION="${REGION:-iad}"
VM_SIZE="${VM_SIZE:-shared-cpu-1x}"
VOLUME_SIZE="${VOLUME_SIZE:-10}"
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
ACE Platform - PostgreSQL Deployment Script for Fly.io

Prerequisites:
  - flyctl installed (https://fly.io/docs/hands-on/install-flyctl/)
  - Logged in to Fly.io (fly auth login)
  - ACE Platform app created (fly launch --no-deploy)

Usage:
  ./scripts/deploy-postgres.sh [options]

Options:
  --name NAME       PostgreSQL cluster name (default: ace-platform-db)
  --region REGION   Deployment region (default: iad)
  --vm-size SIZE    VM size: shared-cpu-1x, shared-cpu-2x, etc (default: shared-cpu-1x)
  --volume-size GB  Initial volume size in GB (default: 10)
  --app APP         Application name to attach (default: ace-platform)
  --help            Show this help message
EOF
    exit 0
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --name)
            DB_NAME="$2"
            shift 2
            ;;
        --region)
            REGION="$2"
            shift 2
            ;;
        --vm-size)
            VM_SIZE="$2"
            shift 2
            ;;
        --volume-size)
            VOLUME_SIZE="$2"
            shift 2
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

# Check if PostgreSQL cluster already exists
check_existing_cluster() {
    log_info "Checking for existing PostgreSQL cluster..."

    if fly postgres list 2>/dev/null | grep -q "$DB_NAME"; then
        log_warn "PostgreSQL cluster '$DB_NAME' already exists"
        read -p "Do you want to skip creation and just attach? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            return 1  # Skip creation
        else
            log_error "Aborting. Delete the existing cluster first or use a different name."
            exit 1
        fi
    fi

    return 0  # Proceed with creation
}

# Create PostgreSQL cluster
create_postgres_cluster() {
    log_info "Creating PostgreSQL cluster: $DB_NAME"
    log_info "  Region: $REGION"
    log_info "  VM Size: $VM_SIZE"
    log_info "  Volume Size: ${VOLUME_SIZE}GB"

    fly postgres create \
        --name "$DB_NAME" \
        --region "$REGION" \
        --vm-size "$VM_SIZE" \
        --volume-size "$VOLUME_SIZE" \
        --initial-cluster-size 1

    log_success "PostgreSQL cluster created successfully"
}

# Attach PostgreSQL to application
attach_postgres() {
    log_info "Attaching PostgreSQL cluster to app: $APP_NAME"

    # Check if app exists
    if ! fly apps list 2>/dev/null | grep -q "$APP_NAME"; then
        log_error "Application '$APP_NAME' does not exist. Create it first with: fly launch --no-deploy"
        exit 1
    fi

    fly postgres attach "$DB_NAME" --app "$APP_NAME"

    log_success "PostgreSQL attached to $APP_NAME"
    log_info "DATABASE_URL has been set as a secret in your app"
}

# Show connection information
show_connection_info() {
    log_info "Connection Information:"
    echo ""
    echo "  Connect to PostgreSQL:"
    echo "    fly postgres connect -a $DB_NAME"
    echo ""
    echo "  Proxy for local access:"
    echo "    fly proxy 5432 -a $DB_NAME"
    echo ""
    echo "  View secrets (DATABASE_URL):"
    echo "    fly secrets list -a $APP_NAME"
    echo ""
    echo "  View PostgreSQL status:"
    echo "    fly status -a $DB_NAME"
    echo ""
}

# Main execution
main() {
    echo "=============================================="
    echo "  ACE Platform - PostgreSQL Deployment"
    echo "=============================================="
    echo ""

    check_prerequisites

    if check_existing_cluster; then
        create_postgres_cluster
    fi

    attach_postgres
    show_connection_info

    log_success "PostgreSQL deployment complete!"
}

main
