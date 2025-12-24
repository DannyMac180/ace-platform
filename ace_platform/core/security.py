"""Security utilities for password hashing and JWT token management.

This module provides:
- Password hashing and verification using bcrypt
- JWT access and refresh token creation
- JWT token validation and decoding
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext

from ace_platform.config import get_settings

settings = get_settings()

# Password hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Token types
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


class TokenError(Exception):
    """Base exception for token-related errors."""

    pass


class TokenExpiredError(TokenError):
    """Raised when a token has expired."""

    pass


class InvalidTokenError(TokenError):
    """Raised when a token is invalid or malformed."""

    pass


# Password hashing functions


def hash_password(password: str) -> str:
    """Hash a password using bcrypt.

    Args:
        password: The plaintext password to hash.

    Returns:
        The hashed password string.

    Example:
        hashed = hash_password("my_secure_password")
        # Store hashed in database
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash.

    Args:
        plain_password: The plaintext password to verify.
        hashed_password: The hashed password from the database.

    Returns:
        True if the password matches, False otherwise.

    Example:
        if verify_password(user_input, user.hashed_password):
            # Password is correct
    """
    return pwd_context.verify(plain_password, hashed_password)


# JWT token functions


def create_access_token(
    user_id: UUID | str,
    additional_claims: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token for a user.

    Args:
        user_id: The user's ID to encode in the token.
        additional_claims: Optional additional claims to include.
        expires_delta: Optional custom expiration time. Defaults to settings.

    Returns:
        The encoded JWT access token.

    Example:
        token = create_access_token(user.id)
        # Return token to client
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.jwt_access_token_expire_minutes)

    return _create_token(
        subject=str(user_id),
        token_type=ACCESS_TOKEN_TYPE,
        expires_delta=expires_delta,
        additional_claims=additional_claims,
    )


def create_refresh_token(
    user_id: UUID | str,
    additional_claims: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT refresh token for a user.

    Refresh tokens have a longer expiration and are used to obtain
    new access tokens without re-authentication.

    Args:
        user_id: The user's ID to encode in the token.
        additional_claims: Optional additional claims to include.
        expires_delta: Optional custom expiration time. Defaults to settings.

    Returns:
        The encoded JWT refresh token.

    Example:
        refresh_token = create_refresh_token(user.id)
        # Return along with access token
    """
    if expires_delta is None:
        expires_delta = timedelta(days=settings.jwt_refresh_token_expire_days)

    return _create_token(
        subject=str(user_id),
        token_type=REFRESH_TOKEN_TYPE,
        expires_delta=expires_delta,
        additional_claims=additional_claims,
    )


def _create_token(
    subject: str,
    token_type: str,
    expires_delta: timedelta,
    additional_claims: dict[str, Any] | None = None,
) -> str:
    """Create a JWT token with the given parameters.

    Args:
        subject: The token subject (typically user ID).
        token_type: The type of token (access or refresh).
        expires_delta: Time until token expiration.
        additional_claims: Optional additional claims.

    Returns:
        The encoded JWT token.
    """
    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    payload = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": expire,
    }

    if additional_claims:
        payload.update(additional_claims)

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    """Decode and validate a JWT token.

    Args:
        token: The JWT token to decode.
        expected_type: Optional expected token type (access or refresh).
            If provided, validates that the token type matches.

    Returns:
        The decoded token payload.

    Raises:
        TokenExpiredError: If the token has expired.
        InvalidTokenError: If the token is invalid or type mismatch.

    Example:
        try:
            payload = decode_token(token, expected_type="access")
            user_id = payload["sub"]
        except TokenExpiredError:
            # Token expired, need to refresh
        except InvalidTokenError:
            # Invalid token, re-authenticate
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except ExpiredSignatureError:
        raise TokenExpiredError("Token has expired")
    except JWTError as e:
        raise InvalidTokenError(f"Invalid token: {e}")

    # Validate token type if expected
    if expected_type is not None:
        token_type = payload.get("type")
        if token_type != expected_type:
            raise InvalidTokenError(f"Expected {expected_type} token, got {token_type}")

    return payload


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate an access token.

    Convenience function that calls decode_token with type validation.

    Args:
        token: The JWT access token to decode.

    Returns:
        The decoded token payload.

    Raises:
        TokenExpiredError: If the token has expired.
        InvalidTokenError: If the token is invalid or not an access token.
    """
    return decode_token(token, expected_type=ACCESS_TOKEN_TYPE)


def decode_refresh_token(token: str) -> dict[str, Any]:
    """Decode and validate a refresh token.

    Convenience function that calls decode_token with type validation.

    Args:
        token: The JWT refresh token to decode.

    Returns:
        The decoded token payload.

    Raises:
        TokenExpiredError: If the token has expired.
        InvalidTokenError: If the token is invalid or not a refresh token.
    """
    return decode_token(token, expected_type=REFRESH_TOKEN_TYPE)


def get_token_user_id(token: str, expected_type: str | None = None) -> str:
    """Extract the user ID from a token.

    Args:
        token: The JWT token to decode.
        expected_type: Optional expected token type.

    Returns:
        The user ID from the token's subject claim.

    Raises:
        TokenExpiredError: If the token has expired.
        InvalidTokenError: If the token is invalid or missing subject.
    """
    payload = decode_token(token, expected_type=expected_type)
    user_id = payload.get("sub")
    if not user_id:
        raise InvalidTokenError("Token missing subject claim")
    return user_id
