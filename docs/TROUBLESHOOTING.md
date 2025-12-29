# Troubleshooting Guide

This guide covers common issues and their solutions when running the ACE Platform.

## Table of Contents

- [Quick Diagnostics](#quick-diagnostics)
- [API Server Issues](#api-server-issues)
- [MCP Server Issues](#mcp-server-issues)
- [Worker Issues](#worker-issues)
- [Database Issues](#database-issues)
- [Redis Issues](#redis-issues)
- [Authentication Issues](#authentication-issues)
- [Evolution Issues](#evolution-issues)
- [Docker Issues](#docker-issues)
- [Performance Issues](#performance-issues)

---

## Quick Diagnostics

Run these commands first to check system health:

```bash
# Check all services are running
docker compose ps

# Check API health
curl http://localhost:8000/health
curl http://localhost:8000/ready

# Check MCP health
curl http://localhost:8001/health

# Check database connection
docker compose exec postgres psql -U postgres -c "SELECT 1"

# Check Redis connection
docker compose exec redis redis-cli ping

# View recent logs
docker compose logs --tail=50
```

---

## API Server Issues

### API returns 500 Internal Server Error

**Symptoms:**
- All or most API endpoints return 500 errors
- Error message: "An unexpected error occurred"

**Diagnosis:**
```bash
docker compose logs api --tail=100
```

**Common Causes & Solutions:**

1. **Database connection failed**
   ```bash
   # Check database is running
   docker compose ps postgres

   # Test connection
   docker compose exec postgres pg_isready

   # Restart if needed
   docker compose restart postgres api
   ```

2. **Missing environment variables**
   ```bash
   # Check required vars are set
   docker compose config | grep -E "(DATABASE_URL|REDIS_URL|OPENAI_API_KEY)"
   ```

3. **Migration not run**
   ```bash
   # Run migrations
   docker compose run --rm migrate
   ```

### API returns 401 Unauthorized

**Symptoms:**
- "Invalid or missing API key" error
- "Token has expired" error

**Solutions:**

1. **Expired JWT token**
   - Get a new access token using refresh token
   - Re-login to get new tokens

2. **Invalid API key**
   ```bash
   # List your API keys (via API)
   curl -X GET http://localhost:8000/auth/api-keys \
     -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
   ```

3. **Missing Authorization header**
   - Ensure header format is: `Authorization: Bearer <token>`
   - Or for API keys: `X-API-Key: <key>`

### API returns 422 Validation Error

**Symptoms:**
- "Request validation failed" error
- Details about which fields are invalid

**Solutions:**
- Check request body matches expected schema
- Ensure UUIDs are valid format
- Check enum values are valid (e.g., "success", "failure", "partial" for outcomes)

### API is slow

**Diagnosis:**
```bash
# Check response times
curl -w "@-" -o /dev/null -s http://localhost:8000/health <<'EOF'
     time_total:  %{time_total}s\n
EOF

# Check database query times
docker compose logs api | grep -i "slow"
```

**Solutions:**
1. Check database indexes exist (run migrations)
2. Check Redis is running for caching
3. Scale API workers: `docker compose up -d --scale api=2`

---

## MCP Server Issues

### MCP tools not appearing in Claude

**Symptoms:**
- Tools don't show up in Claude Desktop/Code
- "No tools available" message

**Diagnosis:**
```bash
# Check MCP server is running
curl http://localhost:8001/health

# Check server logs
docker compose logs mcp --tail=50
```

**Solutions:**

1. **Configuration not loaded**
   - Restart Claude Desktop/Code after config changes
   - Check config file path is correct

2. **Wrong transport**
   - Local: use `stdio` transport with `python -m ace_platform.mcp.server stdio`
   - Remote: use `sse` transport

3. **Environment variables missing**
   ```json
   {
     "mcpServers": {
       "ace-platform": {
         "command": "python",
         "args": ["-m", "ace_platform.mcp.server", "stdio"],
         "env": {
           "DATABASE_URL": "postgresql://...",
           "REDIS_URL": "redis://..."
         }
       }
     }
   }
   ```

### MCP authentication errors

**Symptoms:**
- "Invalid or revoked API key" error
- Tools fail with authentication error

**Solutions:**

1. **Check API key is valid**
   ```bash
   # Test API key via REST API
   curl -X GET http://localhost:8000/playbooks \
     -H "X-API-Key: YOUR_API_KEY"
   ```

2. **Check API key has required scopes**
   - `playbooks:read` for get_playbook, list_playbooks
   - `outcomes:write` for record_outcome
   - `evolution:read` for get_evolution_status
   - `evolution:write` for trigger_evolution

3. **API key may be revoked**
   - Create a new API key via the dashboard or API

---

## Worker Issues

### Evolution jobs stuck in QUEUED

**Symptoms:**
- Jobs remain in QUEUED status
- No new playbook versions created

**Diagnosis:**
```bash
# Check worker is running
docker compose ps worker

# Check worker logs
docker compose logs worker --tail=100

# Check Redis connection
docker compose exec redis redis-cli ping
```

**Solutions:**

1. **Worker not running**
   ```bash
   docker compose up -d worker
   ```

2. **Redis connection failed**
   ```bash
   # Check Redis URL
   echo $REDIS_URL

   # Restart Redis
   docker compose restart redis worker
   ```

3. **Worker crashed**
   ```bash
   # Check for errors
   docker compose logs worker | grep -i error

   # Restart worker
   docker compose restart worker
   ```

### Evolution jobs failing

**Symptoms:**
- Jobs move to FAILED status
- Error message in job record

**Diagnosis:**
```bash
# Check worker logs for errors
docker compose logs worker | grep -i "error\|exception\|failed"
```

**Common Causes:**

1. **OpenAI API error**
   - Check `OPENAI_API_KEY` is valid
   - Check OpenAI API status: https://status.openai.com
   - Rate limiting: wait and retry

2. **Playbook too large**
   - Check `EVOLUTION_PLAYBOOK_TOKEN_BUDGET` setting
   - Default is 80,000 tokens

3. **No outcomes to process**
   - Need at least 1 unprocessed outcome

### Beat scheduler not running

**Symptoms:**
- Auto-evolution not triggering
- Periodic tasks not running

**Solutions:**
```bash
# Check beat is running
docker compose ps beat

# Start beat
docker compose up -d beat

# Check beat logs
docker compose logs beat --tail=50
```

---

## Database Issues

### Connection refused

**Symptoms:**
- "connection refused" or "could not connect to server"

**Solutions:**
```bash
# Check postgres is running
docker compose ps postgres

# Start postgres
docker compose up -d postgres

# Wait for healthy status
docker compose ps postgres  # Should show "healthy"
```

### Database doesn't exist

**Symptoms:**
- "database 'ace_platform' does not exist"

**Solutions:**
```bash
# Create database manually
docker compose exec postgres createdb -U postgres ace_platform

# Run migrations
docker compose run --rm migrate
```

### Migration errors

**Symptoms:**
- "relation does not exist" errors
- Schema mismatch errors

**Solutions:**
```bash
# Check current migration state
docker compose run --rm migrate alembic current

# Run pending migrations
docker compose run --rm migrate alembic upgrade head

# If migrations are corrupt, reset (DANGER: destroys data)
docker compose down -v
docker compose up -d postgres
docker compose run --rm migrate
```

### Slow queries

**Diagnosis:**
```bash
# Enable query logging temporarily
docker compose exec postgres psql -U postgres -c "SET log_statement = 'all';"

# Check for missing indexes
docker compose exec postgres psql -U postgres ace_platform -c "
  SELECT schemaname, tablename, indexname
  FROM pg_indexes
  WHERE schemaname = 'public';
"
```

---

## Redis Issues

### Connection refused

**Solutions:**
```bash
# Check Redis is running
docker compose ps redis

# Start Redis
docker compose up -d redis

# Test connection
docker compose exec redis redis-cli ping
```

### Out of memory

**Symptoms:**
- "OOM command not allowed" errors

**Solutions:**
```bash
# Check memory usage
docker compose exec redis redis-cli info memory

# Clear expired keys
docker compose exec redis redis-cli --scan --pattern '*' | head -100

# Increase memory limit in docker-compose.override.yml
```

---

## Authentication Issues

### Login fails with correct credentials

**Diagnosis:**
```bash
# Check for lockout
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password"}'
```

**Solutions:**

1. **Account locked due to failed attempts**
   - Wait 15-30 minutes for lockout to expire
   - Check Redis for lockout keys

2. **Password hash mismatch**
   - Reset password via API

3. **User not active**
   - Check `is_active` flag in database

### JWT token issues

**Symptoms:**
- "Token has expired"
- "Invalid token"

**Solutions:**

1. **Token expired**
   - Use refresh token to get new access token
   - Check `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` setting

2. **Invalid signature**
   - Ensure `JWT_SECRET_KEY` is consistent across restarts
   - Don't change secret key in production

### Rate limiting

**Symptoms:**
- 429 Too Many Requests
- "Rate limit exceeded"

**Solutions:**
- Wait for rate limit window to reset (usually 1 minute)
- Check `RATE_LIMIT_*` settings
- Use exponential backoff in clients

---

## Evolution Issues

### No evolution triggered

**Symptoms:**
- Outcomes recorded but no evolution
- Manual trigger doesn't start

**Diagnosis:**
```bash
# Check for pending outcomes
curl http://localhost:8000/playbooks/{playbook_id}/outcomes \
  -H "Authorization: Bearer TOKEN"

# Check evolution thresholds
echo "Outcome threshold: $EVOLUTION_OUTCOME_THRESHOLD"
echo "Time threshold: $EVOLUTION_TIME_THRESHOLD_HOURS hours"
```

**Solutions:**

1. **Not enough outcomes**
   - Default requires 5 unprocessed outcomes
   - Or 24 hours since last evolution with at least 1 outcome

2. **Worker not running**
   - See [Worker Issues](#worker-issues)

3. **Evolution already in progress**
   - Check for QUEUED or RUNNING jobs

### Evolution produces no changes

**Symptoms:**
- Evolution completes but no new version
- "No changes made" message

**Causes:**
- Outcomes may not require playbook changes
- LLM determined current playbook is optimal

---

## Docker Issues

### Containers won't start

**Diagnosis:**
```bash
# Check for errors
docker compose logs --tail=50

# Check container status
docker compose ps -a
```

**Solutions:**

1. **Port already in use**
   ```bash
   # Find what's using the port
   lsof -i :8000

   # Use different port
   API_PORT=8080 docker compose up -d
   ```

2. **Image build failed**
   ```bash
   # Rebuild images
   docker compose build --no-cache
   ```

3. **Volume permissions**
   ```bash
   # Reset volumes
   docker compose down -v
   docker compose up -d
   ```

### Out of disk space

**Solutions:**
```bash
# Clean up Docker
docker system prune -a --volumes

# Remove old images
docker image prune -a
```

---

## Performance Issues

### High memory usage

**Diagnosis:**
```bash
docker stats
```

**Solutions:**
1. Reduce worker concurrency
2. Add resource limits in docker-compose.override.yml
3. Scale horizontally instead of vertically

### High CPU usage

**Diagnosis:**
```bash
docker stats
docker compose logs worker | grep -i "processing"
```

**Solutions:**
1. Check for runaway evolution jobs
2. Reduce concurrent workers
3. Check for infinite loops in playbooks

### Slow response times

See [API is slow](#api-is-slow) section.

---

## Getting Help

If you can't resolve an issue:

1. **Check logs**: `docker compose logs --tail=200`
2. **Enable debug mode**: Set `DEBUG=true` in `.env`
3. **Check Sentry**: If configured, check for captured errors
4. **File an issue**: https://github.com/DannyMac180/ace-platform/issues

Include in your issue:
- Error messages
- Steps to reproduce
- Environment (Docker version, OS)
- Relevant logs
