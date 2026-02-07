# User Acceptance Testing (UAT) Checklist

Pre-launch testing checklist for ACE Platform. Complete all sections before closing ace-platform-66.

## Test Environment Setup

- [ ] Docker Compose stack running (`docker compose --profile full up -d`)
- [ ] All services healthy (`docker compose ps` shows healthy status)
- [ ] Environment variables configured (`.env` file)
- [ ] Database migrated (`docker compose run --rm migrate`)

---

## 1. Authentication & Authorization

### 1.1 User Registration
- [ ] Register new user via API
  ```bash
  curl -X POST http://localhost:8000/auth/register \
    -H "Content-Type: application/json" \
    -d '{"email": "test@example.com", "password": "SecurePass123!", "username": "testuser"}'
  ```
- [ ] Email validation works (rejects invalid emails)
- [ ] Password requirements enforced (min 8 chars)
- [ ] Duplicate email rejected

### 1.2 User Login
- [ ] Login with valid credentials returns tokens
  ```bash
  curl -X POST http://localhost:8000/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email": "test@example.com", "password": "SecurePass123!"}'
  ```
- [ ] Access token works for authenticated requests
- [ ] Invalid credentials return 401
- [ ] Account lockout after failed attempts (5 attempts)
- [ ] Lockout expires after configured time

### 1.3 Token Refresh
- [ ] Refresh token returns new access token
  ```bash
  curl -X POST http://localhost:8000/auth/refresh \
    -H "Content-Type: application/json" \
    -d '{"refresh_token": "YOUR_REFRESH_TOKEN"}'
  ```
- [ ] Expired refresh token rejected

### 1.4 API Keys
- [ ] Create API key
  ```bash
  curl -X POST http://localhost:8000/auth/api-keys \
    -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"name": "Test Key", "scopes": ["playbooks:read", "playbooks:write", "outcomes:write"]}'
  ```
