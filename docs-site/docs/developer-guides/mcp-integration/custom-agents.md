---
sidebar_position: 4
---

# Building Custom Agents

Integrate ACE into your own AI agents using the MCP protocol or REST API.

## Overview

You can connect to ACE in two ways:

1. **MCP Protocol** - Standard protocol for AI tool integration
2. **REST API** - Direct HTTP requests

Choose MCP for:
- Building MCP-compatible agents
- Standardized tool interfaces
- Framework integrations

Choose REST API for:
- Simple integrations
- Non-MCP environments
- Maximum control

## MCP Integration

### Python with mcp-python

Install the MCP Python SDK:

```bash
pip install mcp
```

Connect to ACE:

```python
import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client

async def main():
    api_key = "your_api_key"
    url = "https://aceagent.io/mcp/sse"

    headers = {"Authorization": f"Bearer {api_key}"}

    async with sse_client(url, headers=headers) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize connection
            await session.initialize()

            # List available tools
            tools = await session.list_tools()
            print(f"Available tools: {[t.name for t in tools.tools]}")

            # Get a playbook
            result = await session.call_tool(
                "get_playbook",
                {"playbook_id": "abc-123"}
            )
            print(f"Playbook content: {result.content}")

            # Record an outcome
            await session.call_tool(
                "record_outcome",
                {
                    "playbook_id": "abc-123",
                    "task_description": "Reviewed PR #456",
                    "outcome": "success",
                    "notes": "Caught security issue"
                }
            )

asyncio.run(main())
```

### TypeScript with @modelcontextprotocol/sdk

Install the MCP TypeScript SDK:

```bash
npm install @modelcontextprotocol/sdk
```

Connect to ACE:

```typescript
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { SSEClientTransport } from "@modelcontextprotocol/sdk/client/sse.js";

async function main() {
  const apiKey = process.env.ACE_API_KEY;
  const url = "https://aceagent.io/mcp/sse";

  const transport = new SSEClientTransport(new URL(url), {
    headers: {
      Authorization: `Bearer ${apiKey}`,
    },
  });

  const client = new Client({
    name: "my-agent",
    version: "1.0.0",
  });

  await client.connect(transport);

  // List tools
  const tools = await client.listTools();
  console.log("Tools:", tools.tools.map((t) => t.name));

  // Get playbook
  const playbook = await client.callTool({
    name: "get_playbook",
    arguments: { playbook_id: "abc-123" },
  });
  console.log("Playbook:", playbook.content);

  // Record outcome
  await client.callTool({
    name: "record_outcome",
    arguments: {
      playbook_id: "abc-123",
      task_description: "Processed user request",
      outcome: "success",
    },
  });

  await client.close();
}

main();
```

## REST API Integration

### Python with requests

```python
import requests

class AceClient:
    def __init__(self, api_key: str, base_url: str = "https://aceagent.io"):
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def list_playbooks(self):
        """List all playbooks."""
        response = requests.get(
            f"{self.base_url}/api/playbooks",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def get_playbook(self, playbook_id: str, version: int = None):
        """Get playbook content."""
        url = f"{self.base_url}/api/playbooks/{playbook_id}"
        params = {"version": version} if version else {}

        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()

    def record_outcome(
        self,
        playbook_id: str,
        task_description: str,
        outcome: str,
        notes: str = None,
        reasoning_trace: str = None
    ):
        """Record a task outcome."""
        data = {
            "playbook_id": playbook_id,
            "task_description": task_description,
            "outcome": outcome
        }
        if notes:
            data["notes"] = notes
        if reasoning_trace:
            data["reasoning_trace"] = reasoning_trace

        response = requests.post(
            f"{self.base_url}/api/outcomes",
            headers=self.headers,
            json=data
        )
        response.raise_for_status()
        return response.json()

    def trigger_evolution(self, playbook_id: str):
        """Trigger playbook evolution."""
        response = requests.post(
            f"{self.base_url}/api/playbooks/{playbook_id}/evolve",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def get_evolution_status(self, job_id: str):
        """Check evolution job status."""
        response = requests.get(
            f"{self.base_url}/api/evolution/{job_id}/status",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()


# Usage
client = AceClient(api_key="your_api_key")

# Get playbook
playbook = client.get_playbook("abc-123")
print(playbook["content"])

# Use playbook for task...

# Record outcome
client.record_outcome(
    playbook_id="abc-123",
    task_description="Analyzed dataset",
    outcome="success",
    notes="Found 3 key insights"
)
```

### TypeScript with fetch

