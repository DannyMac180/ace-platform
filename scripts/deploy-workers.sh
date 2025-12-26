#!/bin/bash
# =============================================================================
# ACE Platform - Celery Workers Deployment Script for Fly.io
# =============================================================================
# This script deploys Celery workers and beat scheduler to Fly.io.
# Workers and beat run as separate process groups within the main app.
#
# Prerequisites:
#   - flyctl installed (https://fly.io/docs/hands-on/install-flyctl/)
#   - Logged in to Fly.io (fly auth login)
#   - API server already deployed (./scripts/deploy-api.sh)
#   - Redis already deployed (./scripts/deploy-redis.sh)
#
# Usage:
#   ./scripts/deploy-workers.sh [options]
#
# Options:
#   --app APP               Application name (default: ace-platform)
#   --workers N             Number of worker instances (default: 1)
#   --beat                  Enable beat scheduler (default: enabled)
#   --no-beat               Disable beat scheduler
#   --help                  Show this help message
# =============================================================================

set -e

# Default configuration
APP_NAME="${APP_NAME:-ace-platform}"
WORKER_SCALE="${WORKER_SCALE:-1}"
ENABLE_BEAT="${ENABLE_BEAT:-true}"

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
ACE Platform - Celery Workers Deployment Script for Fly.io

Celery workers and beat scheduler run as separate process groups
within the same Fly.io app. This script manages their scaling.

Prerequisites:
  - flyctl installed (https://fly.io/docs/hands-on/install-flyctl/)
  - Logged in to Fly.io (fly auth login)
  - API server already deployed (./scripts/deploy-api.sh)
  - Redis already deployed (./scripts/deploy-redis.sh)

Usage:
  ./scripts/deploy-workers.sh [options]

Options:
  --app APP               Application name (default: ace-platform)
  --workers N             Number of worker instances (default: 1)
  --beat                  Enable beat scheduler (default: enabled)
  --no-beat               Disable beat scheduler
  --help                  Show this help message

Examples:
  # Deploy with defaults (1 worker, 1 beat)
  ./scripts/deploy-workers.sh

  # Scale to 2 workers
  ./scripts/deploy-workers.sh --workers 2

  # Workers only, no beat scheduler
  ./scripts/deploy-workers.sh --no-beat

Process Groups:
  worker  - Processes background tasks (evolution, etc.)
  beat    - Schedules periodic tasks (auto-evolution triggers)
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
        --workers)
            WORKER_SCALE="$2"
            shift 2
            ;;
        --beat)
            ENABLE_BEAT="true"
            shift
            ;;
        --no-beat)
            ENABLE_BEAT="false"
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

# Check Redis is configured
check_redis() {
    log_info "Checking Redis configuration..."

    local secrets
    secrets=$(fly secrets list --app "$APP_NAME" 2>/dev/null || echo "")

    if ! echo "$secrets" | grep -q "^REDIS_URL[[:space:]]"; then
        log_error "REDIS_URL secret is not set."
        log_error "Deploy Redis first: ./scripts/deploy-redis.sh"
        exit 1
    fi

    log_success "Redis is configured"
}

# Scale worker processes
scale_workers() {
    log_info "Scaling worker process to $WORKER_SCALE instance(s)..."

    fly scale count worker="$WORKER_SCALE" --app "$APP_NAME" --yes

    log_success "Worker process scaled to $WORKER_SCALE instance(s)"
}

# Scale beat scheduler
scale_beat() {
    if [[ "$ENABLE_BEAT" == "true" ]]; then
        log_info "Enabling beat scheduler (1 instance)..."
        fly scale count beat=1 --app "$APP_NAME" --yes
        log_success "Beat scheduler enabled"
    else
        log_info "Disabling beat scheduler..."
        fly scale count beat=0 --app "$APP_NAME" --yes
        log_warn "Beat scheduler disabled - periodic tasks will not run"
    fi
}

# Verify processes are running
verify_processes() {
    log_info "Verifying worker processes..."

    # Give it a moment to start
    sleep 3

    # Get process status
    local status
    status=$(fly status --app "$APP_NAME" 2>/dev/null || echo "")

    if echo "$status" | grep -q "worker.*running\|worker.*started"; then
        log_success "Worker process is running"
    else
        log_warn "Worker process may still be starting. Check with: fly status --app $APP_NAME"
    fi

    if [[ "$ENABLE_BEAT" == "true" ]]; then
        if echo "$status" | grep -q "beat.*running\|beat.*started"; then
            log_success "Beat scheduler is running"
        else
            log_warn "Beat scheduler may still be starting. Check with: fly status --app $APP_NAME"
        fi
    fi
}

# Show deployment information
show_deployment_info() {
    log_info "Celery Workers Information:"
    echo ""
    echo "  Worker Instances: $WORKER_SCALE"
    echo "  Beat Scheduler: $([ "$ENABLE_BEAT" == "true" ] && echo "enabled" || echo "disabled")"
    echo ""
    echo "  Useful commands:"
    echo "    fly status -a $APP_NAME              # Check all processes"
    echo "    fly logs -a $APP_NAME -p worker      # View worker logs"
    echo "    fly logs -a $APP_NAME -p beat        # View beat logs"
    echo "    fly scale show -a $APP_NAME          # Show current scaling"
    echo "    fly scale count worker=N -a $APP_NAME   # Scale workers"
    echo ""
    echo "  Worker Tasks:"
    echo "    - Evolution processing (LLM-based playbook evolution)"
    echo "    - Background job execution"
    echo ""
    echo "  Beat Scheduler Tasks:"
    echo "    - Automatic evolution triggering based on outcome thresholds"
    echo "    - Periodic maintenance tasks"
    echo ""
}

# Main execution
main() {
    echo "=============================================="
    echo "  ACE Platform - Celery Workers Deployment"
    echo "=============================================="
    echo ""

    check_prerequisites
    check_app_deployed
    check_redis
    scale_workers
    scale_beat
    verify_processes
    show_deployment_info

    log_success "Celery workers deployment complete!"
}

main
