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
    PAUSED = "paused"
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


class SubscriptionStatus(str, enum.Enum):
    """Status of a user's subscription."""

    NONE = "none"  # No subscription (free tier)
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    UNPAID = "unpaid"


class OAuthProvider(str, enum.Enum):
    """Supported OAuth providers."""

    GOOGLE = "google"
    GITHUB = "github"


class AuditEventType(str, enum.Enum):
    """Types of security-relevant events for audit logging."""

    # Authentication events
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    LOGOUT = "logout"
    OAUTH_LOGIN_SUCCESS = "oauth_login_success"
    OAUTH_LOGIN_FAILURE = "oauth_login_failure"

    # Password events
    PASSWORD_CHANGE = "password_change"
    PASSWORD_RESET_REQUEST = "password_reset_request"
    PASSWORD_RESET_COMPLETE = "password_reset_complete"

    # Email verification
    EMAIL_VERIFICATION_SENT = "email_verification_sent"
    EMAIL_VERIFIED = "email_verified"

    # API key events
    API_KEY_CREATED = "api_key_created"
    API_KEY_REVOKED = "api_key_revoked"

    # Account events
    ACCOUNT_CREATED = "account_created"
    ACCOUNT_LOCKED = "account_locked"
    ACCOUNT_UNLOCKED = "account_unlocked"
    ACCOUNT_DELETED = "account_deleted"

    # Data & privacy
    DATA_EXPORTED = "data_exported"

    # Authorization events
    PERMISSION_DENIED = "permission_denied"

    # Subscription events
    SUBSCRIPTION_CREATED = "subscription_created"
    SUBSCRIPTION_UPDATED = "subscription_updated"
    SUBSCRIPTION_CANCELED = "subscription_canceled"
    PAYMENT_METHOD_ADDED = "payment_method_added"
    PAYMENT_METHOD_REMOVED = "payment_method_removed"

    # OAuth account management
    OAUTH_ACCOUNT_LINKED = "oauth_account_linked"
    OAUTH_ACCOUNT_UNLINKED = "oauth_account_unlinked"


class AuditSeverity(str, enum.Enum):
    """Severity levels for audit events."""

    INFO = "info"  # Normal operations (login success, logout)
    WARNING = "warning"  # Potential issues (login failure, permission denied)
    CRITICAL = "critical"  # Security concerns (account locked, suspicious activity)


class User(Base):
    """Platform user."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # Nullable for OAuth-only users
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subscription_tier: Mapped[str | None] = mapped_column(String(50), nullable=True)
    subscription_status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus), default=SubscriptionStatus.NONE, nullable=False
    )
    subscription_current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    has_used_trial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    has_payment_method: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    stripe_default_payment_method_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
    oauth_accounts: Mapped[list["UserOAuthAccount"]] = relationship(
        "UserOAuthAccount", back_populates="user", cascade="all, delete-orphan"
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


class UserOAuthAccount(Base):
    """Links OAuth provider accounts to platform users.

    Enables users to authenticate via multiple OAuth providers (Google, GitHub)
    and links them to a single platform account by email.
    """

    __tablename__ = "user_oauth_accounts"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[OAuthProvider] = mapped_column(Enum(OAuthProvider), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_email: Mapped[str] = mapped_column(String(255), nullable=False)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    raw_user_info: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="oauth_accounts")

    # Constraints: one provider account per user per provider
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_oauth_provider_user"),
        Index("ix_oauth_accounts_user_provider", "user_id", "provider"),
    )

    def __repr__(self) -> str:
        return f"<UserOAuthAccount {self.provider.value}:{self.provider_email}>"


class PasswordResetToken(Base):
    """Secure password reset token.

    Tokens are stored as hashes (not plaintext) for security.
    Each token can only be used once and expires after a set time.
    """

    __tablename__ = "password_reset_tokens"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<PasswordResetToken {self.id} (user={self.user_id})>"

    @property
    def is_valid(self) -> bool:
        """Check if the token is still valid (not used and not expired)."""
        from datetime import UTC, datetime

        return self.used_at is None and self.expires_at > datetime.now(UTC)


class AuditLog(Base):
    """Security audit log for tracking sensitive operations.

    Records security-relevant events such as:
    - Authentication attempts (login, logout, OAuth)
    - Password changes and resets
    - API key creation and revocation
    - Account state changes
    - Authorization failures
    - Subscription changes
    """

    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,  # Nullable for failed login attempts where user doesn't exist
        index=True,
    )
    event_type: Mapped[AuditEventType] = mapped_column(Enum(AuditEventType), nullable=False)
    severity: Mapped[AuditSeverity] = mapped_column(
        Enum(AuditSeverity), default=AuditSeverity.INFO, nullable=False
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv6 max length
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relationships
    user: Mapped["User | None"] = relationship("User")

    # Indexes for efficient querying
    __table_args__ = (
        Index("ix_audit_logs_user_created", "user_id", "created_at"),
        Index("ix_audit_logs_event_type", "event_type"),
        Index("ix_audit_logs_severity_created", "severity", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.event_type.value} user={self.user_id}>"


class ProcessedWebhookEvent(Base):
    """Tracks processed Stripe webhook event IDs for idempotency.

    Stripe may deliver the same webhook event more than once.
    This table records each processed event ID so duplicates can be skipped.
    """

    __tablename__ = "processed_webhook_events"

    stripe_event_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ProcessedWebhookEvent {self.stripe_event_id}>"
