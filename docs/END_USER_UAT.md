# End-User UAT: Customer Journey Testing

Test ACE Platform as a real customer would experience it. This document provides persona-based test scenarios you can execute manually or automate.

---

## Customer Persona: "Alex the AI Developer"

**Background:** Alex is a developer building AI-powered tools. They want their Claude-based coding assistant to follow consistent practices and improve over time.

**Goals:**
- Create a playbook for their coding assistant
- Have the assistant report outcomes
- See the playbook improve based on real usage
- Track costs and usage

**Technical Comfort:** High (can use CLI, APIs, and Claude Code)

---

## The Customer Journey

### Day 1: Discovery & Sign-Up

#### Scenario 1.1: Landing & First Impression
**As Alex, I want to understand what ACE Platform does and sign up.**

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Visit the landing page | See clear value proposition |
| 2 | Navigate to sign-up | Easy to find registration |
| 3 | Create an account | Account created, logged in |
| 4 | See dashboard | Empty state with clear next steps |

**Test Commands:**
```bash
# Via Web UI
open http://localhost:5173

# Or via API
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "alex@startup.io", "password": "MySecure123!", "username": "alex_dev"}'
```

**Questions to ask yourself:**
- [ ] Is the value proposition clear within 5 seconds?
- [ ] Can I sign up in under 1 minute?
- [ ] Do I understand what to do next after signing up?

---

#### Scenario 1.2: First Playbook Creation
**As Alex, I want to create my first playbook for code reviews.**

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Click "Create Playbook" | Form/modal appears |
| 2 | Enter name & description | Fields accept input |
| 3 | Add initial content | Content saved |
| 4 | See playbook in dashboard | Playbook visible |

**Test Commands:**
```bash
# Login first
LOGIN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "alex@startup.io", "password": "MySecure123!"}')
TOKEN=$(echo $LOGIN | jq -r '.access_token')

# Create playbook
curl -X POST http://localhost:8000/playbooks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Code Review Guidelines",
    "description": "How I want Claude to review my code"
  }'

# Note the playbook ID for later
PLAYBOOK_ID="<from response>"

# Add initial content (version 1)
curl -X POST "http://localhost:8000/playbooks/$PLAYBOOK_ID/versions" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "# Code Review Guidelines\n\n## Before Reviewing\n- Read the PR description\n- Understand the context\n\n## During Review\n- Check for bugs and logic errors\n- Verify error handling exists\n- Look for security issues\n- Ensure code is readable\n\n## After Review\n- Summarize findings clearly\n- Be constructive, not critical"
  }'
```

**Questions to ask yourself:**
- [ ] Was creating a playbook intuitive?
- [ ] Can I see my playbook content after creation?
- [ ] Do I feel confident using it with Claude?

---

### Day 1-3: Integration & First Use

#### Scenario 2.1: Connect Claude Code
**As Alex, I want to connect my playbook to Claude Code.**

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Generate API key | Key displayed (once!) |
| 2 | Configure Claude Code | MCP server connected |
| 3 | Test connection | `list_playbooks` works |

**Test Commands:**
```bash
# Create API key
APIKEY_RESP=$(curl -s -X POST http://localhost:8000/auth/api-keys \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Claude Code Integration",
    "scopes": ["playbooks:read", "playbooks:write", "outcomes:write", "evolutions:read", "evolutions:write"]
  }')
echo $APIKEY_RESP | jq .
API_KEY=$(echo $APIKEY_RESP | jq -r '.key')

# Save this key! It won't be shown again
echo "Your API key: $API_KEY"
```

**Claude Code MCP Setup:**
```bash
# Add the ACE Platform MCP server
claude mcp add ace-platform \
  --type http \
  --url http://localhost:8001/mcp \
  --header "X-API-Key: $API_KEY"

# Verify it works
claude mcp list
```

**Questions to ask yourself:**
- [ ] Was the API key creation process clear?
- [ ] Did I understand to save the key immediately?
- [ ] Is the MCP setup documentation helpful?

---

#### Scenario 2.2: First Real Usage
**As Alex, I use Claude Code with my playbook to review some code.**

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Ask Claude to get playbook | Content retrieved |
| 2 | Claude reviews code | Review follows playbook |
| 3 | Record the outcome | Outcome saved |

