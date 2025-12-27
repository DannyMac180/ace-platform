"""Playbook CRUD API routes.

This module provides REST API endpoints for playbook management:
- GET /playbooks - List user's playbooks with pagination
- POST /playbooks - Create a new playbook
- GET /playbooks/{id} - Get a specific playbook
- PUT /playbooks/{id} - Update a playbook
- DELETE /playbooks/{id} - Delete a playbook
- GET /playbooks/{id}/versions - List version history for a playbook
- GET /playbooks/{id}/versions/{version_number} - Get specific version content
- GET /playbooks/{id}/outcomes - List outcomes for a playbook
- POST /playbooks/{id}/outcomes - Create a new outcome for a playbook
- GET /playbooks/{id}/evolutions - List evolution history for a playbook
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ace_platform.api.auth import (
    SubscriptionError,
    get_user_tier,
    require_active_subscription,
    require_user,
)
from ace_platform.api.deps import get_db
from ace_platform.core.limits import get_tier_limits
from ace_platform.core.rate_limit import rate_limit_outcome
from ace_platform.core.validation import (
    MAX_NOTES_SIZE,
    MAX_PLAYBOOK_CONTENT_SIZE,
    MAX_PLAYBOOK_DESCRIPTION_SIZE,
    MAX_PLAYBOOK_NAME_SIZE,
    MAX_REASONING_TRACE_SIZE,
    MAX_TASK_DESCRIPTION_SIZE,
)
from ace_platform.db.models import (
    EvolutionJob,
    EvolutionJobStatus,
    Outcome,
    OutcomeStatus,
    Playbook,
    PlaybookSource,
    PlaybookStatus,
    PlaybookVersion,
    User,
)

router = APIRouter(prefix="/playbooks", tags=["playbooks"])


# Pydantic Schemas


class PlaybookCreate(BaseModel):
    """Request schema for creating a playbook."""

    name: str = Field(
        ..., min_length=1, max_length=MAX_PLAYBOOK_NAME_SIZE, description="Playbook name"
    )
    description: str | None = Field(
        None, max_length=MAX_PLAYBOOK_DESCRIPTION_SIZE, description="Playbook description"
    )
    initial_content: str | None = Field(
        None,
        max_length=MAX_PLAYBOOK_CONTENT_SIZE,
        description="Initial playbook content (markdown, max 100KB)",
    )


class PlaybookUpdate(BaseModel):
    """Request schema for updating a playbook."""

    name: str | None = Field(
        None, min_length=1, max_length=MAX_PLAYBOOK_NAME_SIZE, description="Playbook name"
    )
    description: str | None = Field(
        None, max_length=MAX_PLAYBOOK_DESCRIPTION_SIZE, description="Playbook description"
    )
    status: PlaybookStatus | None = Field(None, description="Playbook status")


class PlaybookVersionResponse(BaseModel):
    """Response schema for playbook version (basic, used in playbook response)."""

    id: UUID
    version_number: int
    content: str
    bullet_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class PlaybookVersionDetailResponse(BaseModel):
    """Response schema for playbook version with full details."""

    id: UUID
    version_number: int
    content: str
    bullet_count: int
    diff_summary: str | None = None
    created_by_job_id: UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedVersionResponse(BaseModel):
    """Paginated response for version list."""

    items: list[PlaybookVersionDetailResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class PlaybookResponse(BaseModel):
    """Response schema for a playbook."""

    id: UUID
    name: str
    description: str | None
    status: PlaybookStatus
    source: PlaybookSource
    created_at: datetime
    updated_at: datetime
    current_version: PlaybookVersionResponse | None = None

    model_config = {"from_attributes": True}


class PlaybookListItem(BaseModel):
    """Response schema for playbook in list view."""

    id: UUID
    name: str
    description: str | None
    status: PlaybookStatus
    source: PlaybookSource
    created_at: datetime
    updated_at: datetime
    version_count: int = 0
    outcome_count: int = 0

    model_config = {"from_attributes": True}


class PaginatedPlaybookResponse(BaseModel):
    """Paginated response for playbook list."""

    items: list[PlaybookListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class OutcomeResponse(BaseModel):
    """Response schema for an outcome."""

    id: UUID
    task_description: str
    outcome_status: OutcomeStatus
    notes: str | None
    reasoning_trace: str | None
    created_at: datetime
    processed_at: datetime | None
    evolution_job_id: UUID | None

    model_config = {"from_attributes": True}


class OutcomeCreate(BaseModel):
    """Request schema for creating an outcome."""

    task_description: str = Field(
        ...,
        min_length=1,
        max_length=MAX_TASK_DESCRIPTION_SIZE,
        description="Description of the task",
    )
    outcome: OutcomeStatus = Field(..., description="Outcome status: success, failure, or partial")
    reasoning_trace: str | None = Field(
        None, max_length=MAX_REASONING_TRACE_SIZE, description="Optional reasoning trace (max 10KB)"
    )
    notes: str | None = Field(
        None, max_length=MAX_NOTES_SIZE, description="Optional notes (max 2KB)"
    )


class OutcomeCreateResponse(BaseModel):
    """Response schema for outcome creation."""

    outcome_id: UUID = Field(..., description="ID of the created outcome")
    status: str = Field(default="recorded", description="Status of the outcome creation")
    pending_outcomes: int = Field(
        ..., description="Number of unprocessed outcomes for this playbook"
    )


class PaginatedOutcomeResponse(BaseModel):
    """Paginated response for outcome list."""

    items: list[OutcomeResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class EvolutionJobResponse(BaseModel):
    """Response schema for an evolution job."""

    id: UUID
    status: EvolutionJobStatus
    from_version_id: UUID | None
    to_version_id: UUID | None
    outcomes_processed: int
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class PaginatedEvolutionJobResponse(BaseModel):
    """Paginated response for evolution job list."""

    items: list[EvolutionJobResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# Dependency type aliases
DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(require_user)]
SubscribedUser = Annotated[User, Depends(require_active_subscription)]


# Route handlers


@router.get("", response_model=PaginatedPlaybookResponse)
async def list_playbooks(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status_filter: PlaybookStatus | None = Query(None, description="Filter by status"),
) -> PaginatedPlaybookResponse:
    """List playbooks for the authenticated user.

    Returns paginated list of playbooks with version and outcome counts.
    """
    # Build base query for user's playbooks
    base_query = select(Playbook).where(Playbook.user_id == current_user.id)

    if status_filter:
        base_query = base_query.where(Playbook.status == status_filter)

    # Get total count
    count_query = select(func.count()).select_from(base_query.subquery())
    total = await db.scalar(count_query) or 0

    # Get paginated results with counts
    offset = (page - 1) * page_size
    query = (
        base_query.options(selectinload(Playbook.versions), selectinload(Playbook.outcomes))
        .order_by(Playbook.updated_at.desc())
        .offset(offset)
        .limit(page_size)
    )

    result = await db.execute(query)
    playbooks = result.scalars().all()

    # Build response items with counts
    items = [
        PlaybookListItem(
            id=pb.id,
            name=pb.name,
            description=pb.description,
            status=pb.status,
            source=pb.source,
            created_at=pb.created_at,
            updated_at=pb.updated_at,
            version_count=len(pb.versions),
            outcome_count=len(pb.outcomes),
        )
        for pb in playbooks
    ]

    total_pages = (total + page_size - 1) // page_size

    return PaginatedPlaybookResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("", response_model=PlaybookResponse, status_code=status.HTTP_201_CREATED)
async def create_playbook(
    db: DbSession,
    current_user: SubscribedUser,
    data: PlaybookCreate,
) -> PlaybookResponse:
    """Create a new playbook.

    Optionally include initial content to create the first version.
    Requires active subscription and enforces max_playbooks limit.
    """
    # Check max_playbooks limit for user's tier
    user_tier = get_user_tier(current_user)
    limits = get_tier_limits(user_tier)

    if limits.max_playbooks is not None:
        # Count existing playbooks
        count_query = select(func.count()).select_from(
            select(Playbook).where(Playbook.user_id == current_user.id).subquery()
        )
        current_count = await db.scalar(count_query) or 0

        if current_count >= limits.max_playbooks:
            raise SubscriptionError(
                f"You have reached the maximum number of playbooks ({limits.max_playbooks}) "
                f"for your {user_tier.value} subscription. Please upgrade to create more playbooks.",
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
            )

    # Create playbook
    playbook = Playbook(
        user_id=current_user.id,
        name=data.name,
        description=data.description,
        status=PlaybookStatus.ACTIVE,
        source=PlaybookSource.USER_CREATED,
    )
    db.add(playbook)
    await db.flush()

    # Create initial version if content provided
    if data.initial_content:
        bullet_count = data.initial_content.count("\n- ") + data.initial_content.count("\n* ")
        if data.initial_content.startswith("- ") or data.initial_content.startswith("* "):
            bullet_count += 1

        version = PlaybookVersion(
            playbook_id=playbook.id,
            version_number=1,
            content=data.initial_content,
            bullet_count=bullet_count,
        )
        db.add(version)
        await db.flush()

        playbook.current_version_id = version.id

    await db.commit()
    await db.refresh(playbook, ["current_version"])

    return PlaybookResponse(
        id=playbook.id,
        name=playbook.name,
        description=playbook.description,
        status=playbook.status,
        source=playbook.source,
        created_at=playbook.created_at,
        updated_at=playbook.updated_at,
        current_version=(
            PlaybookVersionResponse(
                id=playbook.current_version.id,
                version_number=playbook.current_version.version_number,
                content=playbook.current_version.content,
                bullet_count=playbook.current_version.bullet_count,
                created_at=playbook.current_version.created_at,
            )
            if playbook.current_version
            else None
        ),
    )


@router.get("/{playbook_id}", response_model=PlaybookResponse)
async def get_playbook(
    db: DbSession,
    current_user: CurrentUser,
    playbook_id: UUID,
) -> PlaybookResponse:
    """Get a specific playbook by ID.

    Returns the playbook with its current version content.
    """
    query = (
        select(Playbook)
        .where(Playbook.id == playbook_id, Playbook.user_id == current_user.id)
        .options(selectinload(Playbook.current_version))
    )

    result = await db.execute(query)
    playbook = result.scalar_one_or_none()

    if not playbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found",
        )

    return PlaybookResponse(
        id=playbook.id,
        name=playbook.name,
        description=playbook.description,
        status=playbook.status,
        source=playbook.source,
        created_at=playbook.created_at,
        updated_at=playbook.updated_at,
        current_version=(
            PlaybookVersionResponse(
                id=playbook.current_version.id,
                version_number=playbook.current_version.version_number,
                content=playbook.current_version.content,
                bullet_count=playbook.current_version.bullet_count,
                created_at=playbook.current_version.created_at,
            )
            if playbook.current_version
            else None
        ),
    )


@router.put("/{playbook_id}", response_model=PlaybookResponse)
async def update_playbook(
    db: DbSession,
    current_user: SubscribedUser,
    playbook_id: UUID,
    data: PlaybookUpdate,
) -> PlaybookResponse:
    """Update a playbook's metadata.

    Only updates provided fields. Does not modify version content.
    Requires active subscription.
    """
    query = (
        select(Playbook)
        .where(Playbook.id == playbook_id, Playbook.user_id == current_user.id)
        .options(selectinload(Playbook.current_version))
    )

    result = await db.execute(query)
    playbook = result.scalar_one_or_none()

    if not playbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found",
        )

    # Update fields if provided
    if data.name is not None:
        playbook.name = data.name
    if data.description is not None:
        playbook.description = data.description
    if data.status is not None:
        playbook.status = data.status

    await db.commit()
    await db.refresh(playbook, ["current_version"])

    return PlaybookResponse(
        id=playbook.id,
        name=playbook.name,
        description=playbook.description,
        status=playbook.status,
        source=playbook.source,
        created_at=playbook.created_at,
        updated_at=playbook.updated_at,
        current_version=(
            PlaybookVersionResponse(
                id=playbook.current_version.id,
                version_number=playbook.current_version.version_number,
                content=playbook.current_version.content,
                bullet_count=playbook.current_version.bullet_count,
                created_at=playbook.current_version.created_at,
            )
            if playbook.current_version
            else None
        ),
    )


@router.delete("/{playbook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_playbook(
    db: DbSession,
    current_user: SubscribedUser,
    playbook_id: UUID,
) -> None:
    """Delete a playbook.

    This permanently removes the playbook and all associated data
    including versions, outcomes, and evolution jobs.
    Requires active subscription.
    """
    query = select(Playbook).where(Playbook.id == playbook_id, Playbook.user_id == current_user.id)

    result = await db.execute(query)
    playbook = result.scalar_one_or_none()

    if not playbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found",
        )

    await db.delete(playbook)
    await db.commit()


@router.get("/{playbook_id}/versions", response_model=PaginatedVersionResponse)
async def list_playbook_versions(
    db: DbSession,
    current_user: CurrentUser,
    playbook_id: UUID,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
) -> PaginatedVersionResponse:
    """List version history for a playbook.

    Returns paginated list of all versions, ordered by version number descending.
    Each evolution creates a new version with a diff_summary.
    """
    # Verify playbook exists and belongs to user
    playbook = await db.get(Playbook, playbook_id)
    if not playbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found",
        )

    if playbook.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found",
        )

    # Build base query
    base_query = select(PlaybookVersion).where(PlaybookVersion.playbook_id == playbook_id)

    # Get total count
    count_query = select(func.count()).select_from(base_query.subquery())
    total = await db.scalar(count_query) or 0

    # Get paginated results ordered by version number descending
    offset = (page - 1) * page_size
    query = (
        base_query.order_by(PlaybookVersion.version_number.desc()).offset(offset).limit(page_size)
    )

    result = await db.execute(query)
    versions = result.scalars().all()

    # Build response items
    items = [
        PlaybookVersionDetailResponse(
            id=v.id,
            version_number=v.version_number,
            content=v.content,
            bullet_count=v.bullet_count,
            diff_summary=v.diff_summary,
            created_by_job_id=v.created_by_job_id,
            created_at=v.created_at,
        )
        for v in versions
    ]

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return PaginatedVersionResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{playbook_id}/versions/{version_number}", response_model=PlaybookVersionDetailResponse
)
async def get_playbook_version(
    db: DbSession,
    current_user: CurrentUser,
    playbook_id: UUID,
    version_number: int,
) -> PlaybookVersionDetailResponse:
    """Get a specific version of a playbook.

    Returns the version content and metadata for the specified version number.
    """
    # Verify playbook exists and belongs to user
    playbook = await db.get(Playbook, playbook_id)
    if not playbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found",
        )

    if playbook.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found",
        )

    # Get specific version
    query = select(PlaybookVersion).where(
        PlaybookVersion.playbook_id == playbook_id,
        PlaybookVersion.version_number == version_number,
    )

    result = await db.execute(query)
    version = result.scalar_one_or_none()

    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version {version_number} not found for this playbook",
        )

    return PlaybookVersionDetailResponse(
        id=version.id,
        version_number=version.version_number,
        content=version.content,
        bullet_count=version.bullet_count,
        diff_summary=version.diff_summary,
        created_by_job_id=version.created_by_job_id,
        created_at=version.created_at,
    )


@router.get("/{playbook_id}/outcomes", response_model=PaginatedOutcomeResponse)
async def list_playbook_outcomes(
    db: DbSession,
    current_user: CurrentUser,
    playbook_id: UUID,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status_filter: OutcomeStatus | None = Query(None, description="Filter by outcome status"),
    processed: bool | None = Query(None, description="Filter by processed state"),
) -> PaginatedOutcomeResponse:
    """List outcomes for a playbook.

    Returns paginated list of outcomes with optional filtering.
    """
    # Verify playbook exists and belongs to user
    playbook = await db.get(Playbook, playbook_id)
    if not playbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found",
        )

    if playbook.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found",
        )

    # Build base query
    base_query = select(Outcome).where(Outcome.playbook_id == playbook_id)

    if status_filter:
        base_query = base_query.where(Outcome.outcome_status == status_filter)

    if processed is not None:
        if processed:
            base_query = base_query.where(Outcome.processed_at.isnot(None))
        else:
            base_query = base_query.where(Outcome.processed_at.is_(None))

    # Get total count
    count_query = select(func.count()).select_from(base_query.subquery())
    total = await db.scalar(count_query) or 0

    # Get paginated results
    offset = (page - 1) * page_size
    query = base_query.order_by(Outcome.created_at.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    outcomes = result.scalars().all()

    # Build response items
    items = [
        OutcomeResponse(
            id=o.id,
            task_description=o.task_description,
            outcome_status=o.outcome_status,
            notes=o.notes,
            reasoning_trace=o.reasoning_trace,
            created_at=o.created_at,
            processed_at=o.processed_at,
            evolution_job_id=o.evolution_job_id,
        )
        for o in outcomes
    ]

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return PaginatedOutcomeResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post(
    "/{playbook_id}/outcomes",
    response_model=OutcomeCreateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={429: {"description": "Rate limit exceeded"}},
)
async def create_outcome(
    request: Request,
    db: DbSession,
    current_user: SubscribedUser,
    playbook_id: UUID,
    data: OutcomeCreate,
) -> OutcomeCreateResponse:
    """Create a new outcome for a playbook.

    Records a task outcome (success, failure, or partial) for evolution feedback.
    Requires active subscription. Rate limited to 100 outcomes per hour per user.
    """
    # Apply rate limiting (100/hour per user)
    await rate_limit_outcome(request, str(current_user.id))
    # Verify playbook exists and belongs to user
    playbook = await db.get(Playbook, playbook_id)
    if not playbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found",
        )

    if playbook.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found",
        )

    # Create the outcome
    outcome = Outcome(
        playbook_id=playbook_id,
        task_description=data.task_description,
        outcome_status=data.outcome,
        reasoning_trace=data.reasoning_trace,
        notes=data.notes,
    )
    db.add(outcome)
    await db.flush()

    # Count pending (unprocessed) outcomes for this playbook
    pending_query = select(func.count()).select_from(
        select(Outcome)
        .where(Outcome.playbook_id == playbook_id, Outcome.processed_at.is_(None))
        .subquery()
    )
    pending_count = await db.scalar(pending_query) or 0

    await db.commit()

    return OutcomeCreateResponse(
        outcome_id=outcome.id,
        status="recorded",
        pending_outcomes=pending_count,
    )


@router.get("/{playbook_id}/evolutions", response_model=PaginatedEvolutionJobResponse)
async def list_playbook_evolutions(
    db: DbSession,
    current_user: CurrentUser,
    playbook_id: UUID,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status_filter: EvolutionJobStatus | None = Query(None, description="Filter by job status"),
) -> PaginatedEvolutionJobResponse:
    """List evolution jobs for a playbook.

    Returns paginated list of evolution jobs with optional status filtering.
    """
    # Verify playbook exists and belongs to user
    playbook = await db.get(Playbook, playbook_id)
    if not playbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found",
        )

    if playbook.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found",
        )

    # Build base query
    base_query = select(EvolutionJob).where(EvolutionJob.playbook_id == playbook_id)

    if status_filter:
        base_query = base_query.where(EvolutionJob.status == status_filter)

    # Get total count
    count_query = select(func.count()).select_from(base_query.subquery())
    total = await db.scalar(count_query) or 0

    # Get paginated results
    offset = (page - 1) * page_size
    query = base_query.order_by(EvolutionJob.created_at.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    jobs = result.scalars().all()

    # Build response items
    items = [
        EvolutionJobResponse(
            id=job.id,
            status=job.status,
            from_version_id=job.from_version_id,
            to_version_id=job.to_version_id,
            outcomes_processed=job.outcomes_processed,
            error_message=job.error_message,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )
        for job in jobs
    ]

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return PaginatedEvolutionJobResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
