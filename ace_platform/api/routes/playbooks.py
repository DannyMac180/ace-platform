"""Playbook CRUD API routes.

This module provides REST API endpoints for playbook management:
- GET /playbooks - List user's playbooks with pagination
- POST /playbooks - Create a new playbook
- GET /playbooks/{id} - Get a specific playbook
- PUT /playbooks/{id} - Update a playbook
- DELETE /playbooks/{id} - Delete a playbook
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ace_platform.api.auth import require_user
from ace_platform.api.deps import get_db
from ace_platform.db.models import (
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

    name: str = Field(..., min_length=1, max_length=255, description="Playbook name")
    description: str | None = Field(None, max_length=2000, description="Playbook description")
    initial_content: str | None = Field(
        None, max_length=100000, description="Initial playbook content (markdown)"
    )


class PlaybookUpdate(BaseModel):
    """Request schema for updating a playbook."""

    name: str | None = Field(None, min_length=1, max_length=255, description="Playbook name")
    description: str | None = Field(None, max_length=2000, description="Playbook description")
    status: PlaybookStatus | None = Field(None, description="Playbook status")


class PlaybookVersionResponse(BaseModel):
    """Response schema for playbook version."""

    id: UUID
    version_number: int
    content: str
    bullet_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


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


# Dependency type aliases
DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(require_user)]


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
    current_user: CurrentUser,
    data: PlaybookCreate,
) -> PlaybookResponse:
    """Create a new playbook.

    Optionally include initial content to create the first version.
    """
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
    current_user: CurrentUser,
    playbook_id: UUID,
    data: PlaybookUpdate,
) -> PlaybookResponse:
    """Update a playbook's metadata.

    Only updates provided fields. Does not modify version content.
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
    current_user: CurrentUser,
    playbook_id: UUID,
) -> None:
    """Delete a playbook.

    This permanently removes the playbook and all associated data
    including versions, outcomes, and evolution jobs.
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
