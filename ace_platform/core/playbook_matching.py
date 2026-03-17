"""Backward-compatible platform adapter for core playbook matching helpers."""

from __future__ import annotations

from ace_core.playbook_matching import (
    DEFAULT_EMBEDDING_MAX_CHARS,
    DEFAULT_EMBEDDING_MODEL,
    LOCAL_EMBEDDING_DIMENSIONS,
    LOCAL_EMBEDDING_MODEL,
    build_playbook_match_text,
    cosine_similarity,
    generate_local_embedding,
    keyword_overlap_score,
    parse_embedding,
    score_playbook_match,
)
from ace_core.playbook_matching import (
    generate_embedding as _generate_embedding,
)
from ace_core.playbook_matching import (
    generate_embedding_sync as _generate_embedding_sync,
)
from ace_core.playbook_matching import (
    refresh_playbook_embedding as _refresh_playbook_embedding,
)
from ace_core.playbook_matching import (
    refresh_playbook_embedding_sync as _refresh_playbook_embedding_sync,
)
from ace_platform.config import Settings, get_settings
from ace_platform.db.models import Playbook


def _resolved_settings(settings: Settings | None) -> Settings:
    return settings or get_settings()


async def generate_embedding(
    text: str,
    *,
    settings: Settings | None = None,
) -> tuple[list[float], str]:
    """Generate embedding using platform settings defaults."""
    current_settings = _resolved_settings(settings)
    return await _generate_embedding(
        text,
        openai_api_key=current_settings.openai_api_key,
        model=current_settings.playbook_embedding_model,
    )


def generate_embedding_sync(
    text: str,
    *,
    settings: Settings | None = None,
) -> tuple[list[float], str]:
    """Synchronous variant of embedding generation for platform callers."""
    current_settings = _resolved_settings(settings)
    return _generate_embedding_sync(
        text,
        openai_api_key=current_settings.openai_api_key,
        model=current_settings.playbook_embedding_model,
    )


async def refresh_playbook_embedding(
    playbook: Playbook,
    *,
    content: str | None,
    settings: Settings | None = None,
) -> None:
    """Update a playbook's stored embedding fields using platform settings."""
    current_settings = _resolved_settings(settings)
    await _refresh_playbook_embedding(
        playbook,
        content=content,
        openai_api_key=current_settings.openai_api_key,
        model=current_settings.playbook_embedding_model,
        max_chars=current_settings.playbook_embedding_max_chars,
    )


def refresh_playbook_embedding_sync(
    playbook: Playbook,
    *,
    content: str | None,
    settings: Settings | None = None,
) -> None:
    """Synchronous variant for worker code paths."""
    current_settings = _resolved_settings(settings)
    _refresh_playbook_embedding_sync(
        playbook,
        content=content,
        openai_api_key=current_settings.openai_api_key,
        model=current_settings.playbook_embedding_model,
        max_chars=current_settings.playbook_embedding_max_chars,
    )


__all__ = [
    "DEFAULT_EMBEDDING_MAX_CHARS",
    "DEFAULT_EMBEDDING_MODEL",
    "LOCAL_EMBEDDING_DIMENSIONS",
    "LOCAL_EMBEDDING_MODEL",
    "build_playbook_match_text",
    "cosine_similarity",
    "generate_embedding",
    "generate_embedding_sync",
    "generate_local_embedding",
    "keyword_overlap_score",
    "parse_embedding",
    "refresh_playbook_embedding",
    "refresh_playbook_embedding_sync",
    "score_playbook_match",
]
