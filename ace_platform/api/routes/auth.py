"""Authentication routes for user login, registration, and token management.

This module provides REST API endpoints for:
- User registration (POST /auth/register) - see issue ace-platform-25
- User login (POST /auth/login) - see issue ace-platform-26
- Current user info (GET /auth/me) - see issue ace-platform-27
- Token refresh (POST /auth/refresh) - see issue ace-platform-72
- API key management (POST/GET/DELETE /auth/api-keys) - see issue ace-platform-71
- Email verification (POST /auth/send-verification-email, /auth/verify-email)
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.api.auth import AuthenticationError, RequiredUser, VerifiedPaidUser
from ace_platform.api.deps import get_db
from ace_platform.config import get_settings
from ace_platform.core.api_keys import (
    create_api_key_async,
    list_api_keys_async,
    revoke_api_key_async,
)
from ace_platform.core.audit import (
    audit_account_created,
    audit_api_key_created,
    audit_api_key_revoked,
    audit_email_verified,
    audit_login_failure,
    audit_login_success,
    audit_password_change,
    audit_password_reset_complete,
    audit_password_reset_request,
    get_client_ip,
    get_user_agent,
    is_new_ip_for_user,
)
from ace_platform.core.email import (
    PASSWORD_RESET_TOKEN_EXPIRE_HOURS,
    create_email_verification_token,
    decode_email_verification_token,
    generate_password_reset_token,
    hash_password_reset_token,
    is_email_enabled,
    send_new_login_alert,
    send_password_reset_email,
    send_verification_email,
    send_welcome_email,
)
from ace_platform.core.login_lockout import (
    check_login_lockout,
    record_login_failure,
    reset_login_lockout,
)
from ace_platform.core.rate_limit import (
    RateLimitLogin,
    RateLimitRegister,
    rate_limit_password_reset,
    rate_limit_verification_email,
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
from ace_platform.db.models import PasswordResetToken, User

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
    is_admin: bool = False
    email_verified: bool
    subscription_tier: str | None = None
    subscription_status: str = "none"
    has_used_trial: bool = False
    trial_ends_at: datetime | None = None
    has_payment_method: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str


class SetPasswordRequest(BaseModel):
    """Request body for setting a password (OAuth-only users)."""

    new_password: str = Field(..., min_length=8, description="New password (min 8 characters)")


class ChangePasswordRequest(BaseModel):
    """Request body for changing an existing password."""

    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=8, description="New password (min 8 characters)")


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
        429: {"description": "Rate limit exceeded (3 registrations per hour per IP)"},
    },
)
async def register(
    request: UserRegisterRequest,
    http_request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    _rate_limit: RateLimitRegister,
) -> TokenResponse:
    """Register a new user account.

    Creates a new user with the provided email and password, then returns
    JWT tokens for immediate authentication. A verification email is sent
    to complete the registration.

    Rate limited to 3 registrations per hour per IP address to prevent abuse.

    Note: Some features require email verification. OAuth users are
    automatically verified.
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
        email_verified=False,  # Requires verification
    )
    db.add(user)

    try:
        # Flush to get user ID and check for integrity errors
        await db.flush()
    except IntegrityError:
        # Race condition: another request registered this email between our check and flush
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Audit log the account creation
    await audit_account_created(db, user.id, http_request, method="email")

    # Single commit for both user creation and audit log
    await db.commit()

    # Send verification email (fire and forget - don't fail registration if email fails)
    if is_email_enabled():
        token = create_email_verification_token(user.id, user.email)
        verification_url = f"{get_settings().frontend_url}/verify-email?token={token}"
        await send_verification_email(user.email, verification_url)

    # Return tokens
    return create_tokens(user.id)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login with email and password",
    responses={
        401: {"description": "Invalid credentials"},
        429: {"description": "Rate limit exceeded or too many failed attempts"},
    },
)
async def login(
    request: UserLoginRequest,
    http_request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    _rate_limit: RateLimitLogin,
) -> TokenResponse:
    """Authenticate a user and return JWT tokens.

    Validates the email and password, then returns access and refresh tokens.
    Rate limited to 5 attempts per minute per IP address.

    After 5 failed login attempts, exponential backoff is applied:
    - 5 failures: 30 second lockout
    - 6 failures: 60 second lockout
    - 7 failures: 120 second lockout
    - etc. up to 1 hour maximum

    Lockout counters are tracked by both IP address and email address,
    and are reset upon successful login.
    """
    # Check for lockout before attempting authentication
    await check_login_lockout(http_request, request.email)

    user = await authenticate_user(db, request.email, request.password)
    if not user:
        # Record failed attempt for lockout tracking
        await record_login_failure(http_request, request.email)
        # Audit log the failed login
        await audit_login_failure(
            db, http_request, email=request.email, reason="Invalid credentials"
        )
        await db.commit()
        raise AuthenticationError("Invalid email or password")

    if not user.is_active:
        # Don't record as failed attempt - account exists but is disabled
        await audit_login_failure(
            db, http_request, email=request.email, user_id=user.id, reason="Account disabled"
        )
        await db.commit()
        raise AuthenticationError("Account is disabled")

    # Reset lockout counters on successful login
    await reset_login_lockout(http_request, request.email)

    # Check if this is a new IP BEFORE logging (to avoid race condition)
    client_ip = get_client_ip(http_request)
    should_send_alert = False
    if client_ip:
        is_new_ip = await is_new_ip_for_user(db, user.id, client_ip)
        # Only alert if IP is new AND user has logged in before (not first-ever login)
        if is_new_ip:
            # Check if user has any previous logins at all
            from ace_platform.core.audit import has_previous_logins

            has_logins = await has_previous_logins(db, user.id)
            should_send_alert = has_logins

    # Audit log the successful login
    await audit_login_success(db, user.id, http_request, method="password")
    await db.commit()

    # Send notification after commit if needed
    if should_send_alert:
        await send_new_login_alert(
            to_email=user.email,
            ip_address=client_ip,
            login_time=datetime.now(UTC),
            user_agent=get_user_agent(http_request),
        )

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
# Password Management (while logged in)
# =============================================================================


