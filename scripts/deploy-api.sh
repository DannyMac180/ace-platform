#!/bin/bash
# =============================================================================
# ACE Platform - API Server Deployment Script for Fly.io
# =============================================================================
# This script deploys the FastAPI API server to Fly.io.
#
# Prerequisites:
#   - flyctl installed (https://fly.io/docs/hands-on/install-flyctl/)
#   - Logged in to Fly.io (fly auth login)
#   - PostgreSQL deployed (./scripts/deploy-postgres.sh)
#   - Redis deployed (./scripts/deploy-redis.sh)
#
# Usage:
#   ./scripts/deploy-api.sh [options]
#
# Options:
#   --app APP           Application name (default: ace-platform)
#   --region REGION     Primary region (default: iad)
#   --scale N           Number of API instances (default: 1)
#   --skip-secrets      Skip secrets validation
#   --help              Show this help message
# =============================================================================

set -e

# Default configuration
APP_NAME="${APP_NAME:-ace-platform}"
REGION="${REGION:-iad}"
SCALE="${SCALE:-1}"
SKIP_SECRETS="${SKIP_SECRETS:-false}"

# Required secrets
REQUIRED_SECRETS=("OPENAI_API_KEY" "JWT_SECRET_KEY" "DATABASE_URL" "REDIS_URL")

# Optional secrets (for billing)
OPTIONAL_SECRETS=("STRIPE_SECRET_KEY" "STRIPE_WEBHOOK_SECRET")

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
ACE Platform - API Server Deployment Script for Fly.io

Prerequisites:
  - flyctl installed (https://fly.io/docs/hands-on/install-flyctl/)
  - Logged in to Fly.io (fly auth login)
  - PostgreSQL deployed (./scripts/deploy-postgres.sh)
  - Redis deployed (./scripts/deploy-redis.sh)

Usage:
  ./scripts/deploy-api.sh [options]

Options:
  --app APP           Application name (default: ace-platform)
  --region REGION     Primary region (default: iad)
  --scale N           Number of API instances (default: 1)
  --skip-secrets      Skip secrets validation
  --help              Show this help message

Examples:
  # Deploy with defaults
  ./scripts/deploy-api.sh

  # Deploy with 2 instances
  ./scripts/deploy-api.sh --scale 2

  # Deploy to a different region
  ./scripts/deploy-api.sh --region lax
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
        --region)
            REGION="$2"
            shift 2
            ;;
        --scale)
            SCALE="$2"
            shift 2
            ;;
        --skip-secrets)
            SKIP_SECRETS="true"
            shift
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

    # Check if fly.toml exists
    if [[ ! -f "fly.toml" ]]; then
        log_error "fly.toml not found. Run this script from the project root."
        exit 1
    fi

    # Check if Dockerfile exists
    if [[ ! -f "Dockerfile" ]]; then
        log_error "Dockerfile not found. Run this script from the project root."
        exit 1
    fi

    log_success "Prerequisites check passed"
}

# Check if app exists, create if not
ensure_app_exists() {
    log_info "Checking if app '$APP_NAME' exists..."

    if fly apps list 2>/dev/null | grep -q "^$APP_NAME[[:space:]]"; then
        log_info "App '$APP_NAME' already exists"
    else
        log_info "Creating app '$APP_NAME'..."
        fly apps create "$APP_NAME" --org personal
        log_success "App created"
    fi
}

# Validate required secrets are set
validate_secrets() {
    if [[ "$SKIP_SECRETS" == "true" ]]; then
        log_warn "Skipping secrets validation"
        return 0
    fi

    log_info "Validating required secrets..."

    local secrets_output
    secrets_output=$(fly secrets list --app "$APP_NAME" 2>/dev/null || echo "")

    local missing_secrets=()

    for secret in "${REQUIRED_SECRETS[@]}"; do
        if ! echo "$secrets_output" | grep -q "^$secret[[:space:]]"; then
            missing_secrets+=("$secret")
        fi
    done

    if [[ ${#missing_secrets[@]} -gt 0 ]]; then
        log_error "Missing required secrets: ${missing_secrets[*]}"
        echo ""
        echo "Set the missing secrets with:"
        echo "  fly secrets set ${missing_secrets[0]}=<value> --app $APP_NAME"
        echo ""
        echo "Required secrets:"
        echo "  OPENAI_API_KEY     - Your OpenAI API key"
        echo "  JWT_SECRET_KEY     - Secret key for JWT tokens (generate with: openssl rand -hex 32)"
        echo "  DATABASE_URL       - PostgreSQL connection URL (set by 'fly postgres attach')"
        echo "  REDIS_URL          - Redis connection URL (set by 'fly redis create')"
        echo ""
        echo "Or run with --skip-secrets to deploy anyway"
        exit 1
    fi

    log_success "All required secrets are set"

    # Check optional secrets
    for secret in "${OPTIONAL_SECRETS[@]}"; do
        if ! echo "$secrets_output" | grep -q "^$secret[[:space:]]"; then
            log_warn "Optional secret not set: $secret (billing features will be disabled)"
        fi
    done
}

# Deploy the application
deploy_app() {
    log_info "Deploying API server to Fly.io..."
    log_info "  App: $APP_NAME"
    log_info "  Region: $REGION"

    # Deploy with fly deploy
    fly deploy --app "$APP_NAME" --region "$REGION"

    log_success "Deployment complete"
}

# Scale the API process
scale_api() {
    if [[ "$SCALE" -gt 1 ]]; then
        log_info "Scaling API to $SCALE instances..."
        fly scale count api="$SCALE" --app "$APP_NAME"
        log_success "Scaled to $SCALE instances"
    fi
}

# Verify deployment
verify_deployment() {
    log_info "Verifying deployment..."

    # Wait for the app to be ready
    sleep 5

    # Get app status
    local status
    status=$(fly status --app "$APP_NAME" 2>/dev/null || echo "")

    if echo "$status" | grep -q "running"; then
        log_success "API server is running"
    else
        log_warn "API server may not be fully running yet. Check with: fly status --app $APP_NAME"
    fi

    # Get the app URL
    local app_url="https://${APP_NAME}.fly.dev"

    # Try to hit the health endpoint
    log_info "Checking health endpoint..."
    if curl -s -o /dev/null -w "%{http_code}" "$app_url/health" 2>/dev/null | grep -q "200"; then
        log_success "Health check passed: $app_url/health"
    else
        log_warn "Health check not responding yet. The app may still be starting."
    fi
}

# Show deployment information
show_deployment_info() {
    local app_url="https://${APP_NAME}.fly.dev"

    log_info "Deployment Information:"
    echo ""
    echo "  App URL: $app_url"
    echo "  Health: $app_url/health"
    echo "  API Docs: $app_url/docs"
    echo ""
    echo "  Useful commands:"
    echo "    fly status -a $APP_NAME          # Check app status"
    echo "    fly logs -a $APP_NAME            # View logs"
    echo "    fly ssh console -a $APP_NAME     # SSH into container"
    echo "    fly scale count api=N -a $APP_NAME  # Scale API instances"
    echo ""
}

# Main execution
main() {
    echo "=============================================="
    echo "  ACE Platform - API Server Deployment"
    echo "=============================================="
    echo ""

    check_prerequisites
    ensure_app_exists
    validate_secrets
    deploy_app
    scale_api
    verify_deployment
    show_deployment_info

    log_success "API server deployment complete!"
}

main
