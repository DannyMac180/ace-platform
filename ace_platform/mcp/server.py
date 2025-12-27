"""MCP Server for ACE Platform.

This module provides the MCP server entry point that exposes playbook
management tools to LLM clients (like Claude). It uses FastMCP for
simplified tool registration and supports SSE/stdio transports.

Configuration is loaded from environment variables:
- MCP_SERVER_HOST: Server bind host (default: 0.0.0.0)
- MCP_SERVER_PORT: Server port (default: 8001)
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from mcp.server.fastmcp import Context, FastMCP
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.config import get_settings
from ace_platform.core.api_keys import authenticate_api_key_async
from ace_platform.core.rate_limit import RATE_LIMITS, RateLimiter
from ace_platform.core.validation import validate_outcome_inputs
from ace_platform.db.models import Outcome, OutcomeStatus, Playbook
from ace_platform.db.session import AsyncSessionLocal, close_async_db

settings = get_settings()


@dataclass
class MCPContext:
    """Application context available during MCP requests."""

    db: AsyncSession


@asynccontextmanager
async def mcp_lifespan(server: FastMCP) -> AsyncIterator[MCPContext]:
    """Manage MCP server lifecycle.

    Initializes database connection on startup and cleans up on shutdown.
    """
    # Startup: create a session for the lifespan
    async with AsyncSessionLocal() as db:
        try:
            yield MCPContext(db=db)
        finally:
            pass

    # Shutdown: close database connections
    await close_async_db()


# Create the MCP server instance
mcp = FastMCP(
    name="ACE Platform",
    lifespan=mcp_lifespan,
)


# Helper to get database session from context
def get_db(ctx: Context) -> AsyncSession:
    """Get database session from MCP context."""
    return ctx.request_context.lifespan_context.db


@mcp.tool()
async def get_playbook(
    playbook_id: Annotated[str, "UUID of the playbook to retrieve"],
    api_key: Annotated[str, "API key for authentication"],
    ctx: Context,
    version: Annotated[int | None, "Specific version number to retrieve (default: current)"] = None,
    section: Annotated[str | None, "Filter to a specific section by heading"] = None,
) -> str:
    """Get a playbook's content by ID.

    Returns the playbook name, description, and version content.
    Optionally retrieve a specific version or filter to a section.
    Requires a valid API key with 'playbooks:read' scope.

    Args:
        playbook_id: UUID of the playbook to retrieve.
        api_key: API key for authentication.
        version: Specific version number (default: current version).
        section: Filter content to section matching this heading.

    Returns:
        Playbook content as structured markdown text.
    """
    from ace_platform.db.models import PlaybookVersion

    db = get_db(ctx)

    # Authenticate
    auth_result = await authenticate_api_key_async(db, api_key)
    if not auth_result:
        return "Error: Invalid or revoked API key"

    api_key_record, user = auth_result

    # Check scope
    from ace_platform.core.api_keys import check_scope

    if not check_scope(api_key_record, "playbooks:read"):
        return "Error: API key lacks 'playbooks:read' scope"

    try:
        pb_uuid = UUID(playbook_id)
    except ValueError:
        return f"Error: Invalid playbook ID format: {playbook_id}"

    # Get playbook
    playbook = await db.get(Playbook, pb_uuid)
    if not playbook:
        return f"Error: Playbook {playbook_id} not found"

    # Verify ownership
    if playbook.user_id != user.id:
        return "Error: Access denied - playbook belongs to another user"

    # Get requested version
    content = ""
    version_info = ""

    if version is not None:
        # Get specific version by version_number
        result = await db.execute(
            select(PlaybookVersion).where(
                PlaybookVersion.playbook_id == pb_uuid,
                PlaybookVersion.version_number == version,
            )
        )
        playbook_version = result.scalar_one_or_none()
        if not playbook_version:
            return f"Error: Version {version} not found for playbook {playbook_id}"
        content = playbook_version.content
        version_info = f" (v{version})"
    else:
        # Get current version
        if playbook.current_version_id:
            await db.refresh(playbook, ["current_version"])
            if playbook.current_version:
                content = playbook.current_version.content
                version_info = f" (v{playbook.current_version.version_number})"

    # Filter by section if requested
    if section and content:
        content = _extract_section(content, section)
        if not content:
            return f"Error: Section '{section}' not found in playbook"

    return f"""# {playbook.name}{version_info}

{playbook.description or "No description"}

---

