"""Pytest configuration and fixtures."""

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Use test database URL
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/ace_platform_test",
)


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

    Session = sessionmaker(bind=db_engine)
    session = Session()

    yield session

    session.rollback()
    session.close()

    # Drop all tables after test
    Base.metadata.drop_all(bind=db_engine)
