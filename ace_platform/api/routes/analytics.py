"""First-party analytics event ingestion routes."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.api.auth import OptionalUser
from ace_platform.api.deps import get_db
from ace_platform.config import get_settings
from ace_platform.core.acquisition import (
    canonicalize_channel,
    canonicalize_source,
    parse_signup_attribution,
)
from ace_platform.core.rate_limit import RateLimitAnalyticsEvents
from ace_platform.db.models import AcquisitionEvent, AcquisitionEventType

router = APIRouter(prefix="/analytics", tags=["Analytics"])


class AnalyticsEventRequest(BaseModel):
    """Payload for first-party acquisition event ingestion."""

    event_type: AcquisitionEventType
    event_id: str | None = Field(default=None, max_length=128)
    anonymous_id: str | None = Field(default=None, max_length=128)
    source: str | None = Field(default=None, max_length=64)
    channel: str | None = Field(default=None, max_length=64)
    campaign: str | None = Field(default=None, max_length=255)
    experiment_variant: str | None = Field(default=None, max_length=100)
    attribution: dict[str, Any] | None = None
    event_data: dict[str, Any] | None = None


class AnalyticsEventResponse(BaseModel):
    """Response for analytics ingestion."""

    accepted: bool
    deduped: bool = False
    event_id: str


@router.post(
    "/events",
    response_model=AnalyticsEventResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a first-party analytics event",
)
async def ingest_analytics_event(
    payload: AnalyticsEventRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: OptionalUser,
    _rate_limit: RateLimitAnalyticsEvents,
) -> AnalyticsEventResponse:
    """Store first-party acquisition events with idempotent event IDs."""
    settings = get_settings()
    candidate_event_id = payload.event_id or str(uuid4())

    if not settings.acquisition_tracking_enabled:
        return AnalyticsEventResponse(
            accepted=False,
            deduped=False,
            event_id=candidate_event_id,
        )

    if payload.event_id:
        existing = await db.scalar(
            select(AcquisitionEvent.id).where(AcquisitionEvent.event_id == payload.event_id)
        )
        if existing is not None:
            return AnalyticsEventResponse(
                accepted=True,
                deduped=True,
                event_id=payload.event_id,
            )

    parsed_attribution = parse_signup_attribution(payload.attribution)
    source = canonicalize_source(
        payload.source or parsed_attribution.source,
        parsed_attribution.snapshot.get("referrer_host") if parsed_attribution.snapshot else None,
    )
    channel = canonicalize_channel(source, payload.channel or parsed_attribution.channel)
    campaign = payload.campaign or parsed_attribution.campaign

    event_data = dict(payload.event_data or {})
    if parsed_attribution.snapshot:
        event_data.setdefault("attribution", parsed_attribution.snapshot)

    # Keep a tiny amount of request context for attribution QA/debugging.
    event_data.setdefault("ingest_path", request.url.path)

    event = AcquisitionEvent(
        user_id=user.id if user else None,
        event_type=payload.event_type,
        event_id=candidate_event_id,
        anonymous_id=payload.anonymous_id,
        source=source,
        channel=channel,
        campaign=campaign,
        experiment_variant=payload.experiment_variant,
        event_data=event_data or None,
    )
    db.add(event)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        if payload.event_id:
            existing = await db.scalar(
                select(AcquisitionEvent.id).where(AcquisitionEvent.event_id == payload.event_id)
            )
            if existing is not None:
                return AnalyticsEventResponse(
                    accepted=True,
                    deduped=True,
                    event_id=payload.event_id,
                )

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to ingest analytics event",
        )

    return AnalyticsEventResponse(accepted=True, deduped=False, event_id=candidate_event_id)
