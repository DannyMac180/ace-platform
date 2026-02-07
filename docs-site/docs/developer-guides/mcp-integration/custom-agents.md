---
sidebar_position: 4
---

# Building Custom Agents

Integrate ACE into your own AI agents using the MCP protocol.

## Overview

ACE exposes its capabilities through MCP tools, which gives you a standardized
interface for listing playbooks, fetching content, and recording outcomes.

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

    headers = {"X-API-Key": api_key}

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
      "X-API-Key": apiKey,
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

## Agent Architecture Pattern

Here's a recommended pattern for ACE-integrated agents using MCP tools:

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
    def __init__(self, mcp_session, llm_client):
        self.mcp = mcp_session
        self.llm = llm_client

    async def execute_task(
        self,
        task: str,
        playbook_id: str
    ) -> TaskResult:
        # 1. Fetch playbook via MCP tool
        playbook_result = await self.mcp.call_tool(
            "get_playbook",
            {"playbook_id": playbook_id}
        )
        playbook_content = playbook_result.content

        # 2. Execute task with LLM using playbook as instructions
        prompt = f\"\"\"
        Follow these instructions:

        {playbook_content}

        Task: {task}
        \"\"\"

        try:
            # Your LLM execution here
            result = await self.llm.generate(prompt)

            # 3. Record outcome via MCP tool
            await self.mcp.call_tool(
                "record_outcome",
                {
                    "playbook_id": playbook_id,
                    "task_description": task,
                    "outcome": "success",
                    "notes": f"Generated output of {len(result)} characters",
                    "reasoning_trace": result[:1000],
                },
            )

            return TaskResult(success=True, output=result)

        except Exception as e:
            # Record failure
            await self.mcp.call_tool(
                "record_outcome",
                {
                    "playbook_id": playbook_id,
                    "task_description": task,
                    "outcome": "failure",
                    "notes": str(e),
                },
            )

            return TaskResult(success=False, output="", error=str(e))
```

## Error Handling

Handle common MCP tool failures with retries and backoff:

```python
from time import sleep

async def call_tool_with_retry(session, name, args, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await session.call_tool(name, args)
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            sleep(2 ** attempt)
```

## Caching Playbooks

For high-throughput agents, cache playbooks:

```python
from datetime import datetime, timedelta

class PlaybookCache:
    def __init__(self, cache_ttl: int = 300):
        self._cache = {}
        self._cache_ttl = timedelta(seconds=cache_ttl)

    async def get_playbook(self, session, playbook_id: str, version: int | None = None):
        cache_key = f"{playbook_id}:{version}"

        if cache_key in self._cache:
            cached, timestamp = self._cache[cache_key]
            if datetime.now() - timestamp < self._cache_ttl:
                return cached

        result = await session.call_tool(
            "get_playbook",
            {"playbook_id": playbook_id, "version": version},
        )
        self._cache[cache_key] = (result, datetime.now())
        return result
```

## Monitoring and Observability

Add logging and metrics:

```python
import logging
import time

logger = logging.getLogger(__name__)

async def timed_call(session, tool_name, args):
    start = time.time()
    try:
        result = await session.call_tool(tool_name, args)
        logger.info(
            "mcp_tool_call",
            extra={
                "tool": tool_name,
                "duration_ms": (time.time() - start) * 1000,
            },
        )
        return result
    except Exception as e:
        logger.error(
            "mcp_tool_call_failed",
            extra={
                "tool": tool_name,
                "error": str(e),
            },
        )
        raise
```

## Next Steps

- [Recording effective outcomes](/docs/developer-guides/recording-outcomes)
- [Understanding evolution](/docs/user-guides/understanding-evolution)
