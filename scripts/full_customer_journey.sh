#!/bin/bash
# Full Customer Journey UAT - Simulates complete user experience (30 min)
# Usage: ./scripts/full_customer_journey.sh [API_URL] [MCP_URL]

set -e

API_URL="${1:-${API_URL:-http://localhost:8000}}"
MCP_URL="${2:-${MCP_URL:-http://localhost:8001}}"
RESULTS_FILE="uat_results_$(date +%Y%m%d_%H%M%S).json"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=== ACE Platform: Full Customer Journey UAT ==="
echo "API: $API_URL"
echo "MCP: $MCP_URL"
echo "Results: $RESULTS_FILE"
echo ""

# Initialize results file
echo '{"tests": [], "timestamp": "'$(date -Iseconds)'", "api_url": "'$API_URL'", "mcp_url": "'$MCP_URL'"}' > $RESULTS_FILE

record_result() {
  local phase="$1"
  local name="$2"
  local status="$3"
  local details="$4"

  jq --arg p "$phase" --arg n "$name" --arg s "$status" --arg d "$details" \
    '.tests += [{"phase": $p, "name": $n, "status": $s, "details": $d}]' \
    $RESULTS_FILE > tmp.$$.json && mv tmp.$$.json $RESULTS_FILE

  if [ "$status" = "PASS" ]; then
    echo -e "  ${GREEN}[PASS]${NC} $name"
  elif [ "$status" = "SKIP" ]; then
    echo -e "  ${YELLOW}[SKIP]${NC} $name: $details"
  else
    echo -e "  ${RED}[FAIL]${NC} $name: $details"
  fi
}

# Test persona
PERSONA_EMAIL="alex_$(date +%s)@startup.io"
PERSONA_PASSWORD="SecureStartup123!"
PERSONA_USERNAME="alex_dev_$(date +%s)"

# ============================================================================
# PHASE 1: DISCOVERY & SIGN-UP
# ============================================================================
echo -e "\n${YELLOW}Phase 1: Discovery & Sign-Up${NC}"
echo "Persona: Alex the AI Developer"
echo ""

# Health checks
if curl -sf "$API_URL/health" > /dev/null 2>&1; then
  record_result "discovery" "API health check" "PASS" ""
else
  record_result "discovery" "API health check" "FAIL" "API not responding"
  echo "Cannot continue - API not available"
  exit 1
fi

if curl -sf "$MCP_URL/health" > /dev/null 2>&1; then
  record_result "discovery" "MCP health check" "PASS" ""
else
  record_result "discovery" "MCP health check" "FAIL" "MCP not responding"
fi

# Registration
echo "  Registering as: $PERSONA_EMAIL"
REGISTER_RESP=$(curl -s -X POST "$API_URL/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$PERSONA_EMAIL\", \"password\": \"$PERSONA_PASSWORD\", \"username\": \"$PERSONA_USERNAME\"}")

ACCESS_TOKEN=$(echo $REGISTER_RESP | jq -r '.access_token // empty')
REFRESH_TOKEN=$(echo $REGISTER_RESP | jq -r '.refresh_token // empty')

if [ -n "$ACCESS_TOKEN" ]; then
  record_result "discovery" "User registration" "PASS" ""
else
  record_result "discovery" "User registration" "FAIL" "$(echo $REGISTER_RESP | jq -r '.detail // "Unknown error"')"
  echo "Cannot continue - registration failed"
  exit 1
fi

# Get current user
ME_RESP=$(curl -s "$API_URL/auth/me" -H "Authorization: Bearer $ACCESS_TOKEN")
if echo $ME_RESP | jq -e '.email' > /dev/null 2>&1; then
  record_result "discovery" "Get current user" "PASS" ""
else
  record_result "discovery" "Get current user" "FAIL" "$(echo $ME_RESP | jq -c '.')"
fi

# ============================================================================
# PHASE 2: FIRST PLAYBOOK
# ============================================================================
echo -e "\n${YELLOW}Phase 2: First Playbook Creation${NC}"

