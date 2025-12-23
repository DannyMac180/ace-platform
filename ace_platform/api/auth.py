"""Authentication dependencies for FastAPI and MCP.

This module provides authentication middleware and dependencies for:
- API key authentication (for MCP and API routes)
- Scope-based authorization
- Proper HTTP error responses (401/403)

Usage in FastAPI routes:
    @app.get("/playbooks")
    async def list_playbooks(auth: AuthContext = Depends(require_auth)):
        return {"user_id": str(auth.user.id)}

    @app.post("/playbooks/{id}/evolve")
    async def evolve_playbook(
        id: UUID,
        auth: AuthContext = Depends(require_scope("evolution:write")),
    ):
        ...
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.core.api_keys import authenticate_api_key_async, check_scope
from ace_platform.db.models import ApiKey, User

from .deps import get_db

# Header name for API key authentication
API_KEY_HEADER = "X-API-Key"
AUTHORIZATION_HEADER = "Authorization"
BEARER_PREFIX = "Bearer "


class AuthenticationError(HTTPException):
    """Raised when authentication fails (401)."""

    def __init__(self, detail: str = "Invalid or missing API key"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class AuthorizationError(HTTPException):
    """Raised when authorization fails (403)."""

    def __init__(self, detail: str = "Insufficient permissions"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )


@dataclass
class AuthContext:
    """Authentication context containing the authenticated user and API key."""

    user: User
    api_key: ApiKey

    @property
    def user_id(self):
        """Get the authenticated user's ID."""
        return self.user.id

    @property
    def scopes(self) -> list[str]:
        """Get the API key's scopes."""
        return self.api_key.scopes

    def has_scope(self, required_scope: str) -> bool:
        """Check if the API key has a required scope."""
        return check_scope(self.api_key, required_scope)


def extract_api_key(
    x_api_key: str | None = Header(None, alias=API_KEY_HEADER),
    authorization: str | None = Header(None, alias=AUTHORIZATION_HEADER),
) -> str | None:
    """Extract API key from request headers.

    Supports two formats:
    - X-API-Key header (preferred for API keys)
    - Authorization: Bearer <key> header

    Args:
        x_api_key: Value from X-API-Key header.
        authorization: Value from Authorization header.

    Returns:
        The API key if found, None otherwise.
    """
    # Prefer X-API-Key header
    if x_api_key:
        return x_api_key

    # Fall back to Authorization header
    if authorization and authorization.startswith(BEARER_PREFIX):
        return authorization[len(BEARER_PREFIX) :]

    return None


async def get_optional_auth(
    db: Annotated[AsyncSession, Depends(get_db)],
    api_key: Annotated[str | None, Depends(extract_api_key)],
) -> AuthContext | None:
    """Get authentication context if API key is provided.

    This dependency does not require authentication - it returns None
    if no API key is provided. Use `require_auth` for mandatory auth.

    Args:
        db: Database session.
        api_key: API key from headers.

    Returns:
        AuthContext if authenticated, None if no key provided.

    Raises:
        AuthenticationError: If key is provided but invalid.
    """
    if not api_key:
        return None

    result = await authenticate_api_key_async(db, api_key)
    if not result:
        raise AuthenticationError("Invalid or revoked API key")

    api_key_record, user = result
    return AuthContext(user=user, api_key=api_key_record)


async def require_auth(
    auth: Annotated[AuthContext | None, Depends(get_optional_auth)],
) -> AuthContext:
    """Require authentication for a route.

    Use this dependency to protect routes that require authentication.

    Args:
        auth: Optional auth context from get_optional_auth.

    Returns:
        AuthContext for the authenticated user.

    Raises:
        AuthenticationError: If no valid API key is provided.
    """
    if not auth:
        raise AuthenticationError("API key required")
    return auth


def require_scope(required_scope: str):
    """Create a dependency that requires a specific scope.

    Use this factory to create dependencies for routes that require
    specific permissions.

    Args:
        required_scope: The scope required to access the route.

    Returns:
        A FastAPI dependency function.

    Usage:
        @app.post("/evolve")
        async def evolve(auth: AuthContext = Depends(require_scope("evolution:write"))):
            ...
    """

    async def scope_checker(
        auth: Annotated[AuthContext, Depends(require_auth)],
    ) -> AuthContext:
        """Check that the authenticated user has the required scope."""
        if not auth.has_scope(required_scope):
            raise AuthorizationError(f"API key lacks required scope: {required_scope}")
        return auth

    return scope_checker


def require_any_scope(*required_scopes: str):
    """Create a dependency that requires any of the specified scopes.

    Args:
        *required_scopes: Scopes where at least one must be present.

    Returns:
        A FastAPI dependency function.

    Usage:
        @app.get("/playbooks")
        async def list_playbooks(
            auth: AuthContext = Depends(require_any_scope("playbooks:read", "playbooks:*"))
        ):
            ...
    """

    async def scope_checker(
        auth: Annotated[AuthContext, Depends(require_auth)],
    ) -> AuthContext:
        """Check that the authenticated user has at least one required scope."""
        for scope in required_scopes:
            if auth.has_scope(scope):
                return auth

        scopes_str = ", ".join(required_scopes)
        raise AuthorizationError(f"API key requires one of these scopes: {scopes_str}")

    return scope_checker


# Type aliases for cleaner dependency injection
OptionalAuth = Annotated[AuthContext | None, Depends(get_optional_auth)]
RequiredAuth = Annotated[AuthContext, Depends(require_auth)]
