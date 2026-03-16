"""CLI entrypoint for the Symphony runtime."""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from ace_platform.symphony.orchestrator import SymphonyOrchestrator


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Symphony issue orchestrator")
    parser.add_argument("workflow_path", nargs="?", default="WORKFLOW.md")
    args = parser.parse_args()

    workflow_path = Path(args.workflow_path)
    if not workflow_path.exists():
        parser.error(f"Workflow file not found: {workflow_path}")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    orchestrator = SymphonyOrchestrator(workflow_path.resolve())
    try:
        asyncio.run(orchestrator.run())
    except KeyboardInterrupt:
        return 0
    except Exception:
        logging.exception("symphony_startup_failed")
        return 1
    return 0
