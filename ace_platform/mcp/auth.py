"""MCP Authentication utilities.

This module provides authentication helpers for MCP tools. Since MCP tools
return strings rather than HTTP responses, this module provides a structured
way to handle authentication that can be used consistently across all tools.

Usage:
    @mcp.tool()
    async def my_tool(api_key: str, ctx: Context) -> str:
        auth = await authenticate_mcp_request(get_db(ctx), api_key, "playbooks:read")
        if auth.error:
            return auth.error_message

        # Use auth.user and auth.api_key
        return f"Hello {auth.user.email}"
"""

from dataclasses import dataclass
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.core.api_keys import authenticate_api_key_async, check_scope
from ace_platform.db.models import ApiKey, User


class MCPAuthErrorCode(str, Enum):
    """Error codes for MCP authentication failures.

    These codes map to HTTP status codes for consistency:
    - INVALID_KEY, REVOKED_KEY, INACTIVE_USER -> 401 Unauthorized
    - INSUFFICIENT_SCOPE -> 403 Forbidden
    """

    INVALID_KEY = "invalid_key"  # 401
    REVOKED_KEY = "revoked_key"  # 401
    INACTIVE_USER = "inactive_user"  # 401
    INSUFFICIENT_SCOPE = "insufficient_scope"  # 403
    MISSING_KEY = "missing_key"  # 401


# Mapping of error codes to HTTP-like status codes (for logging/metrics)
ERROR_CODE_TO_STATUS = {
    MCPAuthErrorCode.INVALID_KEY: 401,
    MCPAuthErrorCode.REVOKED_KEY: 401,
    MCPAuthErrorCode.INACTIVE_USER: 401,
    MCPAuthErrorCode.INSUFFICIENT_SCOPE: 403,
    MCPAuthErrorCode.MISSING_KEY: 401,
}


@dataclass
class MCPAuthResult:
    """Result of MCP authentication.

    Attributes:
        success: Whether authentication succeeded.
        user: The authenticated user (if success).
        api_key: The API key record (if success).
        error_code: Error code (if failed).
        error_message: Human-readable error message (if failed).
    """

    success: bool
    user: User | None = None
    api_key: ApiKey | None = None
    error_code: MCPAuthErrorCode | None = None
    error_message: str | None = None

    @property
    def error(self) -> bool:
        """Check if authentication failed."""
        return not self.success

    @property
    def http_status(self) -> int:
        """Get the HTTP status code equivalent for this result."""
        if self.success:
            return 200
        return ERROR_CODE_TO_STATUS.get(self.error_code, 401)

    def has_scope(self, required_scope: str) -> bool:
        """Check if the authenticated key has a required scope."""
        if not self.api_key:
            return False
        return check_scope(self.api_key, required_scope)


def auth_success(user: User, api_key: ApiKey) -> MCPAuthResult:
    """Create a successful authentication result."""
    return MCPAuthResult(success=True, user=user, api_key=api_key)


def auth_error(code: MCPAuthErrorCode, message: str) -> MCPAuthResult:
    """Create a failed authentication result."""
    return MCPAuthResult(
        success=False,
        error_code=code,
        error_message=f"Error: {message}",
    )


async def authenticate_mcp_request(
    db: AsyncSession,
    api_key: str | None,
    required_scope: str | None = None,
) -> MCPAuthResult:
    """Authenticate an MCP request.

    This function performs full authentication and optional scope checking
    for MCP tool requests.

    Args:
        db: Database session.
        api_key: The API key from the request.
        required_scope: Optional scope that must be present.

    Returns:
        MCPAuthResult with success status, user/key on success,
        or error details on failure.

    Example:
        auth = await authenticate_mcp_request(db, api_key, "playbooks:read")
        if auth.error:
            return auth.error_message
        # Continue with auth.user, auth.api_key
    """
    # Check for missing key
    if not api_key:
        return auth_error(
            MCPAuthErrorCode.MISSING_KEY,
            "API key required. Include X-API-Key header or pass api_key parameter.",
        )

    # Authenticate the key
    result = await authenticate_api_key_async(db, api_key)
    if not result:
        return auth_error(
            MCPAuthErrorCode.INVALID_KEY,
            "Invalid or revoked API key.",
        )

    api_key_record, user = result

    # Check if user is active
    if not user.is_active:
        return auth_error(
            MCPAuthErrorCode.INACTIVE_USER,
            "User account is inactive.",
        )

    # Check scope if required
    if required_scope and not check_scope(api_key_record, required_scope):
        return auth_error(
            MCPAuthErrorCode.INSUFFICIENT_SCOPE,
            f"API key lacks required scope: {required_scope}",
        )

    return auth_success(user, api_key_record)


async def require_playbook_access(
    db: AsyncSession,
    api_key: str | None,
    playbook_id,
    required_scope: str,
) -> MCPAuthResult:
    """Authenticate and verify access to a specific playbook.

    This is a convenience function that combines authentication,
    scope checking, and playbook ownership verification.

    Args:
        db: Database session.
        api_key: The API key from the request.
        playbook_id: UUID of the playbook to access.
        required_scope: The scope required for this operation.

    Returns:
        MCPAuthResult. Check auth.error before using auth.user/api_key.
    """
    from uuid import UUID

    from ace_platform.db.models import Playbook

    # First authenticate
    auth = await authenticate_mcp_request(db, api_key, required_scope)
    if auth.error:
        return auth

    # Validate playbook ID format
    try:
        if isinstance(playbook_id, str):
            playbook_id = UUID(playbook_id)
    except ValueError:
        return auth_error(
            MCPAuthErrorCode.INVALID_KEY,  # Reuse for bad input
            f"Invalid playbook ID format: {playbook_id}",
        )

    # Get playbook and verify ownership
    playbook = await db.get(Playbook, playbook_id)
    if not playbook:
        return auth_error(
            MCPAuthErrorCode.INVALID_KEY,
            f"Playbook {playbook_id} not found.",
        )

    if playbook.user_id != auth.user.id:
        return auth_error(
            MCPAuthErrorCode.INSUFFICIENT_SCOPE,
            "Access denied - playbook belongs to another user.",
        )

    return auth
