# ACE Platform Quick Start Guide

Get up and running with ACE Platform in 5 minutes.

## What is ACE Platform?

ACE Platform is a "Playbooks as a Service" platform that helps LLM agents learn and improve over time. Your agents can:

1. **Follow playbooks** - Structured guidelines for completing tasks
2. **Report outcomes** - Record what worked and what didn't
3. **Evolve automatically** - Playbooks improve based on real-world results

## Quick Start

### 1. Create an Account

```bash
curl -X POST https://your-ace-platform.fly.dev/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "your-password"}'
```

Save the returned `access_token` - you'll need it for API calls.

### 2. Create Your First Playbook

```bash
curl -X POST https://your-ace-platform.fly.dev/playbooks \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Code Review Playbook",
    "description": "Guidelines for reviewing code",
    "initial_content": "# Code Review Guidelines\n\n- Check for bugs and logic errors\n- Verify error handling\n- Ensure code is readable\n- Look for security issues"
  }'
```

Note the returned `id` - this is your playbook ID.

### 3. Generate an API Key (for MCP)

```bash
curl -X POST https://your-ace-platform.fly.dev/auth/api-keys \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Agent",
    "scopes": ["playbooks:read", "outcomes:write", "evolution:read", "evolution:write"]
  }'
```

Save the returned API key securely.

### 4. Connect Your LLM Agent

Configure your LLM agent (Claude Desktop, Claude Code, etc.) to use the MCP server. See [MCP Integration Guide](MCP_INTEGRATION.md) for detailed setup.

**Quick Claude Desktop Setup:**

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

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

### 5. Use the Playbook

Your agent can now:

```
Agent: Let me get my code review playbook
[Calls get_playbook with playbook_id and api_key]

Agent: I reviewed the code and found 2 issues. Recording outcome...
[Calls record_outcome with task_description="Reviewed PR #123", outcome="success"]
```

### 6. Watch It Evolve

After recording several outcomes, your playbook will automatically evolve to incorporate lessons learned. You can also trigger evolution manually:

```bash
curl -X POST https://your-ace-platform.fly.dev/playbooks/YOUR_PLAYBOOK_ID/evolve \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

---

## Key Concepts

### Playbooks

Playbooks are structured guidelines that help your agents complete tasks consistently. They contain:

- **Name & Description** - What the playbook is for
- **Content** - Markdown-formatted guidelines, rules, and best practices
- **Versions** - History of how the playbook has evolved

### Outcomes

Outcomes are records of how a task went when following a playbook:

- **Success** - Task completed successfully
- **Failure** - Task failed
- **Partial** - Task partially completed

Include notes about what worked or didn't to help the evolution process.

### Evolution

Evolution is the automatic improvement of playbooks based on outcomes:

1. Agent records outcomes while using a playbook
2. After enough outcomes accumulate, evolution triggers
3. The ACE system analyzes outcomes and updates the playbook
4. A new version is created with improved guidelines

---

## Common Workflows

### Workflow 1: Coding Agent

```
1. Create playbook: "Software Development Best Practices"
2. Agent follows playbook when writing code
3. Agent records outcome: "Implemented feature X - success"
4. After 5+ outcomes, playbook evolves with learned patterns
```

### Workflow 2: Research Agent

```
1. Create playbook: "Research Methodology"
2. Agent follows playbook when researching topics
3. Agent records outcome: "Research on topic Y - partial, missed key source"
4. Playbook evolves to include "Check academic databases"
```

### Workflow 3: Customer Support

```
1. Create playbook: "Customer Issue Resolution"
2. Agent follows playbook when handling tickets
3. Agent records outcomes with resolution notes
4. Playbook evolves with better troubleshooting steps
```

---

## API Quick Reference

| Action | Method | Endpoint |
|--------|--------|----------|
| Register | POST | `/auth/register` |
| Login | POST | `/auth/login` |
| List playbooks | GET | `/playbooks` |
| Create playbook | POST | `/playbooks` |
| Get playbook | GET | `/playbooks/{id}` |
| Record outcome | POST | `/playbooks/{id}/outcomes` |
| Trigger evolution | POST | `/playbooks/{id}/evolve` |
| Get usage | GET | `/usage/summary` |

See [API Reference](API_REFERENCE.md) for complete documentation.

---

## MCP Tools Quick Reference

| Tool | Description |
|------|-------------|
| `list_playbooks` | List your playbooks |
| `get_playbook` | Get playbook content |
| `record_outcome` | Record a task outcome |
| `trigger_evolution` | Manually trigger evolution |
| `get_evolution_status` | Check evolution job status |

See [MCP Integration Guide](MCP_INTEGRATION.md) for setup and usage.

---

## Next Steps

1. **Create domain-specific playbooks** for your use cases
2. **Integrate with your agents** using the MCP server
3. **Monitor usage** via the `/usage` endpoints
4. **Upgrade your plan** if you need more capacity

## Getting Help

- **API Docs:** `/docs` (Swagger UI)
- **Issues:** [GitHub Issues](https://github.com/your-org/ace-platform/issues)
- **Documentation:** See `docs/` directory

---

## Local Development

Want to run ACE Platform locally? See [CLAUDE.md](../CLAUDE.md) for development setup instructions.

```bash
# Quick local setup
git clone https://github.com/your-org/ace-platform.git
cd ace-platform
cp .env.example .env
# Edit .env with your API keys
podman compose up -d postgres redis
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn ace_platform.api.main:app --reload
```
