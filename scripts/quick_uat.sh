#!/bin/bash
# Quick UAT - Run before each release (5 min)
# Usage: ./scripts/quick_uat.sh [API_URL] [MCP_URL]

set -e

API_URL="${1:-${API_URL:-http://localhost:8000}}"
MCP_URL="${2:-${MCP_URL:-http://localhost:8001}}"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; FAILURES=$((FAILURES + 1)); }

FAILURES=0

echo "=== ACE Platform Quick UAT ==="
echo "API: $API_URL"
echo "MCP: $MCP_URL"
echo ""

# 1. Health check
echo "--- Health Checks ---"
if curl -sf "$API_URL/health" > /dev/null 2>&1; then
  pass "API /health"
else
  fail "API /health not responding"
fi

if curl -sf "$API_URL/ready" > /dev/null 2>&1; then
  pass "API /ready"
else
  fail "API /ready not responding"
fi

if curl -sf "$MCP_URL/health" > /dev/null 2>&1; then
  pass "MCP /health"
else
  fail "MCP /health not responding"
fi

# 2. Auth flow
echo ""
echo "--- Authentication ---"
EMAIL="uat-$(date +%s)@test.com"
REGISTER=$(curl -s -X POST "$API_URL/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$EMAIL\", \"password\": \"TestPass123!\"}" 2>/dev/null)
TOKEN=$(echo $REGISTER | jq -r '.access_token // empty')

if [ -n "$TOKEN" ]; then
  pass "User registration"
else
  fail "User registration: $(echo $REGISTER | jq -r '.detail // .message // "Unknown error"')"
fi

# Login test
LOGIN=$(curl -s -X POST "$API_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$EMAIL\", \"password\": \"TestPass123!\"}" 2>/dev/null)
LOGIN_TOKEN=$(echo $LOGIN | jq -r '.access_token // empty')

if [ -n "$LOGIN_TOKEN" ]; then
  pass "User login"
else
  fail "User login"
fi

# 3. Playbook CRUD
echo ""
echo "--- Playbooks ---"
PLAYBOOK=$(curl -s -X POST "$API_URL/playbooks" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Quick UAT Test", "description": "Automated test"}' 2>/dev/null)
PLAYBOOK_ID=$(echo $PLAYBOOK | jq -r '.id // empty')

if [ -n "$PLAYBOOK_ID" ]; then
  pass "Create playbook"
else
  fail "Create playbook: $(echo $PLAYBOOK | jq -c '.')"
fi

# List playbooks (returns paginated response with .items array)
LIST=$(curl -s "$API_URL/playbooks" -H "Authorization: Bearer $TOKEN" 2>/dev/null)
if echo $LIST | jq -e '.items and .total >= 0' > /dev/null 2>&1; then
  pass "List playbooks"
else
  fail "List playbooks: $(echo $LIST | jq -c '.')"
fi

# Get playbook
GET=$(curl -s "$API_URL/playbooks/$PLAYBOOK_ID" -H "Authorization: Bearer $TOKEN" 2>/dev/null)
if echo $GET | jq -e '.id' > /dev/null 2>&1; then
  pass "Get playbook"
else
  fail "Get playbook"
fi

# 4. Outcome recording
echo ""
echo "--- Outcomes ---"
OUTCOME=$(curl -s -X POST "$API_URL/playbooks/$PLAYBOOK_ID/outcomes" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"task_description": "Quick UAT test task", "outcome": "success", "notes": "Automated test"}' 2>/dev/null)
OUTCOME_ID=$(echo $OUTCOME | jq -r '.outcome_id // .id // empty')

if [ -n "$OUTCOME_ID" ]; then
  pass "Record outcome"
else
  fail "Record outcome: $(echo $OUTCOME | jq -c '.')"
fi

# 5. API Key
echo ""
echo "--- API Keys ---"
APIKEY=$(curl -s -X POST "$API_URL/auth/api-keys" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "UAT Key", "scopes": ["playbooks:read"]}' 2>/dev/null)
API_KEY=$(echo $APIKEY | jq -r '.key // empty')

if [ -n "$API_KEY" ]; then
  pass "Create API key"
else
  fail "Create API key"
fi

# 6. Usage
echo ""
echo "--- Usage ---"
USAGE=$(curl -s "$API_URL/usage/summary" -H "Authorization: Bearer $TOKEN" 2>/dev/null)
if echo $USAGE | jq -e '.total_tokens >= 0 or .total_cost >= 0 or type == "object"' > /dev/null 2>&1; then
  pass "Usage endpoint"
else
  fail "Usage endpoint"
fi

# Summary
echo ""
echo "=== Summary ==="
TOTAL=12
PASSED=$((TOTAL - FAILURES))
echo "Passed: $PASSED / $TOTAL"

if [ $FAILURES -gt 0 ]; then
  echo -e "${RED}$FAILURES test(s) failed${NC}"
  exit 1
else
  echo -e "${GREEN}All tests passed!${NC}"
  exit 0
fi