@router.post(
    "/set-password",
    response_model=MessageResponse,
    summary="Set a password for OAuth-only accounts",
    responses={
        401: {"description": "Not authenticated"},
        400: {"description": "Password already set"},
    },
)
async def set_password(
    body: SetPasswordRequest,
    request: Request,
    user: RequiredUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    """Set a password for an account that currently has no password."""
    if user.hashed_password is not None:
        raise HTTPException(status_code=400, detail="Password is already set")

    user.hashed_password = hash_password(body.new_password)
    await audit_password_change(db, user.id, request)
    await db.commit()

    return MessageResponse(message="Password set")


@router.post(
    "/change-password",
    response_model=MessageResponse,
    summary="Change your password",
    responses={
        401: {"description": "Not authenticated"},
        400: {"description": "Invalid current password or no password set"},
    },
)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    user: RequiredUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    """Change the user's password after verifying the current password."""
    if user.hashed_password is None:
        raise HTTPException(status_code=400, detail="No password set for this account")

    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect current password")

    user.hashed_password = hash_password(body.new_password)
    await audit_password_change(db, user.id, request)
    await db.commit()

    return MessageResponse(message="Password changed")


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
        403: {"description": "Email verification required"},
    },
)
async def create_api_key(
    request: CreateApiKeyRequest,
    http_request: Request,
    user: VerifiedPaidUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiKeyResponse:
    """Create a new API key for the authenticated user.

    Requires email verification. OAuth users are automatically verified.
    Password-registered users must verify their email first.

    **Important:** The full API key is only returned once in this response.
    Store it securely - it cannot be retrieved again.
    """
    result = await create_api_key_async(
        db=db,
        user_id=user.id,
        name=request.name,
        scopes=request.scopes,
    )

    # Audit log the API key creation
    await audit_api_key_created(
        db, user.id, http_request, key_id=result.key_id, key_name=request.name
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
    user: VerifiedPaidUser,
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
    http_request: Request,
    user: VerifiedPaidUser,
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

    # Audit log the API key revocation
    await audit_api_key_revoked(db, user.id, http_request, key_id=key_id)
    await db.commit()


# =============================================================================
# Email Verification Schemas
# =============================================================================


class VerifyEmailRequest(BaseModel):
    """Request body for email verification."""

    token: str = Field(..., description="Email verification token")


class SendVerificationEmailResponse(BaseModel):
    """Response for send verification email request."""

    message: str
    email_sent: bool


class VerifyEmailResponse(BaseModel):
    """Response for email verification."""

    message: str
    verified: bool


# =============================================================================
# Email Verification Routes
# =============================================================================

settings = get_settings()


@router.post(
    "/send-verification-email",
    response_model=SendVerificationEmailResponse,
    summary="Send or resend verification email",
    responses={
        401: {"description": "Not authenticated"},
        400: {"description": "Email already verified or email service unavailable"},
        429: {"description": "Rate limit exceeded (3 emails per hour)"},
    },
)
async def send_verification_email_endpoint(
    request: Request,
    user: RequiredUser,
) -> SendVerificationEmailResponse:
    """Send a verification email to the authenticated user.

    Use this to resend the verification email if the original was lost.
    Has no effect if email is already verified. Rate limited to 3 emails per hour.
    """
    # Apply rate limiting (3/hour per user) to prevent email spam
    await rate_limit_verification_email(request, str(user.id))

    if user.email_verified:
        return SendVerificationEmailResponse(
            message="Email is already verified",
            email_sent=False,
        )

    if not is_email_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service is not configured. Please contact support.",
        )

    # Create verification token
    token = create_email_verification_token(user.id, user.email)
    verification_url = f"{settings.frontend_url}/verify-email?token={token}"

    # Send email
    result = await send_verification_email(user.email, verification_url)

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to send verification email. Please try again later.",
        )

    return SendVerificationEmailResponse(
        message="Verification email sent. Please check your inbox.",
        email_sent=True,
    )


