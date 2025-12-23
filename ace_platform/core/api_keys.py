"""API key management service.

This module provides functions for creating, validating, and managing API keys
for MCP authentication. Keys are hashed before storage - the full key is only
returned once at creation time.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from ace_platform.db.models import ApiKey, User

# API key format: ace_<random_32_chars>
API_KEY_PREFIX = "ace_"
API_KEY_LENGTH = 32  # Length of random part


@dataclass
class CreateApiKeyResult:
    """Result of creating an API key."""

    key_id: UUID
    full_key: str  # Only returned once at creation!
    key_prefix: str
    name: str
    scopes: list[str]


@dataclass
class ApiKeyInfo:
    """Public information about an API key (no secret)."""

    key_id: UUID
    name: str
    key_prefix: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None
    is_active: bool


def generate_api_key() -> tuple[str, str]:
    """Generate a new API key.

    Returns:
        Tuple of (full_key, prefix) where:
        - full_key: The complete API key (ace_<32_random_chars>)
        - prefix: First 8 characters for identification
    """
    random_part = secrets.token_urlsafe(API_KEY_LENGTH)[:API_KEY_LENGTH]
    full_key = f"{API_KEY_PREFIX}{random_part}"
    prefix = full_key[:8]
    return full_key, prefix


def hash_api_key(key: str) -> str:
    """Hash an API key for secure storage.

    Uses SHA-256 for fast verification while maintaining security.

    Args:
        key: The full API key to hash.

    Returns:
        Hex-encoded hash of the key.
    """
    return hashlib.sha256(key.encode()).hexdigest()


async def create_api_key_async(
    db: AsyncSession,
    user_id: UUID,
    name: str,
    scopes: list[str] | None = None,
) -> CreateApiKeyResult:
    """Create a new API key for a user.

    The full key is only returned once - it cannot be retrieved later.

    Args:
        db: Async database session.
        user_id: UUID of the user creating the key.
        name: Human-readable name for the key.
        scopes: List of permission scopes (e.g., ["read", "write"]).

    Returns:
        CreateApiKeyResult with the full key (save it now!).

    Raises:
        ValueError: If user doesn't exist.
    """
    # Verify user exists
    user = await db.get(User, user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")

    # Generate key
    full_key, prefix = generate_api_key()
    hashed_key = hash_api_key(full_key)

    # Create database record
    api_key = ApiKey(
        user_id=user_id,
        name=name,
        key_prefix=prefix,
        hashed_key=hashed_key,
        scopes=scopes or [],
    )
    db.add(api_key)
    await db.flush()

    return CreateApiKeyResult(
        key_id=api_key.id,
        full_key=full_key,
        key_prefix=prefix,
        name=name,
        scopes=scopes or [],
    )


def create_api_key_sync(
    db: Session,
    user_id: UUID,
    name: str,
    scopes: list[str] | None = None,
) -> CreateApiKeyResult:
    """Create a new API key for a user (sync version).

    The full key is only returned once - it cannot be retrieved later.

    Args:
        db: Sync database session.
        user_id: UUID of the user creating the key.
        name: Human-readable name for the key.
        scopes: List of permission scopes.

    Returns:
        CreateApiKeyResult with the full key.

    Raises:
        ValueError: If user doesn't exist.
    """
    # Verify user exists
    user = db.get(User, user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")

    # Generate key
    full_key, prefix = generate_api_key()
    hashed_key = hash_api_key(full_key)

    # Create database record
    api_key = ApiKey(
        user_id=user_id,
        name=name,
        key_prefix=prefix,
        hashed_key=hashed_key,
        scopes=scopes or [],
    )
    db.add(api_key)
    db.flush()

    return CreateApiKeyResult(
        key_id=api_key.id,
        full_key=full_key,
        key_prefix=prefix,
        name=name,
        scopes=scopes or [],
    )


async def list_api_keys_async(
    db: AsyncSession,
    user_id: UUID,
    include_revoked: bool = False,
) -> list[ApiKeyInfo]:
    """List API keys for a user.

    Note: Full keys are never returned - only the prefix for identification.

    Args:
        db: Async database session.
        user_id: UUID of the user.
        include_revoked: Whether to include revoked keys.

    Returns:
        List of ApiKeyInfo (without secret keys).
    """
    query = select(ApiKey).where(ApiKey.user_id == user_id)
    if not include_revoked:
        query = query.where(ApiKey.revoked_at.is_(None))

    result = await db.execute(query.order_by(ApiKey.created_at.desc()))
    keys = result.scalars().all()

    return [
        ApiKeyInfo(
            key_id=key.id,
            name=key.name,
            key_prefix=key.key_prefix,
            scopes=key.scopes,
            created_at=key.created_at,
            last_used_at=key.last_used_at,
            is_active=key.is_active,
        )
        for key in keys
    ]


async def authenticate_api_key_async(
    db: AsyncSession,
    api_key: str,
) -> tuple[ApiKey, User] | None:
    """Authenticate an API key and return the associated key and user.

    Also updates the last_used_at timestamp.

    Args:
        db: Async database session.
        api_key: The full API key to authenticate.

    Returns:
        Tuple of (ApiKey, User) if valid, None if invalid or revoked.
    """
    if not api_key or not api_key.startswith(API_KEY_PREFIX):
        return None

    hashed = hash_api_key(api_key)

    result = await db.execute(
        select(ApiKey).where(
            ApiKey.hashed_key == hashed,
            ApiKey.revoked_at.is_(None),
        )
    )
    key_record = result.scalar_one_or_none()

    if not key_record:
        return None

    # Update last used timestamp
    key_record.last_used_at = datetime.now(UTC)
    await db.flush()

    # Get user
    user = await db.get(User, key_record.user_id)
    if not user or not user.is_active:
        return None

    return key_record, user


def authenticate_api_key_sync(
    db: Session,
    api_key: str,
) -> tuple[ApiKey, User] | None:
    """Authenticate an API key (sync version).

    Args:
        db: Sync database session.
        api_key: The full API key to authenticate.

    Returns:
        Tuple of (ApiKey, User) if valid, None if invalid or revoked.
    """
    if not api_key or not api_key.startswith(API_KEY_PREFIX):
        return None

    hashed = hash_api_key(api_key)

    key_record = db.execute(
        select(ApiKey).where(
            ApiKey.hashed_key == hashed,
            ApiKey.revoked_at.is_(None),
        )
    ).scalar_one_or_none()

    if not key_record:
        return None

    # Update last used timestamp
    key_record.last_used_at = datetime.now(UTC)
    db.flush()

    # Get user
    user = db.get(User, key_record.user_id)
    if not user or not user.is_active:
        return None

    return key_record, user


async def revoke_api_key_async(
    db: AsyncSession,
    key_id: UUID,
    user_id: UUID,
) -> bool:
    """Revoke an API key.

    Args:
        db: Async database session.
        key_id: UUID of the key to revoke.
        user_id: UUID of the user (for authorization check).

    Returns:
        True if key was revoked, False if not found or already revoked.
    """
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.user_id == user_id,
            ApiKey.revoked_at.is_(None),
        )
    )
    key = result.scalar_one_or_none()

    if not key:
        return False

    key.revoked_at = datetime.now(UTC)
    await db.flush()
    return True


def revoke_api_key_sync(
    db: Session,
    key_id: UUID,
    user_id: UUID,
) -> bool:
    """Revoke an API key (sync version).

    Args:
        db: Sync database session.
        key_id: UUID of the key to revoke.
        user_id: UUID of the user (for authorization check).

    Returns:
        True if key was revoked, False if not found or already revoked.
    """
    key = db.execute(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.user_id == user_id,
            ApiKey.revoked_at.is_(None),
        )
    ).scalar_one_or_none()

    if not key:
        return False

    key.revoked_at = datetime.now(UTC)
    db.flush()
    return True


def check_scope(key: ApiKey, required_scope: str) -> bool:
    """Check if an API key has a required scope.

    Empty scopes list means all scopes are allowed (for backwards compatibility).

    Args:
        key: The API key to check.
        required_scope: The scope that is required.

    Returns:
        True if the key has the required scope or has no scope restrictions.
    """
    # No scopes means unrestricted access
    if not key.scopes:
        return True

    # Check for wildcard
    if "*" in key.scopes:
        return True

    # Check for exact match or prefix match (e.g., "playbooks:read" matches "playbooks:*")
    for scope in key.scopes:
        if scope == required_scope:
            return True
        # Handle wildcard suffix (e.g., "playbooks:*" matches "playbooks:read")
        if scope.endswith(":*"):
            prefix = scope[:-1]  # Remove "*"
            if required_scope.startswith(prefix):
                return True

    return False
