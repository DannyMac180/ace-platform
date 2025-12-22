"""SQLAlchemy models for ACE Platform.

This module defines all database models for the platform:
- User: Platform users with auth
- Playbook: User playbooks with version tracking
- PlaybookVersion: Immutable playbook versions
- Outcome: Task outcomes for evolution
- EvolutionJob: Background evolution jobs
- UsageRecord: LLM usage tracking
- ApiKey: MCP API keys
"""

import enum
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func

if TYPE_CHECKING:
    pass


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class PlaybookStatus(str, enum.Enum):
    """Status of a playbook."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class PlaybookSource(str, enum.Enum):
    """Source/origin of a playbook."""

    STARTER = "starter"
    USER_CREATED = "user_created"
    IMPORTED = "imported"


class OutcomeStatus(str, enum.Enum):
    """Outcome of a task execution."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


class EvolutionJobStatus(str, enum.Enum):
    """Status of an evolution job."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class User(Base):
    """Platform user."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    playbooks: Mapped[list["Playbook"]] = relationship(
        "Playbook", back_populates="user", cascade="all, delete-orphan"
    )
    api_keys: Mapped[list["ApiKey"]] = relationship(
        "ApiKey", back_populates="user", cascade="all, delete-orphan"
    )
    usage_records: Mapped[list["UsageRecord"]] = relationship(
        "UsageRecord", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"


class Playbook(Base):
    """User playbook with version tracking."""

    __tablename__ = "playbooks"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_version_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook_versions.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )
    status: Mapped[PlaybookStatus] = mapped_column(
        Enum(PlaybookStatus), default=PlaybookStatus.ACTIVE, nullable=False
    )
    source: Mapped[PlaybookSource] = mapped_column(
        Enum(PlaybookSource), default=PlaybookSource.USER_CREATED, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="playbooks")
    current_version: Mapped["PlaybookVersion | None"] = relationship(
        "PlaybookVersion",
        foreign_keys=[current_version_id],
        post_update=True,
    )
    versions: Mapped[list["PlaybookVersion"]] = relationship(
        "PlaybookVersion",
        back_populates="playbook",
        foreign_keys="PlaybookVersion.playbook_id",
        cascade="all, delete-orphan",
        order_by="PlaybookVersion.version_number.desc()",
    )
    outcomes: Mapped[list["Outcome"]] = relationship(
        "Outcome", back_populates="playbook", cascade="all, delete-orphan"
    )
    evolution_jobs: Mapped[list["EvolutionJob"]] = relationship(
        "EvolutionJob", back_populates="playbook", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Playbook {self.name}>"


class PlaybookVersion(Base):
    """Immutable playbook version for evolution history."""

    __tablename__ = "playbook_versions"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    playbook_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbooks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    bullet_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by_job_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evolution_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    diff_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    playbook: Mapped["Playbook"] = relationship(
        "Playbook", back_populates="versions", foreign_keys=[playbook_id]
    )
    created_by_job: Mapped["EvolutionJob | None"] = relationship(
        "EvolutionJob", back_populates="created_version", foreign_keys=[created_by_job_id]
    )

    # Composite unique constraint: one version number per playbook
    __table_args__ = (
        UniqueConstraint("playbook_id", "version_number", name="uq_playbook_version"),
        Index("ix_playbook_versions_playbook_version", "playbook_id", "version_number"),
    )

    def __repr__(self) -> str:
        return f"<PlaybookVersion {self.playbook_id}:v{self.version_number}>"


class Outcome(Base):
    """Task outcome for evolution feedback."""

    __tablename__ = "outcomes"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    playbook_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbooks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_description: Mapped[str] = mapped_column(Text, nullable=False)
    outcome_status: Mapped[OutcomeStatus] = mapped_column(Enum(OutcomeStatus), nullable=False)
    reasoning_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reflection_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evolution_job_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evolution_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    playbook: Mapped["Playbook"] = relationship("Playbook", back_populates="outcomes")
    evolution_job: Mapped["EvolutionJob | None"] = relationship(
        "EvolutionJob", back_populates="processed_outcomes"
    )

    # Index for finding unprocessed outcomes
    __table_args__ = (Index("ix_outcomes_playbook_unprocessed", "playbook_id", "processed_at"),)

    def __repr__(self) -> str:
        return f"<Outcome {self.id} ({self.outcome_status.value})>"


class EvolutionJob(Base):
    """Background job for playbook evolution."""

    __tablename__ = "evolution_jobs"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    playbook_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbooks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[EvolutionJobStatus] = mapped_column(
        Enum(EvolutionJobStatus), default=EvolutionJobStatus.QUEUED, nullable=False
    )
    from_version_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    to_version_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    outcomes_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_totals: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ace_core_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    playbook: Mapped["Playbook"] = relationship("Playbook", back_populates="evolution_jobs")
    from_version: Mapped["PlaybookVersion | None"] = relationship(
        "PlaybookVersion", foreign_keys=[from_version_id]
    )
    to_version: Mapped["PlaybookVersion | None"] = relationship(
        "PlaybookVersion", foreign_keys=[to_version_id]
    )
    created_version: Mapped["PlaybookVersion | None"] = relationship(
        "PlaybookVersion",
        back_populates="created_by_job",
        foreign_keys="PlaybookVersion.created_by_job_id",
    )
    processed_outcomes: Mapped[list["Outcome"]] = relationship(
        "Outcome", back_populates="evolution_job"
    )
    usage_records: Mapped[list["UsageRecord"]] = relationship(
        "UsageRecord", back_populates="evolution_job"
    )

    # Partial unique index to prevent concurrent evolution jobs
    # Only one queued or running job per playbook at a time
    __table_args__ = (
        Index(
            "ix_evolution_jobs_active_per_playbook",
            "playbook_id",
            unique=True,
            postgresql_where=(status.in_([EvolutionJobStatus.QUEUED, EvolutionJobStatus.RUNNING])),
        ),
    )

    def __repr__(self) -> str:
        return f"<EvolutionJob {self.id} ({self.status.value})>"


class UsageRecord(Base):
    """LLM usage record for metering and billing."""

    __tablename__ = "usage_records"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    playbook_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbooks.id", ondelete="SET NULL"),
        nullable=True,
    )
    evolution_job_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evolution_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    operation: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="usage_records")
    playbook: Mapped["Playbook | None"] = relationship("Playbook")
    evolution_job: Mapped["EvolutionJob | None"] = relationship(
        "EvolutionJob", back_populates="usage_records"
    )

    # Index for billing aggregation
    __table_args__ = (Index("ix_usage_records_user_created", "user_id", "created_at"),)

    def __repr__(self) -> str:
        return f"<UsageRecord {self.operation} {self.total_tokens} tokens>"


class ApiKey(Base):
    """API key for MCP authentication."""

    __tablename__ = "api_keys"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(8), nullable=False)
    hashed_key: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="api_keys")

    def __repr__(self) -> str:
        return f"<ApiKey {self.key_prefix}... ({self.name})>"

    @property
    def is_active(self) -> bool:
        """Check if the API key is active (not revoked)."""
        return self.revoked_at is None
