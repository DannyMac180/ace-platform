"""Helpers for encrypting stored OAuth provider tokens."""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet

from ace_platform.config import get_settings

_ENCRYPTED_TOKEN_PREFIX = "enc:v1:"


def _get_encryption_secret() -> str:
    """Return the server-side secret material used for OAuth token storage.

    Prefer the session secret because OAuth tokens belong to the hosted auth
    surface. Fall back to the JWT secret for local/test compatibility.
    """

    settings = get_settings()
    return settings.session_secret_key or settings.jwt_secret_key


def _derive_fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


@lru_cache(maxsize=8)
def _get_fernet(secret: str) -> Fernet:
    return Fernet(_derive_fernet_key(secret))


def is_encrypted_oauth_token(value: str | None) -> bool:
    """Return whether the stored value uses the managed encryption envelope."""

    return bool(value and value.startswith(_ENCRYPTED_TOKEN_PREFIX))


def encrypt_oauth_token(value: str | None) -> str | None:
    """Encrypt a provider token for at-rest storage."""

    if not value:
        return value

    fernet = _get_fernet(_get_encryption_secret())
    ciphertext = fernet.encrypt(value.encode("utf-8")).decode("utf-8")
    return f"{_ENCRYPTED_TOKEN_PREFIX}{ciphertext}"


def decrypt_oauth_token(value: str | None) -> str | None:
    """Decrypt a stored provider token.

    Legacy plaintext rows are returned as-is so this hardening remains backward
    compatible without a data migration.
    """

    if not value:
        return value

    if not is_encrypted_oauth_token(value):
        return value

    fernet = _get_fernet(_get_encryption_secret())
    ciphertext = value[len(_ENCRYPTED_TOKEN_PREFIX) :]
    return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
