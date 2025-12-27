#!/bin/bash
# =============================================================================
# ACE Platform - Production Secrets Setup Script for Fly.io
# =============================================================================
# This script helps configure all required secrets for production deployment.
#
# Prerequisites:
#   - flyctl installed (https://fly.io/docs/hands-on/install-flyctl/)
#   - Logged in to Fly.io (fly auth login)
#   - App created (fly launch --no-deploy or ./scripts/deploy-api.sh)
#
# Usage:
#   ./scripts/setup-secrets.sh [options]
#
# Options:
#   --app APP               Application name (default: ace-platform)
#   --check                 Check which secrets are set (don't modify)
#   --interactive           Prompt for each secret value
#   --generate-jwt          Generate a secure JWT secret key
#   --help                  Show this help message
# =============================================================================

set -e

# Default configuration
APP_NAME="${APP_NAME:-ace-platform}"
CHECK_ONLY="${CHECK_ONLY:-false}"
INTERACTIVE="${INTERACTIVE:-false}"
GENERATE_JWT="${GENERATE_JWT:-false}"

# Required secrets (core functionality)
REQUIRED_SECRETS=(
    "OPENAI_API_KEY"
    "JWT_SECRET_KEY"
)

# Auto-configured secrets (set by other scripts)
AUTO_SECRETS=(
    "DATABASE_URL"
    "REDIS_URL"
)

# Optional secrets (for billing/Stripe)
BILLING_SECRETS=(
    "STRIPE_SECRET_KEY"
    "STRIPE_WEBHOOK_SECRET"
)

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
ACE Platform - Production Secrets Setup Script for Fly.io

This script helps configure all required secrets for production deployment.

Prerequisites:
  - flyctl installed (https://fly.io/docs/hands-on/install-flyctl/)
  - Logged in to Fly.io (fly auth login)
  - App created (fly launch --no-deploy or ./scripts/deploy-api.sh)

Usage:
  ./scripts/setup-secrets.sh [options]

Options:
  --app APP               Application name (default: ace-platform)
  --check                 Check which secrets are set (don't modify)
  --interactive           Prompt for each secret value
  --generate-jwt          Generate a secure JWT secret key
  --help                  Show this help message

Examples:
  # Check current secrets status
  ./scripts/setup-secrets.sh --check

  # Set secrets interactively
  ./scripts/setup-secrets.sh --interactive

  # Generate and set a JWT secret
  ./scripts/setup-secrets.sh --generate-jwt

  # Set a specific secret
  fly secrets set OPENAI_API_KEY=sk-... --app ace-platform

Required Secrets:
  OPENAI_API_KEY    - OpenAI API key for LLM calls
  JWT_SECRET_KEY    - Secret key for JWT token signing

Auto-Configured Secrets (set by deploy scripts):
  DATABASE_URL      - Set by ./scripts/deploy-postgres.sh
  REDIS_URL         - Set by ./scripts/deploy-redis.sh

Optional Secrets (for billing):
  STRIPE_SECRET_KEY      - Stripe API key for billing
  STRIPE_WEBHOOK_SECRET  - Stripe webhook signing secret
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
        --check)
            CHECK_ONLY="true"
            shift
            ;;
        --interactive)
            INTERACTIVE="true"
            shift
            ;;
        --generate-jwt)
            GENERATE_JWT="true"
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

    # Check if app exists
    if ! fly apps list 2>/dev/null | grep -q "^$APP_NAME[[:space:]]"; then
        log_error "App '$APP_NAME' does not exist."
        log_error "Create it first: fly apps create $APP_NAME"
        exit 1
    fi

    log_success "Prerequisites check passed"
}

# Get current secrets
get_current_secrets() {
    fly secrets list --app "$APP_NAME" 2>/dev/null || echo ""
}

# Check if a secret is set
is_secret_set() {
    local secret_name="$1"
    local secrets="$2"
    echo "$secrets" | grep -q "^$secret_name[[:space:]]"
}

# Check secrets status
check_secrets() {
    log_info "Checking secrets for app: $APP_NAME"
    echo ""

    local secrets
    secrets=$(get_current_secrets)

    echo "Required Secrets:"
    for secret in "${REQUIRED_SECRETS[@]}"; do
        if is_secret_set "$secret" "$secrets"; then
            echo -e "  ${GREEN}✓${NC} $secret"
        else
            echo -e "  ${RED}✗${NC} $secret (not set)"
        fi
    done

    echo ""
    echo "Auto-Configured Secrets:"
    for secret in "${AUTO_SECRETS[@]}"; do
        if is_secret_set "$secret" "$secrets"; then
            echo -e "  ${GREEN}✓${NC} $secret"
        else
            echo -e "  ${YELLOW}○${NC} $secret (not set - run deploy scripts)"
        fi
    done

    echo ""
    echo "Billing Secrets (optional):"
    for secret in "${BILLING_SECRETS[@]}"; do
        if is_secret_set "$secret" "$secrets"; then
            echo -e "  ${GREEN}✓${NC} $secret"
        else
            echo -e "  ${YELLOW}○${NC} $secret (not set)"
        fi
    done

    echo ""

    # Summary
    local missing=0
    for secret in "${REQUIRED_SECRETS[@]}"; do
        if ! is_secret_set "$secret" "$secrets"; then
            ((missing++))
        fi
    done

    if [[ $missing -eq 0 ]]; then
        log_success "All required secrets are set"
    else
        log_warn "$missing required secret(s) missing"
    fi
}

