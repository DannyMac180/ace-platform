"""Authentication routes for user login, registration, and token management.

This module provides REST API endpoints for:
- User registration (POST /auth/register) - see issue ace-platform-25
- User login (POST /auth/login) - see issue ace-platform-26
- Current user info (GET /auth/me) - see issue ace-platform-27
- Token refresh (POST /auth/refresh) - see issue ace-platform-72
- API key management (POST/GET/DELETE /auth/api-keys) - see issue ace-platform-71
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.api.auth import AuthenticationError, RequiredUser
from ace_platform.api.deps import get_db
from ace_platform.core.api_keys import (
    create_api_key_async,
    list_api_keys_async,
    revoke_api_key_async,
)
from ace_platform.core.security import (
    InvalidTokenError,
    TokenExpiredError,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from ace_platform.db.models import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


# =============================================================================
# Request/Response Schemas
# =============================================================================


class UserRegisterRequest(BaseModel):
    """Request body for user registration."""

    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(..., min_length=8, description="Password (min 8 characters)")


class UserLoginRequest(BaseModel):
    """Request body for user login."""

    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(..., description="User's password")


class TokenResponse(BaseModel):
    """Response containing access and refresh tokens."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")


class TokenRefreshRequest(BaseModel):
    """Request body for token refresh."""

    refresh_token: str = Field(..., description="JWT refresh token")


class UserResponse(BaseModel):
    """Response containing user information."""

    id: UUID
    email: str
    is_active: bool
    email_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str


# =============================================================================
# API Key Schemas
# =============================================================================


class CreateApiKeyRequest(BaseModel):
    """Request body for creating an API key."""

    name: str = Field(..., min_length=1, max_length=100, description="Name for the API key")
    scopes: list[str] = Field(
        default=[],
        description="Permission scopes (e.g., ['playbooks:read', 'outcomes:write'])",
    )


class ApiKeyResponse(BaseModel):
    """Response for API key creation (includes full key - only shown once!)."""

    id: UUID = Field(..., description="API key ID")
    name: str = Field(..., description="API key name")
    key: str = Field(..., description="Full API key (save this - shown only once!)")
    key_prefix: str = Field(..., description="Key prefix for identification")
    scopes: list[str] = Field(..., description="Permission scopes")


class ApiKeyInfo(BaseModel):
    """Response for listing API keys (no full key, only prefix)."""

    id: UUID = Field(..., description="API key ID")
    name: str = Field(..., description="API key name")
    key_prefix: str = Field(..., description="Key prefix for identification")
    scopes: list[str] = Field(..., description="Permission scopes")
    created_at: datetime = Field(..., description="When the key was created")
    last_used_at: datetime | None = Field(None, description="When the key was last used")
    is_active: bool = Field(..., description="Whether the key is active")


