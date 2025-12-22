"""Database session management.

This module provides both async and sync database sessions:
- Async sessions for API/MCP server (high concurrency, I/O-bound)
- Sync sessions for Celery workers (simpler, CPU-bound tasks)
"""

from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from ace_platform.config import get_settings

settings = get_settings()

# Async engine and session factory for API/MCP
async_engine = create_async_engine(
    settings.database_url_async,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Sync engine and session factory for Celery workers
sync_engine = create_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI to get an async database session.

    Usage in FastAPI:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_async_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@contextmanager
def get_sync_db() -> Generator[Session, None, None]:
    """Get a sync database session for Celery workers.

    Usage in Celery tasks:
        with get_sync_db() as db:
            ...
    """
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@asynccontextmanager
async def async_session_context() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for database sessions.

    Usage:
        async with async_session_context() as db:
            result = await db.execute(select(User))
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@contextmanager
def sync_session_context() -> Generator[Session, None, None]:
    """Sync context manager for database sessions.

    Usage:
        with sync_session_context() as db:
            result = db.execute(select(User))
    """
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def init_async_db() -> None:
    """Initialize async database (create tables).

    This is mainly for testing. Use Alembic migrations in production.
    """
    from ace_platform.db.models import Base

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_async_db() -> None:
    """Close async database connections."""
    await async_engine.dispose()


def init_sync_db() -> None:
    """Initialize sync database (create tables).

    This is mainly for testing. Use Alembic migrations in production.
    """
    from ace_platform.db.models import Base

    Base.metadata.create_all(bind=sync_engine)


def close_sync_db() -> None:
    """Close sync database connections."""
    sync_engine.dispose()