**Simulated Workflow in Claude Code:**
```
You: "Get my code review playbook and use it to review this PR"

Claude: [Calls get_playbook MCP tool]
        "I'll follow these guidelines to review your code..."
        [Reviews the code]
        "Review complete. Let me record this outcome."
        [Calls record_outcome MCP tool]
```

**Manual Test (simulating Claude's actions):**
```bash
# Get playbook
curl -s "http://localhost:8001/playbooks/$PLAYBOOK_ID" \
  -H "X-API-Key: $API_KEY" | jq .

# Record a successful outcome
curl -X POST "http://localhost:8000/playbooks/$PLAYBOOK_ID/outcomes" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Reviewed PR #42 - added user authentication",
    "outcome": "success",
    "reasoning_trace": "Followed all steps in playbook. Found 2 minor issues, provided constructive feedback.",
    "notes": "The security checklist was very helpful for this auth-related PR."
  }'
```

**Questions to ask yourself:**
- [ ] Does Claude correctly retrieve and follow the playbook?
- [ ] Is recording outcomes seamless?
- [ ] Do I trust the system is capturing my feedback?

---

### Days 4-7: Building Usage History

#### Scenario 3.1: Regular Usage Pattern
**As Alex, I continue using the playbook for real work over several days.**

Record multiple outcomes (mix of success, failure, partial):

```bash
# Outcome 2: Success
curl -X POST "http://localhost:8000/playbooks/$PLAYBOOK_ID/outcomes" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Reviewed PR #43 - refactored database queries",
    "outcome": "success",
    "reasoning_trace": "Bug check was thorough, found performance issue.",
    "notes": "Should add performance considerations to playbook."
  }'

# Outcome 3: Partial
curl -X POST "http://localhost:8000/playbooks/$PLAYBOOK_ID/outcomes" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Reviewed PR #44 - frontend component",
    "outcome": "partial",
    "reasoning_trace": "Missed accessibility considerations - playbook does not mention a11y.",
    "notes": "Need to add accessibility checklist to playbook."
  }'

# Outcome 4: Failure
curl -X POST "http://localhost:8000/playbooks/$PLAYBOOK_ID/outcomes" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Reviewed PR #45 - API endpoint changes",
    "outcome": "failure",
    "reasoning_trace": "Approved PR that broke backwards compatibility. Playbook needs API versioning guidance.",
    "notes": "Major gap: no mention of API compatibility checks."
  }'

# Outcome 5: Success
curl -X POST "http://localhost:8000/playbooks/$PLAYBOOK_ID/outcomes" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Reviewed PR #46 - test coverage improvements",
    "outcome": "success",
    "reasoning_trace": "Playbook error handling check helped catch missing test cases.",
    "notes": "Error handling section is very effective."
  }'
```

**Questions to ask yourself:**
- [ ] Is recording outcomes quick enough that I'll actually do it?
- [ ] Can I see my accumulated outcomes in the dashboard?
- [ ] Do I feel like the system is learning from my feedback?

---

### Week 2: Evolution Magic

#### Scenario 4.1: Witness Evolution
**As Alex, I see my playbook evolve based on my feedback.**

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Check evolution status | See pending outcomes |
| 2 | Trigger/wait for evolution | New version created |
| 3 | Review new version | Improvements visible |
| 4 | Compare versions | Diff shows changes |

**Test Commands:**
```bash
# Check evolution status
curl -s "http://localhost:8000/playbooks/$PLAYBOOK_ID/evolution-status" \
  -H "Authorization: Bearer $TOKEN" | jq .

# Trigger evolution manually (or wait for auto-trigger after 5 outcomes)
curl -X POST "http://localhost:8000/playbooks/$PLAYBOOK_ID/evolve" \
  -H "Authorization: Bearer $TOKEN" | jq .

# Monitor evolution job (check worker logs or poll)
sleep 60  # Wait for evolution to complete

# Check job status
curl -s "http://localhost:8000/playbooks/$PLAYBOOK_ID/jobs" \
  -H "Authorization: Bearer $TOKEN" | jq '.[-1]'

# See new version
curl -s "http://localhost:8000/playbooks/$PLAYBOOK_ID/versions" \
  -H "Authorization: Bearer $TOKEN" | jq .

# Get the evolved playbook
curl -s "http://localhost:8000/playbooks/$PLAYBOOK_ID" \
  -H "Authorization: Bearer $TOKEN" | jq '.current_version.content'
```

**Questions to ask yourself:**
- [ ] Did the playbook actually improve?
- [ ] Did it incorporate my feedback (a11y, API compatibility)?
- [ ] Can I see what changed between versions?
- [ ] Do I trust this system to improve my workflows?

---

### Ongoing: Usage & Billing

#### Scenario 5.1: Check Usage & Costs
**As Alex, I want to understand my usage and costs.**

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | View usage summary | See token usage, costs |
| 2 | See breakdown by playbook | Per-playbook costs |
| 3 | Understand billing | Clear pricing model |

**Test Commands:**
```bash
# Usage summary
curl -s "http://localhost:8000/usage/summary" \
  -H "Authorization: Bearer $TOKEN" | jq .

# Detailed usage
curl -s "http://localhost:8000/usage?group_by=playbook" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Questions to ask yourself:**
- [ ] Do I understand what I'm being charged for?
- [ ] Can I predict my monthly costs?
- [ ] Is the value worth the cost?

---

## Success Criteria Checklist

After completing the customer journey, rate each area:

| Area | Rating (1-5) | Notes |
|------|--------------|-------|
| **Onboarding Clarity** | | Was it clear what to do? |
| **Time to First Value** | | How long until I saw benefit? |
| **Integration Ease** | | Was MCP setup straightforward? |
| **Daily Workflow Fit** | | Does it fit natural usage? |
| **Evolution Quality** | | Did playbooks actually improve? |
| **Trust & Reliability** | | Do I trust the system? |
| **Cost Transparency** | | Are costs clear and fair? |
| **Overall Satisfaction** | | Would I pay for this? |

**Target:** Each area should score 4+ for launch readiness.

---

## Continuous Testing Framework

### Quick Regression Test (5 min)

Run before each release:

```bash
#!/bin/bash
# save as: scripts/quick_uat.sh

set -e
API_URL="${API_URL:-http://localhost:8000}"
MCP_URL="${MCP_URL:-http://localhost:8001}"

echo "=== ACE Platform Quick UAT ==="

# 1. Health
echo -n "Health check... "
curl -sf "$API_URL/health" > /dev/null && echo "OK" || echo "FAIL"

# 2. Auth flow
echo -n "Auth flow... "
EMAIL="uat-$(date +%s)@test.com"
REGISTER=$(curl -sf -X POST "$API_URL/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$EMAIL\", \"password\": \"Test123!\"}" 2>/dev/null)
TOKEN=$(echo $REGISTER | jq -r '.access_token // empty')
[ -n "$TOKEN" ] && echo "OK" || echo "FAIL"

# 3. Playbook CRUD
echo -n "Playbook CRUD... "
PLAYBOOK=$(curl -sf -X POST "$API_URL/playbooks" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "UAT Test", "description": "Quick test"}' 2>/dev/null)
PLAYBOOK_ID=$(echo $PLAYBOOK | jq -r '.id // empty')
[ -n "$PLAYBOOK_ID" ] && echo "OK" || echo "FAIL"

# 4. Outcome recording
echo -n "Outcome recording... "
OUTCOME=$(curl -sf -X POST "$API_URL/playbooks/$PLAYBOOK_ID/outcomes" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"task_description": "Test", "outcome": "success"}' 2>/dev/null)
OUTCOME_ID=$(echo $OUTCOME | jq -r '.id // empty')
[ -n "$OUTCOME_ID" ] && echo "OK" || echo "FAIL"

# 5. MCP health
echo -n "MCP server... "
curl -sf "$MCP_URL/health" > /dev/null && echo "OK" || echo "FAIL"

echo "=== Quick UAT Complete ==="
```

### Full Customer Journey Test (30 min)

Run weekly or before major releases:

```bash
#!/bin/bash
# save as: scripts/full_customer_journey.sh

set -e
API_URL="${API_URL:-http://localhost:8000}"
MCP_URL="${MCP_URL:-http://localhost:8001}"
RESULTS_FILE="uat_results_$(date +%Y%m%d_%H%M%S).json"

echo "=== Full Customer Journey Test ==="
echo "Results will be saved to: $RESULTS_FILE"

# Initialize results
echo '{"tests": [], "timestamp": "'$(date -Iseconds)'"}' > $RESULTS_FILE

record_result() {
  local name="$1"
  local status="$2"
  local details="$3"
  jq --arg n "$name" --arg s "$status" --arg d "$details" \
    '.tests += [{"name": $n, "status": $s, "details": $d}]' \
    $RESULTS_FILE > tmp.$$.json && mv tmp.$$.json $RESULTS_FILE
  echo "[$status] $name"
}

# Test persona details
PERSONA_EMAIL="alex_$(date +%s)@startup.io"
PERSONA_PASSWORD="SecureStartup123!"

# === PHASE 1: DISCOVERY ===
echo ""
echo "--- Phase 1: Discovery & Sign-Up ---"

# Health check
if curl -sf "$API_URL/health" > /dev/null; then
  record_result "API Health" "PASS" ""
else
  record_result "API Health" "FAIL" "API not responding"
  exit 1
fi

# Registration
REGISTER_RESP=$(curl -s -X POST "$API_URL/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$PERSONA_EMAIL\", \"password\": \"$PERSONA_PASSWORD\", \"username\": \"alex_dev\"}")
ACCESS_TOKEN=$(echo $REGISTER_RESP | jq -r '.access_token // empty')

if [ -n "$ACCESS_TOKEN" ]; then
  record_result "User Registration" "PASS" ""
else
  record_result "User Registration" "FAIL" "$REGISTER_RESP"
  exit 1
fi

# === PHASE 2: FIRST PLAYBOOK ===
echo ""
echo "--- Phase 2: First Playbook ---"

PLAYBOOK_RESP=$(curl -s -X POST "$API_URL/playbooks" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Code Review Guidelines",
    "description": "How I want Claude to review my code"
  }')
PLAYBOOK_ID=$(echo $PLAYBOOK_RESP | jq -r '.id // empty')

if [ -n "$PLAYBOOK_ID" ]; then
  record_result "Create Playbook" "PASS" ""
else
  record_result "Create Playbook" "FAIL" "$PLAYBOOK_RESP"
fi

# Add content
VERSION_RESP=$(curl -s -X POST "$API_URL/playbooks/$PLAYBOOK_ID/versions" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "# Code Review Guidelines\n\n- Check for bugs\n- Verify error handling\n- Look for security issues"
  }')
if echo $VERSION_RESP | jq -e '.version_number' > /dev/null 2>&1; then
  record_result "Add Playbook Content" "PASS" ""
else
  record_result "Add Playbook Content" "FAIL" "$VERSION_RESP"
fi

# === PHASE 3: API KEY & MCP ===
echo ""
echo "--- Phase 3: Integration ---"

APIKEY_RESP=$(curl -s -X POST "$API_URL/auth/api-keys" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Claude Code",
    "scopes": ["playbooks:read", "playbooks:write", "outcomes:write", "evolutions:read", "evolutions:write"]
  }')
API_KEY=$(echo $APIKEY_RESP | jq -r '.key // empty')

if [ -n "$API_KEY" ]; then
  record_result "Create API Key" "PASS" ""
else
  record_result "Create API Key" "FAIL" "$APIKEY_RESP"
fi

# MCP test
MCP_HEALTH=$(curl -s "$MCP_URL/health")
if echo $MCP_HEALTH | jq -e '.status == "healthy"' > /dev/null 2>&1; then
  record_result "MCP Health" "PASS" ""
else
  record_result "MCP Health" "FAIL" "$MCP_HEALTH"
fi

# === PHASE 4: USAGE ===
echo ""
echo "--- Phase 4: Record Outcomes ---"

for i in 1 2 3 4 5; do
  STATUS="success"
  [ $i -eq 3 ] && STATUS="failure"
  [ $i -eq 4 ] && STATUS="partial"

  OUTCOME_RESP=$(curl -s -X POST "$API_URL/playbooks/$PLAYBOOK_ID/outcomes" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
      \"task_description\": \"Reviewed PR #$i\",
      \"outcome\": \"$STATUS\",
      \"reasoning_trace\": \"Test outcome $i\",
      \"notes\": \"UAT test note $i\"
    }")

  if echo $OUTCOME_RESP | jq -e '.id' > /dev/null 2>&1; then
    record_result "Record Outcome $i ($STATUS)" "PASS" ""
  else
    record_result "Record Outcome $i" "FAIL" "$OUTCOME_RESP"
  fi
  sleep 1
done

# === PHASE 5: EVOLUTION ===
echo ""
echo "--- Phase 5: Evolution ---"

EVOLVE_RESP=$(curl -s -X POST "$API_URL/playbooks/$PLAYBOOK_ID/evolve" \
  -H "Authorization: Bearer $ACCESS_TOKEN")
JOB_ID=$(echo $EVOLVE_RESP | jq -r '.job_id // .id // empty')

if [ -n "$JOB_ID" ]; then
  record_result "Trigger Evolution" "PASS" "Job ID: $JOB_ID"
else
  record_result "Trigger Evolution" "FAIL" "$EVOLVE_RESP"
fi

# Wait and check
echo "Waiting 60s for evolution to complete..."
sleep 60

VERSIONS_RESP=$(curl -s "$API_URL/playbooks/$PLAYBOOK_ID/versions" \
  -H "Authorization: Bearer $ACCESS_TOKEN")
VERSION_COUNT=$(echo $VERSIONS_RESP | jq 'length')

if [ "$VERSION_COUNT" -ge 2 ]; then
  record_result "Evolution Created New Version" "PASS" "Versions: $VERSION_COUNT"
else
  record_result "Evolution Created New Version" "FAIL" "Only $VERSION_COUNT version(s)"
fi

# === PHASE 6: USAGE ===
echo ""
echo "--- Phase 6: Usage Tracking ---"

USAGE_RESP=$(curl -s "$API_URL/usage/summary" -H "Authorization: Bearer $ACCESS_TOKEN")
if echo $USAGE_RESP | jq -e '.total_tokens >= 0' > /dev/null 2>&1; then
  record_result "Usage Tracking" "PASS" ""
else
  record_result "Usage Tracking" "FAIL" "$USAGE_RESP"
fi

# === SUMMARY ===
echo ""
echo "=== Test Summary ==="
PASSED=$(jq '[.tests[] | select(.status == "PASS")] | length' $RESULTS_FILE)
FAILED=$(jq '[.tests[] | select(.status == "FAIL")] | length' $RESULTS_FILE)
TOTAL=$(jq '.tests | length' $RESULTS_FILE)

echo "Passed: $PASSED / $TOTAL"
echo "Failed: $FAILED"
echo ""
echo "Full results saved to: $RESULTS_FILE"

if [ "$FAILED" -gt 0 ]; then
  echo ""
  echo "Failed tests:"
  jq -r '.tests[] | select(.status == "FAIL") | "  - \(.name): \(.details)"' $RESULTS_FILE
  exit 1
fi
```

### Make Scripts Executable

```bash
mkdir -p scripts
chmod +x scripts/quick_uat.sh
chmod +x scripts/full_customer_journey.sh
```

### CI Integration

Add to `.github/workflows/uat.yml`:

```yaml
name: Customer Journey UAT

on:
  push:
    branches: [main]
  schedule:
    - cron: '0 8 * * 1'  # Weekly on Monday

jobs:
  uat:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Start services
        run: docker compose --profile full up -d

      - name: Wait for services
        run: sleep 30

      - name: Run Quick UAT
        run: ./scripts/quick_uat.sh

      - name: Run Full Customer Journey
        run: ./scripts/full_customer_journey.sh

      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: uat-results
          path: uat_results_*.json
```

---

## Testing Cadence

| Frequency | Test | Purpose |
|-----------|------|---------|
| Every PR | Quick UAT (5 min) | Catch regressions |
| Weekly | Full Journey (30 min) | Validate experience |
| Pre-release | Manual persona test | Human judgment |
| Post-deploy | Production smoke | Verify deployment |

---

## Issue Reporting Template

When you find issues during UAT, create them with:

```bash
bd create "Issue title" --priority P1 --label uat --label frontend \
  --body "## Persona
Alex the AI Developer

## Scenario
Scenario 2.1: Connect Claude Code

## Steps to Reproduce
1. ...
2. ...

## Expected
...

## Actual
...

## Impact
How this affects the customer experience"
```
