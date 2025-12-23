"""FastAPI dependencies for ACE Platform.

This module provides common dependencies for route handlers:
- Database session injection
- Correlation ID access
- Authentication (to be added)
"""

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.db.session import get_async_db

from .middleware import CORRELATION_ID_HEADER, get_correlation_id


async def get_db() -> AsyncSession:
    """Get an async database session.

    This is a dependency that provides a database session for route handlers.

    Yields:
        AsyncSession: An async SQLAlchemy session.

    Usage:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Item))
            return result.scalars().all()
    """
    async for session in get_async_db():
        yield session


def get_request_correlation_id(
    x_correlation_id: str | None = Header(None, alias=CORRELATION_ID_HEADER),
) -> str:
    """Get the correlation ID for the current request.

    This dependency provides the correlation ID from the request context.
    It can be used to include the correlation ID in downstream service calls
    or for logging.

    Args:
        x_correlation_id: The correlation ID from headers (injected by FastAPI).

    Returns:
        The correlation ID for the current request.

    Usage:
        @app.get("/items")
        async def get_items(correlation_id: str = Depends(get_request_correlation_id)):
            logger.info(f"[{correlation_id}] Fetching items")
            # Use correlation_id in downstream calls
            return items
    """
    # Prefer the context variable (set by middleware) over the header
    # This ensures we use the same ID that was generated/validated by middleware
    return get_correlation_id() or x_correlation_id or "unknown"


# Type aliases for cleaner dependency injection
DbSession = Annotated[AsyncSession, Depends(get_db)]
CorrelationId = Annotated[str, Depends(get_request_correlation_id)]
