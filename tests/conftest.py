"""Pytest configuration and fixtures."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Use test database URL
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/ace_platform_test",
)


# =============================================================================
# Rate Limit Override Fixtures
# =============================================================================


async def _no_rate_limit():
    """Mock rate limit dependency that does nothing."""
    pass


@pytest.fixture
def app_no_rate_limit():
    """Create a test FastAPI app with OAuth rate limiting disabled.

    Use this fixture when testing OAuth endpoints to avoid rate limit
    interference between tests.
    """
    from ace_platform.api.main import create_app
    from ace_platform.core.rate_limit import rate_limit_oauth

    app = create_app()
    app.dependency_overrides[rate_limit_oauth] = _no_rate_limit
    yield app
    # Clean up overrides
    app.dependency_overrides.clear()


@pytest.fixture
def client_no_rate_limit(app_no_rate_limit):
    """Create a test client with OAuth rate limiting disabled."""
    return TestClient(app_no_rate_limit)


@pytest.fixture
def client_no_rate_limit_no_redirect(app_no_rate_limit):
    """Create a test client with OAuth rate limiting disabled and no redirect following."""
    return TestClient(app_no_rate_limit, follow_redirects=False)


@pytest.fixture(scope="session")
def db_engine():
    """Create test database engine."""
    from ace_platform.config import get_settings

    settings = get_settings()
    engine = create_engine(settings.database_url, echo=False)
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create a new database session for each test."""
    from ace_platform.db.models import Base

    # Create all tables
    Base.metadata.create_all(bind=db_engine)

    session_factory = sessionmaker(bind=db_engine)
    session = session_factory()

    yield session

    session.rollback()
    session.close()

    # Drop all tables after test
    Base.metadata.drop_all(bind=db_engine)