@router.post(
    "/verify-email",
    response_model=VerifyEmailResponse,
    summary="Verify email address",
    responses={
        400: {"description": "Invalid or expired token"},
    },
)
async def verify_email_endpoint(
    request: VerifyEmailRequest,
    http_request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> VerifyEmailResponse:
    """Verify email address using the token sent via email.

    This endpoint does not require authentication - the token itself
    proves ownership of the email.
    """
    # Decode and validate token
    result = decode_email_verification_token(request.token)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        )

    user_id, email = result

    # Get user and verify email matches
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification token",
        )

    # Check if email matches (prevents token reuse after email change)
    if user.email.lower() != email.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification token is no longer valid",
        )

    # Check if already verified
    if user.email_verified:
        return VerifyEmailResponse(
            message="Email is already verified",
            verified=True,
        )

    # Mark as verified
    user.email_verified = True

    # Audit log the email verification
    await audit_email_verified(db, user.id, http_request)
    await db.commit()

    # Send welcome email (fire and forget)
    await send_welcome_email(user.email)

    return VerifyEmailResponse(
        message="Email verified successfully",
        verified=True,
    )


# =============================================================================
# Password Reset Schemas
# =============================================================================


class ForgotPasswordRequest(BaseModel):
    """Request body for forgot password."""

    email: EmailStr = Field(..., description="Email address to send reset link to")


class ResetPasswordRequest(BaseModel):
    """Request body for password reset."""

    token: str = Field(..., description="Password reset token")
    new_password: str = Field(..., min_length=8, description="New password (min 8 characters)")


# =============================================================================
# Password Reset Routes
# =============================================================================


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    summary="Request password reset email",
    responses={
        429: {"description": "Rate limit exceeded (3 requests per hour per email)"},
    },
)
async def forgot_password(
    request: ForgotPasswordRequest,
    http_request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    """Request a password reset email.

    If the email exists in the system, a password reset link will be sent.
    For security, this endpoint always returns success even if the email
    doesn't exist (to prevent email enumeration).

    Rate limited to 3 requests per hour per email address.
    """
    # Apply rate limiting BEFORE any database lookups
    await rate_limit_password_reset(http_request, request.email)

    # Always return success message (prevents email enumeration)
    success_message = "If an account exists with this email, a password reset link has been sent."

    # Check if user exists
    user = await get_user_by_email(db, request.email)
    if not user or not user.is_active:
        # Don't reveal whether the email exists
        return MessageResponse(message=success_message)

    # Check if email service is configured
    if not is_email_enabled():
        # Log for debugging but don't expose to user
        return MessageResponse(message=success_message)

    # Invalidate any existing unused tokens for this user
    existing_tokens = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
    )
    for token_record in existing_tokens.scalars():
        token_record.used_at = datetime.now(UTC)

    # Generate new token
    token = generate_password_reset_token()
    token_hash = hash_password_reset_token(token)
    expires_at = datetime.now(UTC) + timedelta(hours=PASSWORD_RESET_TOKEN_EXPIRE_HOURS)

    # Store token
    password_reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(password_reset_token)

    # Audit log the password reset request
    await audit_password_reset_request(db, user.id, http_request)
    await db.commit()

    # Send reset email
    reset_url = f"{settings.frontend_url}/reset-password?token={token}"
    await send_password_reset_email(user.email, reset_url)

    return MessageResponse(message=success_message)


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Reset password using token",
    responses={
        400: {"description": "Invalid or expired token"},
    },
)
async def reset_password(
    request: ResetPasswordRequest,
    http_request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    """Reset password using a token from the reset email.

    The token can only be used once and expires after 1 hour.
    """
    # Hash the provided token to compare with stored hash
    token_hash = hash_password_reset_token(request.token)

    # Look up the token
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    token_record = result.scalar_one_or_none()

    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token",
        )

    # Check if token is valid (not used, not expired)
    if not token_record.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset token has expired or already been used",
        )

    # Get the user
    user = await db.get(User, token_record.user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid password reset token",
        )

    # Update password
    user.hashed_password = hash_password(request.new_password)

    # Mark token as used
    token_record.used_at = datetime.now(UTC)

    # Audit log the password reset
    await audit_password_reset_complete(db, user.id, http_request)
    await db.commit()

    return MessageResponse(message="Password has been reset successfully")