# =============================================================================
# Helper Functions
# =============================================================================


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Fetch a user by email address.

    Args:
        db: Database session.
        email: Email address to look up.

    Returns:
        User if found, None otherwise.
    """
    result = await db.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


# Dummy hash used for timing-safe authentication
# This prevents timing attacks that could enumerate valid emails
_DUMMY_HASH = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.PrJWC/3fQVT7eG"


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    """Authenticate a user by email and password.

    This function is timing-safe: it always performs a password hash
    verification, even when the user doesn't exist, to prevent timing
    attacks that could enumerate valid email addresses.

    Args:
        db: Database session.
        email: User's email address.
        password: User's password.

    Returns:
        User if credentials are valid, None otherwise.
    """
    user = await get_user_by_email(db, email)
    if not user:
        # Always verify against dummy hash to prevent timing attacks
        verify_password(password, _DUMMY_HASH)
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def create_tokens(user_id: UUID) -> TokenResponse:
    """Create access and refresh tokens for a user.

    Args:
        user_id: The user's ID.

    Returns:
        TokenResponse with access and refresh tokens.
    """
    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


# =============================================================================
# Routes
# =============================================================================


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    responses={
        409: {"description": "Email already registered"},
    },
)
async def register(
    request: UserRegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Register a new user account.

    Creates a new user with the provided email and password, then returns
    JWT tokens for immediate authentication.
    """
    # Check if email already exists
    existing_user = await get_user_by_email(db, request.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Create new user
    user = User(
        email=request.email.lower(),
        hashed_password=hash_password(request.password),
    )
    db.add(user)

    try:
        await db.commit()
    except IntegrityError:
        # Race condition: another request registered this email between our check and commit
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    await db.refresh(user)

    # Return tokens
    return create_tokens(user.id)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login with email and password",
    responses={
        401: {"description": "Invalid credentials"},
    },
)
async def login(
    request: UserLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Authenticate a user and return JWT tokens.

    Validates the email and password, then returns access and refresh tokens.
    """
    user = await authenticate_user(db, request.email, request.password)
    if not user:
        raise AuthenticationError("Invalid email or password")

    if not user.is_active:
        raise AuthenticationError("Account is disabled")

    return create_tokens(user.id)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
    responses={
        401: {"description": "Invalid or expired refresh token"},
    },
)
async def refresh_token(
    request: TokenRefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Refresh an access token using a refresh token.

    Takes a valid refresh token and returns new access and refresh tokens.
    """
    try:
        payload = decode_refresh_token(request.refresh_token)
    except TokenExpiredError:
        raise AuthenticationError("Refresh token has expired")
    except InvalidTokenError:
        # Use generic message to avoid leaking token parsing details
        raise AuthenticationError("Invalid refresh token")

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise AuthenticationError("Invalid token")

    # Verify user still exists and is active
    try:
        user_id = UUID(user_id_str)
    except ValueError:
        raise AuthenticationError("Invalid token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise AuthenticationError("User not found")

    if not user.is_active:
        raise AuthenticationError("Account is disabled")

    return create_tokens(user.id)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user info",
    responses={
        401: {"description": "Not authenticated"},
    },
)
async def get_current_user(user: RequiredUser) -> UserResponse:
    """Get the current authenticated user's information."""
    return UserResponse.model_validate(user)


# =============================================================================
# API Key Management Routes
# =============================================================================


@router.post(
    "/api-keys",
    response_model=ApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API key",
    responses={
        401: {"description": "Not authenticated"},
    },
)
async def create_api_key(
    request: CreateApiKeyRequest,
    user: RequiredUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiKeyResponse:
    """Create a new API key for the authenticated user.

    **Important:** The full API key is only returned once in this response.
    Store it securely - it cannot be retrieved again.
    """
    result = await create_api_key_async(
        db=db,
        user_id=user.id,
        name=request.name,
        scopes=request.scopes,
    )
    await db.commit()

    return ApiKeyResponse(
        id=result.key_id,
        name=result.name,
        key=result.full_key,
        key_prefix=result.key_prefix,
        scopes=result.scopes,
    )


@router.get(
    "/api-keys",
    response_model=list[ApiKeyInfo],
    summary="List API keys",
    responses={
        401: {"description": "Not authenticated"},
    },
)
async def list_api_keys(
    user: RequiredUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    include_revoked: bool = False,
) -> list[ApiKeyInfo]:
    """List all API keys for the authenticated user.

    By default, only active keys are returned. Set `include_revoked=true`
    to also include revoked keys.

    **Note:** Only the key prefix is shown, not the full key.
    """
    keys = await list_api_keys_async(
        db=db,
        user_id=user.id,
        include_revoked=include_revoked,
    )

    return [
        ApiKeyInfo(
            id=key.key_id,
            name=key.name,
            key_prefix=key.key_prefix,
            scopes=key.scopes,
            created_at=key.created_at,
            last_used_at=key.last_used_at,
            is_active=key.is_active,
        )
        for key in keys
    ]


@router.delete(
    "/api-keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an API key",
    responses={
        401: {"description": "Not authenticated"},
        404: {"description": "API key not found"},
    },
)
async def revoke_api_key(
    key_id: UUID,
    user: RequiredUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Revoke an API key.

    Once revoked, the key can no longer be used for authentication.
    This action cannot be undone.
    """
    revoked = await revoke_api_key_async(
        db=db,
        key_id=key_id,
        user_id=user.id,
    )

    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found or already revoked",
        )

    await db.commit()
