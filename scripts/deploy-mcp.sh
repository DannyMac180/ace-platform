#!/bin/bash
# =============================================================================
# ACE Platform - MCP Server Deployment Script for Fly.io
# =============================================================================
# This script deploys the MCP (Model Context Protocol) server to Fly.io.
# The MCP server runs as a separate process group alongside the API server.
#
# Prerequisites:
#   - flyctl installed (https://fly.io/docs/hands-on/install-flyctl/)
#   - Logged in to Fly.io (fly auth login)
#   - API server already deployed (./scripts/deploy-api.sh)
#
# Usage:
#   ./scripts/deploy-mcp.sh [options]
#
# Options:
#   --app APP           Application name (default: ace-platform)
#   --scale N           Number of MCP instances (default: 1)
#   --help              Show this help message
# =============================================================================

set -e

# Default configuration
APP_NAME="${APP_NAME:-ace-platform}"
SCALE="${SCALE:-1}"

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
ACE Platform - MCP Server Deployment Script for Fly.io

The MCP server runs as a separate process group in the same Fly.io app
as the API server. This script scales the MCP process after initial deployment.

Prerequisites:
  - flyctl installed (https://fly.io/docs/hands-on/install-flyctl/)
  - Logged in to Fly.io (fly auth login)
  - API server already deployed (./scripts/deploy-api.sh)

Usage:
  ./scripts/deploy-mcp.sh [options]

Options:
  --app APP           Application name (default: ace-platform)
  --scale N           Number of MCP instances (default: 1)
  --help              Show this help message

Examples:
  # Ensure MCP process is running (1 instance)
  ./scripts/deploy-mcp.sh

  # Scale to 2 MCP instances
  ./scripts/deploy-mcp.sh --scale 2

Note: The MCP server is deployed as part of the main app deployment.
      This script manages the MCP process scaling and verification.
EOF
    exit 0
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --app)
            APP_NAME="$2"
            shift 2
            ;;
        --scale)
            SCALE="$2"
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

# Check if app exists and is deployed
check_app_deployed() {
    log_info "Checking if app '$APP_NAME' is deployed..."

    if ! fly apps list 2>/dev/null | grep -q "^$APP_NAME[[:space:]]"; then
        log_error "App '$APP_NAME' does not exist."
        log_error "Deploy the API server first: ./scripts/deploy-api.sh"
        exit 1
    fi

    # Check if there are running machines
    local status
    status=$(fly status --app "$APP_NAME" 2>/dev/null || echo "")

    if ! echo "$status" | grep -q "running\|started"; then
        log_error "App '$APP_NAME' is not running."
        log_error "Deploy the API server first: ./scripts/deploy-api.sh"
        exit 1
    fi

    log_success "App is deployed and running"
}

# Scale MCP process
scale_mcp() {
    log_info "Scaling MCP process to $SCALE instance(s)..."

    # Scale the MCP process group
    fly scale count mcp="$SCALE" --app "$APP_NAME" --yes

    log_success "MCP process scaled to $SCALE instance(s)"
}

# Verify MCP process is running
verify_mcp() {
    log_info "Verifying MCP process..."

    # Give it a moment to start
    sleep 3

    # Get process status
    local status
    status=$(fly status --app "$APP_NAME" 2>/dev/null || echo "")

    if echo "$status" | grep -q "mcp.*running\|mcp.*started"; then
        log_success "MCP process is running"
    else
        log_warn "MCP process may still be starting. Check with: fly status --app $APP_NAME"
    fi
}

# Show deployment information
show_deployment_info() {
    log_info "MCP Server Information:"
    echo ""
    echo "  The MCP server runs as a process group within the Fly.io app."
    echo "  It uses SSE transport for remote connections."
    echo ""
    echo "  MCP Server Port: 8001 (internal)"
    echo ""
    echo "  Useful commands:"
    echo "    fly status -a $APP_NAME          # Check all processes"
    echo "    fly logs -a $APP_NAME -p mcp     # View MCP logs"
    echo "    fly scale show -a $APP_NAME      # Show current scaling"
    echo "    fly scale count mcp=N -a $APP_NAME  # Scale MCP instances"
    echo ""
    echo "  Connecting to MCP Server:"
    echo "    The MCP server requires API key authentication."
    echo "    Generate an API key via the API: POST /auth/api-keys"
    echo ""
    echo "  Claude Desktop Configuration (for remote access):"
    echo "    Configure Claude Desktop to connect via SSE transport"
    echo "    with the appropriate API key for authentication."
    echo ""
}

# Main execution
main() {
    echo "=============================================="
    echo "  ACE Platform - MCP Server Deployment"
    echo "=============================================="
    echo ""

    check_prerequisites
    check_app_deployed
    scale_mcp
    verify_mcp
    show_deployment_info

    log_success "MCP server deployment complete!"
}

main
