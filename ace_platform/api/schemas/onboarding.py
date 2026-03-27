"""Schemas and helpers for quick-start onboarding state."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ace_platform.config import Settings

DEFAULT_QUICK_START_VIDEO_ID = "GsiZrW5QlQ4"
QuickStartOnboardingStatus = Literal["active", "minimized", "completed"]


class QuickStartOnboardingState(BaseModel):
    """Persisted quick-start onboarding state for one user."""

    model_config = ConfigDict(extra="forbid")

    status: QuickStartOnboardingStatus = "active"
    last_seen_at: datetime | None = None
    minimized_at: datetime | None = None
    completed_at: datetime | None = None


class QuickStartOnboardingConfig(BaseModel):
    """Backend-owned media/config used by the dashboard quick start."""

    video_embed_url: str
    video_url: str


class QuickStartOnboardingPayload(BaseModel):
    """Authenticated quick-start onboarding payload returned to the dashboard."""

    state: QuickStartOnboardingState
    config: QuickStartOnboardingConfig


def build_quick_start_embed_url(video_id: str) -> str:
    """Build the privacy-enhanced YouTube embed URL for the given video ID."""

    normalized_video_id = video_id.strip() or DEFAULT_QUICK_START_VIDEO_ID
    return (
        "https://www.youtube-nocookie.com/embed/"
        f"{normalized_video_id}?rel=0&modestbranding=1&playsinline=1"
    )


def build_quick_start_config(settings: Settings) -> QuickStartOnboardingConfig:
    """Resolve the backend-owned quick-start media configuration."""

    configured_embed_url = settings.quick_start_video_embed_url.strip()
    if configured_embed_url:
        embed_url = configured_embed_url
    else:
        embed_url = build_quick_start_embed_url(
            settings.quick_start_video_id or DEFAULT_QUICK_START_VIDEO_ID
        )

    return QuickStartOnboardingConfig(
        video_embed_url=embed_url,
        video_url=settings.quick_start_video_url.strip() or "/landing-hero-video.mp4",
    )


def normalize_quick_start_state(raw_state: object) -> QuickStartOnboardingState:
    """Normalize persisted onboarding state into the API contract."""

    if not isinstance(raw_state, dict):
        return QuickStartOnboardingState()

    normalized = dict(raw_state)
    status = normalized.get("status")
    if status == "dismissed":
        normalized["status"] = "minimized"
        normalized.setdefault("minimized_at", normalized.get("dismissed_at"))

    try:
        return QuickStartOnboardingState.model_validate(normalized)
    except Exception:
        return QuickStartOnboardingState()


def build_quick_start_payload(
    raw_state: object,
    settings: Settings,
) -> QuickStartOnboardingPayload:
    """Build the authenticated dashboard payload for quick-start onboarding."""

    return QuickStartOnboardingPayload(
        state=normalize_quick_start_state(raw_state),
        config=build_quick_start_config(settings),
    )