```typescript
class AceClient {
  private baseUrl: string;
  private headers: HeadersInit;

  constructor(apiKey: string, baseUrl = "https://aceagent.io") {
    this.baseUrl = baseUrl;
    this.headers = {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    };
  }

  async listPlaybooks() {
    const response = await fetch(`${this.baseUrl}/api/playbooks`, {
      headers: this.headers,
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async getPlaybook(playbookId: string, version?: number) {
    const url = new URL(`${this.baseUrl}/api/playbooks/${playbookId}`);
    if (version) url.searchParams.set("version", String(version));

    const response = await fetch(url.toString(), {
      headers: this.headers,
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async recordOutcome(params: {
    playbookId: string;
    taskDescription: string;
    outcome: "success" | "partial" | "failure";
    notes?: string;
    reasoningTrace?: string;
  }) {
    const response = await fetch(`${this.baseUrl}/api/outcomes`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify({
        playbook_id: params.playbookId,
        task_description: params.taskDescription,
        outcome: params.outcome,
        notes: params.notes,
        reasoning_trace: params.reasoningTrace,
      }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async triggerEvolution(playbookId: string) {
    const response = await fetch(
      `${this.baseUrl}/api/playbooks/${playbookId}/evolve`,
      {
        method: "POST",
        headers: this.headers,
      }
    );
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }
}

// Usage
const client = new AceClient(process.env.ACE_API_KEY!);

const playbook = await client.getPlaybook("abc-123");
console.log(playbook.content);

await client.recordOutcome({
  playbookId: "abc-123",
  taskDescription: "Generated report",
  outcome: "success",
  notes: "Report was well-structured",
});
```

## Agent Architecture Pattern

Here's a recommended pattern for ACE-integrated agents:

```python
from typing import Optional
from dataclasses import dataclass

@dataclass
class TaskResult:
    success: bool
    output: str
    reasoning: Optional[str] = None
    error: Optional[str] = None

class AceAgent:
    def __init__(self, ace_client: AceClient, llm_client):
        self.ace = ace_client
        self.llm = llm_client

    async def execute_task(
        self,
        task: str,
        playbook_id: str
    ) -> TaskResult:
        # 1. Fetch playbook
        playbook = self.ace.get_playbook(playbook_id)

        # 2. Execute task with LLM using playbook as instructions
        prompt = f"""
        Follow these instructions:

        {playbook['content']}

        Task: {task}
        """

        try:
            # Your LLM execution here
            result = await self.llm.generate(prompt)

            # 3. Record outcome
            self.ace.record_outcome(
                playbook_id=playbook_id,
                task_description=task,
                outcome="success",
                notes=f"Generated output of {len(result)} characters",
                reasoning_trace=result[:1000]  # First 1000 chars
            )

            return TaskResult(success=True, output=result)

        except Exception as e:
            # Record failure
            self.ace.record_outcome(
                playbook_id=playbook_id,
                task_description=task,
                outcome="failure",
                notes=str(e)
            )

            return TaskResult(success=False, output="", error=str(e))
```

## Error Handling

Handle common error scenarios:

```python
import requests
from time import sleep

class AceClientWithRetry(AceClient):
    def _request(self, method, url, **kwargs):
        max_retries = 3

        for attempt in range(max_retries):
            try:
                response = requests.request(
                    method,
                    url,
                    headers=self.headers,
                    **kwargs
                )

                if response.status_code == 429:
                    # Rate limited
                    retry_after = int(response.headers.get("Retry-After", 60))
                    sleep(retry_after)
                    continue

                response.raise_for_status()
                return response.json()

            except requests.exceptions.ConnectionError:
                if attempt < max_retries - 1:
                    sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401:
                    raise AuthenticationError("Invalid API key")
                elif e.response.status_code == 403:
                    raise PermissionError("Insufficient scopes")
                elif e.response.status_code == 404:
                    raise NotFoundError("Resource not found")
                raise
```

## Caching Playbooks

For high-throughput agents, cache playbooks:

```python
from functools import lru_cache
from datetime import datetime, timedelta

class CachedAceClient(AceClient):
    def __init__(self, *args, cache_ttl: int = 300, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache = {}
        self._cache_ttl = timedelta(seconds=cache_ttl)

    def get_playbook(self, playbook_id: str, version: int = None):
        cache_key = f"{playbook_id}:{version}"

        if cache_key in self._cache:
            cached, timestamp = self._cache[cache_key]
            if datetime.now() - timestamp < self._cache_ttl:
                return cached

        result = super().get_playbook(playbook_id, version)
        self._cache[cache_key] = (result, datetime.now())
        return result
```

## Monitoring and Observability

Add logging and metrics:

```python
import logging
import time

logger = logging.getLogger(__name__)

class ObservableAceClient(AceClient):
    def get_playbook(self, playbook_id: str, version: int = None):
        start = time.time()
        try:
            result = super().get_playbook(playbook_id, version)
            logger.info(
                "get_playbook",
                extra={
                    "playbook_id": playbook_id,
                    "version": version,
                    "duration_ms": (time.time() - start) * 1000
                }
            )
            return result
        except Exception as e:
            logger.error(
                "get_playbook_failed",
                extra={
                    "playbook_id": playbook_id,
                    "error": str(e)
                }
            )
            raise

    def record_outcome(self, *args, **kwargs):
        start = time.time()
        result = super().record_outcome(*args, **kwargs)
        logger.info(
            "outcome_recorded",
            extra={
                "playbook_id": kwargs.get("playbook_id"),
                "outcome": kwargs.get("outcome"),
                "duration_ms": (time.time() - start) * 1000
            }
        )
        return result
```

## Next Steps

- [API reference](/docs/api-reference/overview)
- [Recording effective outcomes](/docs/developer-guides/recording-outcomes)
- [Understanding evolution](/docs/user-guides/understanding-evolution)
