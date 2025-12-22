"""Database module for ACE Platform.

Provides SQLAlchemy models and session management.
"""

from ace_platform.db.models import (
    ApiKey,
    Base,
    EvolutionJob,
    EvolutionJobStatus,
    Outcome,
    OutcomeStatus,
    Playbook,
    PlaybookSource,
    PlaybookStatus,
    PlaybookVersion,
    UsageRecord,
    User,
)
from ace_platform.db.session import (
    AsyncSessionLocal,
    SyncSessionLocal,
    async_session_context,
    close_async_db,
    close_sync_db,
    get_async_db,
    get_sync_db,
    init_async_db,
    init_sync_db,
    sync_session_context,
)

__all__ = [
    # Base
    "Base",
    # Models
    "User",
    "Playbook",
    "PlaybookVersion",
    "Outcome",
    "EvolutionJob",
    "UsageRecord",
    "ApiKey",
    # Enums
    "PlaybookStatus",
    "PlaybookSource",
    "OutcomeStatus",
    "EvolutionJobStatus",
    # Session factories
    "AsyncSessionLocal",
    "SyncSessionLocal",
    # Session getters
    "get_async_db",
    "get_sync_db",
    # Context managers
    "async_session_context",
    "sync_session_context",
    # Init/Close
    "init_async_db",
    "init_sync_db",
    "close_async_db",
    "close_sync_db",
]