# Generate JWT secret
generate_jwt_secret() {
    log_info "Generating secure JWT secret key..."

    local jwt_secret
    jwt_secret=$(openssl rand -hex 32)

    log_info "Setting JWT_SECRET_KEY..."
    fly secrets set JWT_SECRET_KEY="$jwt_secret" --app "$APP_NAME"

    log_success "JWT_SECRET_KEY has been set"
    echo ""
    echo "  Note: The generated key is securely stored in Fly.io secrets."
    echo "  You don't need to save it separately."
}

# Interactive secret setup
interactive_setup() {
    log_info "Interactive secrets setup for app: $APP_NAME"
    echo ""

    local secrets
    secrets=$(get_current_secrets)

    # OPENAI_API_KEY
    if ! is_secret_set "OPENAI_API_KEY" "$secrets"; then
        echo -e "${YELLOW}OPENAI_API_KEY is not set.${NC}"
        echo "Get your API key from: https://platform.openai.com/api-keys"
        read -p "Enter your OpenAI API key (or press Enter to skip): " -r openai_key
        if [[ -n "$openai_key" ]]; then
            fly secrets set OPENAI_API_KEY="$openai_key" --app "$APP_NAME"
            log_success "OPENAI_API_KEY set"
        else
            log_warn "Skipped OPENAI_API_KEY"
        fi
        echo ""
    else
        log_info "OPENAI_API_KEY already set (skipping)"
    fi

    # JWT_SECRET_KEY
    if ! is_secret_set "JWT_SECRET_KEY" "$secrets"; then
        echo -e "${YELLOW}JWT_SECRET_KEY is not set.${NC}"
        read -p "Generate a secure JWT secret? (Y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            generate_jwt_secret
        else
            read -p "Enter your JWT secret key: " -r jwt_key
            if [[ -n "$jwt_key" ]]; then
                fly secrets set JWT_SECRET_KEY="$jwt_key" --app "$APP_NAME"
                log_success "JWT_SECRET_KEY set"
            else
                log_warn "Skipped JWT_SECRET_KEY"
            fi
        fi
        echo ""
    else
        log_info "JWT_SECRET_KEY already set (skipping)"
    fi

    # Stripe secrets (optional)
    echo "Would you like to configure Stripe billing secrets?"
    read -p "Configure Stripe? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if ! is_secret_set "STRIPE_SECRET_KEY" "$secrets"; then
            echo "Get your Stripe secret key from: https://dashboard.stripe.com/apikeys"
            read -p "Enter your Stripe secret key: " -r stripe_key
            if [[ -n "$stripe_key" ]]; then
                fly secrets set STRIPE_SECRET_KEY="$stripe_key" --app "$APP_NAME"
                log_success "STRIPE_SECRET_KEY set"
            fi
        else
            log_info "STRIPE_SECRET_KEY already set (skipping)"
        fi

        if ! is_secret_set "STRIPE_WEBHOOK_SECRET" "$secrets"; then
            echo "Get your webhook secret from: https://dashboard.stripe.com/webhooks"
            read -p "Enter your Stripe webhook secret: " -r webhook_secret
            if [[ -n "$webhook_secret" ]]; then
                fly secrets set STRIPE_WEBHOOK_SECRET="$webhook_secret" --app "$APP_NAME"
                log_success "STRIPE_WEBHOOK_SECRET set"
            fi
        else
            log_info "STRIPE_WEBHOOK_SECRET already set (skipping)"
        fi
    fi

    echo ""
    log_info "Secrets setup complete. Running final check..."
    echo ""
    check_secrets
}

# Show post-setup info
show_post_setup_info() {
    echo ""
    log_info "Next Steps:"
    echo ""
    echo "  1. If DATABASE_URL is not set, run:"
    echo "     ./scripts/deploy-postgres.sh"
    echo ""
    echo "  2. If REDIS_URL is not set, run:"
    echo "     ./scripts/deploy-redis.sh"
    echo ""
    echo "  3. Deploy the application:"
    echo "     ./scripts/deploy-api.sh"
    echo ""
    echo "  Useful commands:"
    echo "    fly secrets list -a $APP_NAME       # List all secrets"
    echo "    fly secrets set KEY=value -a $APP_NAME  # Set a secret"
    echo "    fly secrets unset KEY -a $APP_NAME  # Remove a secret"
    echo ""
}

# Main execution
main() {
    echo "=============================================="
    echo "  ACE Platform - Production Secrets Setup"
    echo "=============================================="
    echo ""

    check_prerequisites

    if [[ "$CHECK_ONLY" == "true" ]]; then
        check_secrets
        exit 0
    fi

    if [[ "$GENERATE_JWT" == "true" ]]; then
        generate_jwt_secret
        exit 0
    fi

    if [[ "$INTERACTIVE" == "true" ]]; then
        interactive_setup
        show_post_setup_info
        exit 0
    fi

    # Default: show status and instructions
    check_secrets
    show_post_setup_info
}

main