- [ ] List API keys
- [ ] API key authentication works (`X-API-Key` header)
- [ ] Revoke API key
- [ ] Revoked key rejected
- [ ] Scope enforcement (key without scope can't access endpoint)

---

## 2. Playbook Management

### 2.1 Create Playbook
- [ ] Create playbook via API
  ```bash
  curl -X POST http://localhost:8000/playbooks \
    -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"name": "Test Playbook", "description": "Testing UAT"}'
  ```
- [ ] Name validation (required, max length)
- [ ] Returns created playbook with ID

### 2.2 List Playbooks
- [ ] List all playbooks for user
  ```bash
  curl http://localhost:8000/playbooks \
    -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
  ```
- [ ] Pagination works (`?limit=10&offset=0`)
- [ ] Only shows user's own playbooks

### 2.3 Get Playbook
- [ ] Get single playbook by ID
  ```bash
  curl http://localhost:8000/playbooks/{playbook_id} \
    -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
  ```
- [ ] Returns current version content
- [ ] 404 for non-existent playbook
- [ ] 403 for other user's playbook

### 2.4 Update Playbook
- [ ] Update playbook metadata
  ```bash
  curl -X PATCH http://localhost:8000/playbooks/{playbook_id} \
    -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"name": "Updated Name"}'
  ```

### 2.5 Delete Playbook
- [ ] Delete playbook
  ```bash
  curl -X DELETE http://localhost:8000/playbooks/{playbook_id} \
    -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
  ```
- [ ] Cascades to versions, outcomes, jobs

### 2.6 Playbook Versions
- [ ] List versions
  ```bash
  curl http://localhost:8000/playbooks/{playbook_id}/versions \
    -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
  ```
- [ ] Get specific version
- [ ] Create manual version (upload content)
  ```bash
  curl -X POST http://localhost:8000/playbooks/{playbook_id}/versions \
    -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"content": "# My Playbook\n\n- Step 1\n- Step 2"}'
  ```

---

## 3. Outcomes

### 3.1 Record Outcome
- [ ] Record successful outcome
  ```bash
  curl -X POST http://localhost:8000/playbooks/{playbook_id}/outcomes \
    -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "task_description": "Completed user onboarding",
      "outcome_status": "success",
      "reasoning_trace": "User followed all steps",
      "notes": "Took 5 minutes"
    }'
  ```
- [ ] Record failure outcome
- [ ] Record partial outcome
- [ ] Invalid status rejected

### 3.2 List Outcomes
- [ ] List outcomes for playbook
  ```bash
  curl http://localhost:8000/playbooks/{playbook_id}/outcomes \
    -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
  ```
- [ ] Filter by status (`?status=success`)
- [ ] Filter by processed state (`?processed=false`)
- [ ] Pagination works

---

## 4. Evolution

### 4.1 Trigger Evolution
- [ ] Manual evolution trigger
  ```bash
  curl -X POST http://localhost:8000/playbooks/{playbook_id}/evolve \
    -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
  ```
- [ ] Returns job ID
- [ ] Job status changes: QUEUED → RUNNING → COMPLETED

### 4.2 Evolution Status
- [ ] Get evolution status
  ```bash
  curl http://localhost:8000/playbooks/{playbook_id}/evolution-status \
    -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
  ```
- [ ] Shows pending outcomes count
- [ ] Shows outcome threshold and ready_to_evolve flag
- [ ] Shows active job if running

### 4.3 Evolution Jobs
- [ ] List evolution jobs
  ```bash
  curl http://localhost:8000/playbooks/{playbook_id}/evolutions \
    -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
  ```
- [ ] Get job details (token usage, outcomes processed)

### 4.4 Evolution Results
- [ ] New version created after successful evolution
- [ ] Outcomes marked as processed
- [ ] Token usage recorded
- [ ] Diff summary generated

### 4.5 Auto-Evolution (if enabled)
- [ ] Evolution triggers after threshold outcomes (default: 5)
- [ ] Evolution triggers after time threshold (default: 24h with 1+ outcome)

---

## 5. MCP Server

### 5.1 Health Check
- [ ] MCP health endpoint
  ```bash
  curl http://localhost:8001/health
  ```
- [ ] MCP ready endpoint
  ```bash
  curl http://localhost:8001/ready
  ```

### 5.2 MCP Tools (via Claude Desktop/Code)
- [ ] `list_playbooks` - Lists user's playbooks
- [ ] `get_playbook` - Gets playbook content by ID
- [ ] `record_outcome` - Records outcome for playbook
- [ ] `trigger_evolution` - Triggers manual evolution
- [ ] `get_evolution_status` - Gets evolution status

### 5.3 MCP Authentication
- [ ] API key authentication works
- [ ] Invalid API key rejected
- [ ] Scope enforcement (correct scopes required)

---

## 6. Usage & Metering

### 6.1 Usage Tracking
- [ ] Usage records created for LLM calls
- [ ] Token counts accurate
- [ ] Costs calculated correctly

### 6.2 Usage Endpoints
- [ ] Get usage summary
  ```bash
  curl http://localhost:8000/usage/summary \
    -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
  ```
- [ ] Get daily breakdown
- [ ] Get usage by playbook
- [ ] Get usage by operation

---

## 7. Metrics & Monitoring

### 7.1 Health Endpoints
- [ ] `/health` returns healthy
- [ ] `/ready` returns ready (with DB connection)

### 7.2 Prometheus Metrics
- [ ] `/metrics` endpoint accessible
- [ ] Key metrics present:
  - [ ] `ace_outcomes_by_status`
  - [ ] `ace_evolutions_triggered`
  - [ ] `ace_evolution_duration_seconds`
  - [ ] `ace_tokens_total`
  - [ ] `ace_evolution_jobs_active`

---

## 8. Error Handling

### 8.1 API Errors
- [ ] 400 Bad Request for invalid input
- [ ] 401 Unauthorized for missing/invalid auth
- [ ] 403 Forbidden for unauthorized access
- [ ] 404 Not Found for missing resources
- [ ] 422 Validation Error with details
- [ ] 429 Rate Limited (if applicable)
- [ ] 500 Internal Server Error (graceful)

### 8.2 Sentry Integration (if configured)
- [ ] Exceptions captured
- [ ] User context attached
- [ ] Playbook/job context attached

---

## 9. Docker Deployment

### 9.1 Container Health
- [ ] All containers start successfully
- [ ] Health checks pass
- [ ] Containers restart on failure

### 9.2 Service Communication
- [ ] API connects to PostgreSQL
- [ ] API connects to Redis
- [ ] Worker connects to Redis (task queue)
- [ ] MCP connects to PostgreSQL

### 9.3 Migrations
- [ ] Migration service completes
- [ ] Database schema correct

### 9.4 Volumes
- [ ] PostgreSQL data persists
- [ ] Redis data persists (if configured)

---

## 10. Performance & Load

### 10.1 API Performance
- [ ] Health check < 50ms
- [ ] List playbooks < 200ms
- [ ] Get playbook < 100ms

### 10.2 Load Testing
- [ ] Run load test script
  ```bash
  python scripts/load_test_mcp.py --test all --users 10 --requests 100
  ```
- [ ] Success rate > 99%
- [ ] p95 response time < 500ms

### 10.3 Concurrent Users
- [ ] Handles 10 concurrent users
- [ ] No deadlocks or race conditions

---

## 11. Security

### 11.1 Authentication
- [ ] Passwords hashed (bcrypt)
- [ ] JWT tokens expire correctly
- [ ] API keys are hashed in database

### 11.2 Authorization
- [ ] Users can only access own resources
- [ ] API key scopes enforced
- [ ] Admin endpoints protected (if any)

### 11.3 Input Validation
- [ ] SQL injection prevented
- [ ] XSS prevented (if frontend)
- [ ] Request size limits enforced

### 11.4 Rate Limiting
- [ ] Login rate limiting works
- [ ] API rate limiting works (if enabled)

---

## 12. Documentation

### 12.1 API Documentation
- [ ] `/docs` (Swagger UI) accessible (if DEBUG=true)
- [ ] `/redoc` accessible (if DEBUG=true)
- [ ] All endpoints documented

### 12.2 Written Documentation
- [ ] README.md accurate
- [ ] CLAUDE.md up to date
- [ ] API_REFERENCE.md complete
- [ ] MCP_INTEGRATION.md accurate
- [ ] ENVIRONMENT_VARIABLES.md complete
- [ ] SELF_HOSTED_DEPLOYMENT.md accurate
- [ ] TROUBLESHOOTING.md helpful
- [ ] TOKEN_ECONOMICS.md accurate

---

## Sign-Off

| Section | Tester | Date | Status |
|---------|--------|------|--------|
| Authentication | | | |
| Playbooks | | | |
| Outcomes | | | |
| Evolution | | | |
| MCP Server | | | |
| Usage & Metering | | | |
| Metrics | | | |
| Error Handling | | | |
| Docker | | | |
| Performance | | | |
| Security | | | |
| Documentation | | | |

**Overall Status:** [ ] PASS / [ ] FAIL

**Notes:**
_Record any issues discovered during testing here_

---

## Post-UAT Actions

After completing UAT:

1. [ ] Fix any issues found (create new issues in bd if needed)
2. [ ] Re-test failed items
3. [ ] Update documentation if needed
4. [ ] Close ace-platform-66 when all tests pass
5. [ ] Tag release version
6. [ ] Deploy to production