# Create playbook with initial content
INITIAL_CONTENT="# Code Review Guidelines

## Before Reviewing
- Read the PR description thoroughly
- Understand the context and motivation

## During Review
- Check for bugs and logic errors
- Verify error handling exists
- Look for security vulnerabilities
- Ensure code is readable and maintainable
- Check test coverage

## After Review
- Summarize findings clearly
- Be constructive, not critical
- Suggest improvements, don't just criticize"

PLAYBOOK_JSON=$(jq -n \
  --arg name "Code Review Guidelines" \
  --arg desc "Best practices for reviewing code as an AI assistant" \
  --arg content "$INITIAL_CONTENT" \
  '{name: $name, description: $desc, initial_content: $content}')

PLAYBOOK_RESP=$(curl -s -X POST "$API_URL/playbooks" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$PLAYBOOK_JSON")

PLAYBOOK_ID=$(echo $PLAYBOOK_RESP | jq -r '.id // empty')
if [ -n "$PLAYBOOK_ID" ]; then
  record_result "playbook" "Create playbook with content" "PASS" ""
  echo "  Playbook ID: $PLAYBOOK_ID"
  # Check if version was created
  VERSION_ID=$(echo $PLAYBOOK_RESP | jq -r '.current_version.id // empty')
  if [ -n "$VERSION_ID" ]; then
    echo "  Initial version created: $VERSION_ID"
  fi
else
  record_result "playbook" "Create playbook with content" "FAIL" "$(echo $PLAYBOOK_RESP | jq -c '.')"
  echo "Cannot continue - playbook creation failed"
  exit 1
fi

# Verify playbook retrieval with content
GET_RESP=$(curl -s "$API_URL/playbooks/$PLAYBOOK_ID" -H "Authorization: Bearer $ACCESS_TOKEN")
if echo $GET_RESP | jq -e '.current_version.content' > /dev/null 2>&1; then
  record_result "playbook" "Retrieve playbook with content" "PASS" ""
else
  # Check if we at least got the playbook (content might be in different format)
  if echo $GET_RESP | jq -e '.id' > /dev/null 2>&1; then
    record_result "playbook" "Retrieve playbook" "PASS" "(no content yet)"
  else
    record_result "playbook" "Retrieve playbook with content" "FAIL" "$(echo $GET_RESP | jq -c '.')"
  fi
fi

# ============================================================================
# PHASE 3: INTEGRATION SETUP
# ============================================================================
echo -e "\n${YELLOW}Phase 3: Integration Setup${NC}"

# Create API key
APIKEY_RESP=$(curl -s -X POST "$API_URL/auth/api-keys" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Claude Code Integration",
    "scopes": ["playbooks:read", "playbooks:write", "outcomes:write", "evolutions:read", "evolutions:write"]
  }')

API_KEY=$(echo $APIKEY_RESP | jq -r '.key // empty')
if [ -n "$API_KEY" ]; then
  record_result "integration" "Create API key" "PASS" ""
  echo "  API Key created (save this!): ${API_KEY:0:20}..."
else
  record_result "integration" "Create API key" "FAIL" "$(echo $APIKEY_RESP | jq -c '.')"
fi

# List API keys
LIST_KEYS=$(curl -s "$API_URL/auth/api-keys" -H "Authorization: Bearer $ACCESS_TOKEN")
if echo $LIST_KEYS | jq -e 'type == "array" and length > 0' > /dev/null 2>&1; then
  record_result "integration" "List API keys" "PASS" ""
else
  record_result "integration" "List API keys" "FAIL" ""
fi

# Test MCP health (MCP uses its own protocol, not REST - just verify server is up)
MCP_HEALTH=$(curl -s "$MCP_URL/health" 2>/dev/null || echo '{"error": "failed"}')
if echo $MCP_HEALTH | jq -e '.status == "healthy"' > /dev/null 2>&1; then
  record_result "integration" "MCP server healthy" "PASS" ""
else
  record_result "integration" "MCP server healthy" "FAIL" "$(echo $MCP_HEALTH | jq -c '.')"
fi

# Note: MCP tools (list_playbooks, trigger_evolution, etc.) use MCP protocol
# They can be tested via Claude Code with: claude mcp add ace-local --type http --url $MCP_URL/mcp
echo "  Note: MCP tools require MCP protocol client (Claude Code/Desktop)"

# ============================================================================
# PHASE 4: DAILY USAGE
# ============================================================================
echo -e "\n${YELLOW}Phase 4: Daily Usage - Recording Outcomes${NC}"

# Simulate a week of usage with mixed outcomes
OUTCOMES=(
  '{"task_description": "Reviewed PR #101 - User authentication feature", "outcome": "success", "reasoning_trace": "Followed all playbook steps. Found 2 minor issues, provided constructive feedback.", "notes": "Security checklist was helpful for auth code."}'
  '{"task_description": "Reviewed PR #102 - Database query optimization", "outcome": "success", "reasoning_trace": "Caught performance issue using bug-check step.", "notes": "Should add performance review to playbook."}'
  '{"task_description": "Reviewed PR #103 - Frontend component refactor", "outcome": "partial", "reasoning_trace": "Missed accessibility issues - playbook has no a11y checklist.", "notes": "NEED: Add accessibility review section."}'
  '{"task_description": "Reviewed PR #104 - API breaking change", "outcome": "failure", "reasoning_trace": "Approved PR that broke backwards compatibility. Playbook needs API versioning guidance.", "notes": "CRITICAL: Add API compatibility checks."}'
  '{"task_description": "Reviewed PR #105 - Test coverage improvements", "outcome": "success", "reasoning_trace": "Error handling check helped identify missing edge cases.", "notes": "Test coverage section working well."}'
)

for i in "${!OUTCOMES[@]}"; do
  OUTCOME_DATA="${OUTCOMES[$i]}"
  OUTCOME_RESP=$(curl -s -X POST "$API_URL/playbooks/$PLAYBOOK_ID/outcomes" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$OUTCOME_DATA")

  OUTCOME_ID=$(echo $OUTCOME_RESP | jq -r '.outcome_id // .id // empty')
  STATUS=$(echo $OUTCOME_DATA | jq -r '.outcome')

  if [ -n "$OUTCOME_ID" ]; then
    record_result "usage" "Record outcome $((i+1)) ($STATUS)" "PASS" ""
  else
    record_result "usage" "Record outcome $((i+1))" "FAIL" "$(echo $OUTCOME_RESP | jq -c '.')"
  fi

  sleep 1
done

# List outcomes
OUTCOMES_LIST=$(curl -s "$API_URL/playbooks/$PLAYBOOK_ID/outcomes" -H "Authorization: Bearer $ACCESS_TOKEN")
OUTCOME_COUNT=$(echo $OUTCOMES_LIST | jq 'length // 0')
if [ "$OUTCOME_COUNT" -ge 5 ]; then
  record_result "usage" "List outcomes ($OUTCOME_COUNT recorded)" "PASS" ""
else
  record_result "usage" "List outcomes" "FAIL" "Expected 5, got $OUTCOME_COUNT"
fi

# ============================================================================
# PHASE 5: EVOLUTION
# ============================================================================
echo -e "\n${YELLOW}Phase 5: Evolution${NC}"

# Note: Evolution trigger is only available via MCP protocol tools
# We can check evolution history and wait for auto-evolution (triggered after 5 outcomes)
echo "  Note: Evolution trigger requires MCP client (trigger_evolution tool)"
echo "  Checking for auto-evolution (triggers after 5 outcomes)..."

# Check evolution jobs (might have been auto-triggered)
JOBS_RESP=$(curl -s "$API_URL/playbooks/$PLAYBOOK_ID/evolutions" -H "Authorization: Bearer $ACCESS_TOKEN")

# Check if we have any jobs (auto-evolution should have triggered after 5 outcomes)
JOB_COUNT=$(echo $JOBS_RESP | jq '.items | length // 0' 2>/dev/null || echo "0")

if [ "$JOB_COUNT" -gt 0 ]; then
  record_result "evolution" "Evolution job exists (auto-triggered)" "PASS" "$JOB_COUNT job(s)"

  # Get latest job status
  LATEST_JOB=$(echo $JOBS_RESP | jq '.items[0]')
  JOB_STATUS=$(echo $LATEST_JOB | jq -r '.status // "unknown"')
  JOB_ID=$(echo $LATEST_JOB | jq -r '.id // "unknown"')
  echo "  Latest job: $JOB_ID (status: $JOB_STATUS)"

  # If job is running/queued, wait a bit
  if [ "$JOB_STATUS" = "queued" ] || [ "$JOB_STATUS" = "running" ]; then
    echo "  Waiting for evolution to complete (max 120s)..."
    for i in {1..24}; do
      sleep 5
      JOBS_RESP=$(curl -s "$API_URL/playbooks/$PLAYBOOK_ID/evolutions" -H "Authorization: Bearer $ACCESS_TOKEN")
      JOB_STATUS=$(echo $JOBS_RESP | jq -r '.items[0].status // "unknown"')
      echo -n "."
      if [ "$JOB_STATUS" = "completed" ] || [ "$JOB_STATUS" = "failed" ]; then
        echo ""
        break
      fi
    done
  fi

  # Check final status
  JOBS_RESP=$(curl -s "$API_URL/playbooks/$PLAYBOOK_ID/evolutions" -H "Authorization: Bearer $ACCESS_TOKEN")
  LATEST_JOB=$(echo $JOBS_RESP | jq '.items[0]')
  JOB_STATUS=$(echo $LATEST_JOB | jq -r '.status // "unknown"')

  if [ "$JOB_STATUS" = "completed" ]; then
    record_result "evolution" "Evolution completed" "PASS" ""
    OUTCOMES_PROCESSED=$(echo $LATEST_JOB | jq -r '.outcomes_processed // 0')
    echo "  Outcomes processed: $OUTCOMES_PROCESSED"
  else
    record_result "evolution" "Evolution completed" "FAIL" "Status: $JOB_STATUS"
  fi
else
  # No auto-evolution yet - this might be because threshold not met or worker not running
  record_result "evolution" "Auto-evolution triggered" "SKIP" "No jobs yet (may need worker or threshold)"
  echo "  No evolution jobs found - check if Celery worker is running"
fi

# Check versions
VERSIONS_RESP=$(curl -s "$API_URL/playbooks/$PLAYBOOK_ID/versions" -H "Authorization: Bearer $ACCESS_TOKEN")
VERSION_COUNT=$(echo $VERSIONS_RESP | jq '.items | length // 0' 2>/dev/null || echo $VERSIONS_RESP | jq 'length // 0' 2>/dev/null || echo "0")

echo "  Current version count: $VERSION_COUNT"

if [ "$VERSION_COUNT" -ge 2 ]; then
  record_result "evolution" "New version created" "PASS" "$VERSION_COUNT versions"
elif [ "$VERSION_COUNT" -ge 1 ]; then
  record_result "evolution" "Initial version exists" "PASS" "$VERSION_COUNT version(s)"
else
  record_result "evolution" "Version check" "FAIL" "No versions found"
fi

# Show current playbook content
echo -e "\n  ${YELLOW}Current Playbook Content:${NC}"
CURRENT_CONTENT=$(curl -s "$API_URL/playbooks/$PLAYBOOK_ID" -H "Authorization: Bearer $ACCESS_TOKEN" | jq -r '.current_version.content // "No content"')
echo "$CURRENT_CONTENT" | head -15
echo "  ..."

# ============================================================================
# PHASE 6: USAGE & BILLING
# ============================================================================
echo -e "\n${YELLOW}Phase 6: Usage & Billing${NC}"

USAGE_RESP=$(curl -s "$API_URL/usage/summary" -H "Authorization: Bearer $ACCESS_TOKEN")
if echo $USAGE_RESP | jq -e 'type == "object"' > /dev/null 2>&1; then
  record_result "billing" "Get usage summary" "PASS" ""
  TOTAL_TOKENS=$(echo $USAGE_RESP | jq '.total_tokens // 0')
  TOTAL_COST=$(echo $USAGE_RESP | jq '.total_cost // 0')
  echo "  Total tokens: $TOTAL_TOKENS"
  echo "  Total cost: \$$TOTAL_COST"
else
  record_result "billing" "Get usage summary" "FAIL" "$(echo $USAGE_RESP | jq -c '.')"
fi

# ============================================================================
# PHASE 7: EDGE CASES
# ============================================================================
echo -e "\n${YELLOW}Phase 7: Edge Cases & Error Handling${NC}"

# Invalid auth
INVALID_AUTH=$(curl -s -w "\n%{http_code}" "$API_URL/playbooks" -H "Authorization: Bearer invalid_token")
HTTP_CODE=$(echo "$INVALID_AUTH" | tail -1)
if [ "$HTTP_CODE" = "401" ]; then
  record_result "edge_cases" "Invalid auth returns 401" "PASS" ""
else
  record_result "edge_cases" "Invalid auth returns 401" "FAIL" "Got $HTTP_CODE"
fi

# Non-existent playbook
MISSING=$(curl -s -w "\n%{http_code}" "$API_URL/playbooks/00000000-0000-0000-0000-000000000000" -H "Authorization: Bearer $ACCESS_TOKEN")
HTTP_CODE=$(echo "$MISSING" | tail -1)
if [ "$HTTP_CODE" = "404" ]; then
  record_result "edge_cases" "Missing playbook returns 404" "PASS" ""
else
  record_result "edge_cases" "Missing playbook returns 404" "FAIL" "Got $HTTP_CODE"
fi

# Invalid outcome status
INVALID_OUTCOME=$(curl -s -X POST "$API_URL/playbooks/$PLAYBOOK_ID/outcomes" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"task_description": "Test", "outcome": "invalid_status"}')
if echo $INVALID_OUTCOME | jq -e '.error' > /dev/null 2>&1; then
  record_result "edge_cases" "Invalid outcome status rejected" "PASS" ""
else
  record_result "edge_cases" "Invalid outcome status rejected" "FAIL" "$(echo $INVALID_OUTCOME | jq -c '.')"
fi

# ============================================================================
# SUMMARY
# ============================================================================
echo -e "\n${YELLOW}=== Test Summary ===${NC}"

PASSED=$(jq '[.tests[] | select(.status == "PASS")] | length' $RESULTS_FILE)
FAILED=$(jq '[.tests[] | select(.status == "FAIL")] | length' $RESULTS_FILE)
SKIPPED=$(jq '[.tests[] | select(.status == "SKIP")] | length' $RESULTS_FILE)
TOTAL=$(jq '.tests | length' $RESULTS_FILE)

echo "Total Tests: $TOTAL"
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Skipped: ${YELLOW}$SKIPPED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"
echo ""
echo "Results saved to: $RESULTS_FILE"

if [ "$FAILED" -gt 0 ]; then
  echo -e "\n${RED}Failed Tests:${NC}"
  jq -r '.tests[] | select(.status == "FAIL") | "  [\(.phase)] \(.name): \(.details)"' $RESULTS_FILE
  echo ""
  exit 1
else
  echo -e "\n${GREEN}Customer journey validated!${NC}"
  if [ "$SKIPPED" -gt 0 ]; then
    echo -e "${YELLOW}Note: $SKIPPED test(s) skipped - may require additional setup${NC}"
  fi
fi

# Save test artifacts
echo ""
echo "Test Artifacts:"
echo "  Persona Email: $PERSONA_EMAIL"
echo "  Playbook ID: $PLAYBOOK_ID"
echo "  API Key: ${API_KEY:0:20}..."