{content or "No content yet - add outcomes to evolve the playbook."}
"""


def _extract_section(content: str, section_name: str) -> str:
    """Extract a specific section from markdown content.

    Finds a section by its heading (any level) and returns all content
    until the next heading of the same or higher level.

    Args:
        content: Full markdown content.
        section_name: Section heading to find (case-insensitive).

    Returns:
        Section content including the heading, or empty string if not found.
    """
    lines = content.split("\n")
    result_lines = []
    in_section = False
    section_level = 0

    section_name_lower = section_name.lower().strip()

    for line in lines:
        # Check if this is a heading
        if line.startswith("#"):
            # Count heading level
            level = len(line) - len(line.lstrip("#"))
            heading_text = line.lstrip("#").strip().lower()

            if in_section:
                # Check if we've hit another heading at same or higher level
                if level <= section_level:
                    break  # End of section
            elif heading_text == section_name_lower or section_name_lower in heading_text:
                # Found our section
                in_section = True
                section_level = level

        if in_section:
            result_lines.append(line)

    return "\n".join(result_lines).strip()


@mcp.tool()
async def list_playbooks(
    api_key: Annotated[str, "API key for authentication"],
    ctx: Context,
) -> str:
    """List all playbooks for the authenticated user.

    Returns a list of playbook names and IDs.
    Requires a valid API key with 'playbooks:read' scope.
    """
    db = get_db(ctx)

    # Authenticate
    auth_result = await authenticate_api_key_async(db, api_key)
    if not auth_result:
        return "Error: Invalid or revoked API key"

    api_key_record, user = auth_result

    # Check scope
    from ace_platform.core.api_keys import check_scope

    if not check_scope(api_key_record, "playbooks:read"):
        return "Error: API key lacks 'playbooks:read' scope"

    # Query user's playbooks
    result = await db.execute(
        select(Playbook).where(Playbook.user_id == user.id).order_by(Playbook.created_at.desc())
    )
    playbooks = result.scalars().all()

    if not playbooks:
        return "No playbooks found. Create one in the dashboard first."

    lines = ["# Your Playbooks\n"]
    for pb in playbooks:
        lines.append(f"- **{pb.name}** (`{pb.id}`)")
        if pb.description:
            lines.append(f"  {pb.description[:100]}...")

    return "\n".join(lines)


@mcp.tool()
async def record_outcome(
    playbook_id: Annotated[str, "UUID of the playbook this outcome is for"],
    task_description: Annotated[str, "Description of the task that was attempted"],
    outcome: Annotated[str, "Outcome status: 'success', 'failure', or 'partial'"],
    api_key: Annotated[str, "API key for authentication"],
    notes: Annotated[str | None, "Optional notes about the outcome"] = None,
    reasoning_trace: Annotated[str | None, "Optional reasoning trace/log"] = None,
    ctx: Context = None,
) -> str:
    """Record a task outcome for playbook evolution.

    After recording enough outcomes, the playbook will automatically evolve
    to incorporate lessons learned. Requires 'outcomes:write' scope.

    Size limits:
    - task_description: 10KB max
    - notes: 2KB max
    - reasoning_trace: 10KB max
    """
    # Validate input sizes
    validation_error = validate_outcome_inputs(task_description, notes, reasoning_trace)
    if validation_error:
        return f"Error: {validation_error}"

    db = get_db(ctx)

    # Authenticate
    auth_result = await authenticate_api_key_async(db, api_key)
    if not auth_result:
        return "Error: Invalid or revoked API key"

    api_key_record, user = auth_result

    # Check scope
    from ace_platform.core.api_keys import check_scope

    if not check_scope(api_key_record, "outcomes:write"):
        return "Error: API key lacks 'outcomes:write' scope"

    try:
        pb_uuid = UUID(playbook_id)
    except ValueError:
        return f"Error: Invalid playbook ID format: {playbook_id}"

    # Validate outcome status
    try:
        outcome_status = OutcomeStatus(outcome.lower())
    except ValueError:
        return f"Error: Invalid outcome status '{outcome}'. Use 'success', 'failure', or 'partial'."

    # Get playbook and verify ownership
    playbook = await db.get(Playbook, pb_uuid)
    if not playbook:
        return f"Error: Playbook {playbook_id} not found"

    if playbook.user_id != user.id:
        return "Error: Access denied - playbook belongs to another user"

    # Create outcome record
    new_outcome = Outcome(
        playbook_id=pb_uuid,
        task_description=task_description,
        outcome_status=outcome_status,
        notes=notes,
        reasoning_trace=reasoning_trace,
    )
    db.add(new_outcome)
    await db.commit()

    return f"Outcome recorded successfully (ID: {new_outcome.id}). Status: {outcome_status.value}"


@mcp.tool()
async def get_evolution_status(
    job_id: Annotated[str, "UUID of the evolution job to check"],
    api_key: Annotated[str, "API key for authentication"],
    ctx: Context,
) -> str:
    """Get the status of an evolution job.

    Returns the job status, progress, timing, and any error information.
    Requires a valid API key with 'evolution:read' scope.

    Use this to poll for job completion after triggering evolution.

    Args:
        job_id: UUID of the evolution job to check.
        api_key: API key for authentication.

    Returns:
        Job status information as structured text.
    """
    from ace_platform.db.models import EvolutionJob

    db = get_db(ctx)

    # Authenticate
    auth_result = await authenticate_api_key_async(db, api_key)
    if not auth_result:
        return "Error: Invalid or revoked API key"

    api_key_record, user = auth_result

    # Check scope
    from ace_platform.core.api_keys import check_scope

    if not check_scope(api_key_record, "evolution:read"):
        return "Error: API key lacks 'evolution:read' scope"

    try:
        job_uuid = UUID(job_id)
    except ValueError:
        return f"Error: Invalid job ID format: {job_id}"

    # Get evolution job
    job = await db.get(EvolutionJob, job_uuid)
    if not job:
        return f"Error: Evolution job {job_id} not found"

    # Get the associated playbook to verify ownership
    playbook = await db.get(Playbook, job.playbook_id)
    if not playbook or playbook.user_id != user.id:
        return "Error: Access denied - job belongs to another user"

    # Format timestamps
    started = job.started_at.isoformat() if job.started_at else "Not started"
    completed = job.completed_at.isoformat() if job.completed_at else "Not completed"

    # Build response
    lines = [
        "# Evolution Job Status",
        "",
        f"**Job ID:** {job.id}",
        f"**Status:** {job.status.value}",
        f"**Playbook:** {playbook.name} (`{job.playbook_id}`)",
        f"**Outcomes Processed:** {job.outcomes_processed}",
        "",
        "## Timing",
        f"- **Created:** {job.created_at.isoformat()}",
        f"- **Started:** {started}",
        f"- **Completed:** {completed}",
    ]

    # Add error message if present
    if job.error_message:
        lines.extend(
            [
                "",
                "## Error",
                "```",
                f"{job.error_message}",
                "```",
            ]
        )

    # Add version info if available
    if job.from_version_id or job.to_version_id:
        lines.extend(["", "## Versions"])
        if job.from_version_id:
            lines.append(f"- **From Version:** {job.from_version_id}")
        if job.to_version_id:
            lines.append(f"- **To Version:** {job.to_version_id}")

    return "\n".join(lines)


@mcp.tool()
async def trigger_evolution(
    playbook_id: Annotated[str, "UUID of the playbook to evolve"],
    api_key: Annotated[str, "API key for authentication"],
    ctx: Context,
) -> str:
    """Manually trigger playbook evolution.

    This queues an evolution job that will process unprocessed outcomes
    and generate an improved playbook version. Requires 'evolution:write' scope.

    Note: Evolution happens automatically based on thresholds, but you can
    trigger it manually if needed.
    """
    db = get_db(ctx)

    # Authenticate
    auth_result = await authenticate_api_key_async(db, api_key)
    if not auth_result:
        return "Error: Invalid or revoked API key"

    api_key_record, user = auth_result

    # Check scope
    from ace_platform.core.api_keys import check_scope

    if not check_scope(api_key_record, "evolution:write"):
        return "Error: API key lacks 'evolution:write' scope"

    try:
        pb_uuid = UUID(playbook_id)
    except ValueError:
        return f"Error: Invalid playbook ID format: {playbook_id}"

    # Get playbook and verify ownership
    playbook = await db.get(Playbook, pb_uuid)
    if not playbook:
        return f"Error: Playbook {playbook_id} not found"

    if playbook.user_id != user.id:
        return "Error: Access denied - playbook belongs to another user"

    # Check rate limit (10/hour per playbook)
    limiter = RateLimiter()
    try:
        config = RATE_LIMITS["evolution"]
        rate_result = await limiter.is_allowed(
            "evolution",
            playbook_id,
            limit=config["limit"],
            window_seconds=config["window_seconds"],
        )
        if not rate_result.allowed:
            return f"Error: Rate limit exceeded. Evolution can be triggered at most {config['limit']} times per hour. Try again later."
    except Exception:
        # If Redis unavailable, allow the request
        pass

    # Trigger evolution
    from ace_platform.core.evolution_jobs import trigger_evolution_async

    try:
        result = await trigger_evolution_async(db, pb_uuid)
        await db.commit()

        if result.is_new:
            return f"Evolution job queued (Job ID: {result.job_id}). Check back later for results."
        else:
            return f"Evolution already in progress (Job ID: {result.job_id}, Status: {result.status.value})."
    except ValueError as e:
        return f"Error: {e}"


def run_server(transport: str = "stdio") -> None:
    """Run the MCP server.

    Args:
        transport: Transport to use ('stdio' or 'sse').
                   Use 'stdio' for local development with Claude Desktop.
                   Use 'sse' for web-based clients.
    """
    if transport == "sse":
        mcp.run(
            transport="sse",
            host=settings.mcp_server_host,
            port=settings.mcp_server_port,
        )
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    import sys

    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    run_server(transport)
