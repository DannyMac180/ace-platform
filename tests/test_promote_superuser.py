"""Tests for superuser promotion script helpers."""

from scripts.promote_superuser import normalize_database_url


def test_normalize_database_url_converts_postgresql_scheme():
    url = "postgresql://user:pass@localhost:5432/ace_platform"
    assert (
        normalize_database_url(url) == "postgresql+asyncpg://user:pass@localhost:5432/ace_platform"
    )


def test_normalize_database_url_converts_postgres_scheme():
    url = "postgres://user:pass@localhost:5432/ace_platform"
    assert (
        normalize_database_url(url) == "postgresql+asyncpg://user:pass@localhost:5432/ace_platform"
    )


def test_normalize_database_url_leaves_async_urls_unchanged():
    url = "postgresql+asyncpg://user:pass@localhost:5432/ace_platform"
    assert normalize_database_url(url) == url
