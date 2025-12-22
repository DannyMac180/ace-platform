"""Basic health check tests."""


def test_imports():
    """Test that core modules can be imported."""
    from ace_platform import config
    from ace_platform.db import models

    assert config is not None
    assert models is not None


def test_settings_load():
    """Test that settings can be loaded."""
    from ace_platform.config import get_settings

    settings = get_settings()
    assert settings is not None
    assert settings.database_url is not None


def test_models_metadata():
    """Test that models are properly defined."""
    from ace_platform.db.models import Base

    tables = Base.metadata.tables
    expected_tables = [
        "users",
        "api_keys",
        "playbooks",
        "playbook_versions",
        "evolution_jobs",
        "outcomes",
        "usage_records",
    ]
    for table in expected_tables:
        assert table in tables, f"Missing table: {table}"
