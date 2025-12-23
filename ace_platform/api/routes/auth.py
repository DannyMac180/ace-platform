"""Authentication routes for user login, registration, and token management.

This module provides REST API endpoints for:
- User registration (POST /auth/register) - see issue ace-platform-25
- User login (POST /auth/login) - see issue ace-platform-26
- Current user info (GET /auth/me) - see issue ace-platform-27
- Token refresh (POST /auth/refresh) - see issue ace-platform-72
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.api.auth import AuthenticationError, RequiredUser
from ace_platform.api.deps import get_db
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


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    """Authenticate a user by email and password.

    Args:
        db: Database session.
        email: User's email address.
        password: User's password.

    Returns:
        User if credentials are valid, None otherwise.
    """
    user = await get_user_by_email(db, email)
    if not user:
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
    await db.commit()
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
    except InvalidTokenError as e:
        raise AuthenticationError(str(e))

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
