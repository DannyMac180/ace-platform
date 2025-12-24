"""Tests for starter playbook seeding.

These tests verify:
1. System user creation
2. Playbook seeding from files
3. Idempotent seeding (skip existing)
4. Bullet counting
5. Description extraction
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ace_platform.db.seed import (
    SYSTEM_USER_EMAIL,
    SYSTEM_USER_ID,
    count_bullets,
    ensure_system_user,
    extract_description,
    seed_starter_playbooks,
)


class TestCountBullets:
    """Tests for bullet counting."""

    def test_count_bullets_empty(self):
        """Test counting bullets in empty content."""
        assert count_bullets("") == 0

    def test_count_bullets_no_bullets(self):
        """Test counting bullets in content without bullets."""
        content = """# My Playbook

This is a description.

## STRATEGIES
Some text here.
"""
        assert count_bullets(content) == 0

    def test_count_bullets_single(self):
        """Test counting a single bullet."""
        content = "[str-00001] helpful=5 harmful=0 :: Some strategy"
        assert count_bullets(content) == 1

    def test_count_bullets_multiple(self):
        """Test counting multiple bullets."""
        content = """# Playbook

## STRATEGIES
[str-00001] helpful=5 harmful=0 :: First strategy
[str-00002] helpful=3 harmful=1 :: Second strategy

## MISTAKES
[err-00001] helpful=2 harmful=0 :: A mistake to avoid
"""
        assert count_bullets(content) == 3

    def test_count_bullets_with_various_ids(self):
        """Test counting bullets with different ID formats."""
        content = """
[str-00001] helpful=0 harmful=0 :: Strategy
[err-00002] helpful=1 harmful=0 :: Error
[ctx-00003] helpful=2 harmful=1 :: Context
[heu-00004] helpful=3 harmful=0 :: Heuristic
"""
        assert count_bullets(content) == 4


class TestExtractDescription:
    """Tests for description extraction."""

    def test_extract_description_none(self):
        """Test extracting from content without description."""
        content = "## STRATEGIES\nSome content"
        assert extract_description(content) is None

    def test_extract_description_simple(self):
        """Test extracting a simple description."""
        content = """# My Playbook

This is the description.

## STRATEGIES
"""
        assert extract_description(content) == "This is the description."

    def test_extract_description_multiline(self):
        """Test extracting a multi-line description."""
        content = """# Coding Agent

A starter playbook for software development tasks
including code generation and debugging.

## STRATEGIES
"""
        expected = (
            "A starter playbook for software development tasks "
            "including code generation and debugging."
        )
        assert extract_description(content) == expected

    def test_extract_description_no_header(self):
        """Test content without title header."""
        content = """Some text here

## STRATEGIES
"""
        assert extract_description(content) is None


class TestEnsureSystemUser:
    """Tests for system user creation."""

    @pytest.mark.asyncio
    async def test_creates_system_user_when_missing(self):
        """Test that system user is created when it doesn't exist."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await ensure_system_user(mock_db)

        # Verify user was added and returned
        mock_db.add.assert_called_once()
        added_user = mock_db.add.call_args[0][0]
        assert added_user.id == SYSTEM_USER_ID
        assert added_user.email == SYSTEM_USER_EMAIL
        assert result.id == SYSTEM_USER_ID
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_existing_system_user(self):
        """Test that existing system user is returned."""
        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = SYSTEM_USER_ID
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result

        user = await ensure_system_user(mock_db)

        mock_db.add.assert_not_called()
        assert user == mock_user


class TestSeedStarterPlaybooks:
    """Tests for starter playbook seeding."""

    @pytest.mark.asyncio
    async def test_seed_with_no_directory(self):
        """Test seeding when playbooks directory doesn't exist."""
        mock_db = AsyncMock()

        with patch("ace_platform.db.seed.PLAYBOOKS_DIR", Path("/nonexistent")):
            results = await seed_starter_playbooks(mock_db)

        assert results["created"] == []
        assert results["skipped"] == []

    @pytest.mark.asyncio
    async def test_seed_with_empty_directory(self):
        """Test seeding when playbooks directory is empty."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("ace_platform.db.seed.PLAYBOOKS_DIR", Path(tmpdir)):
                results = await seed_starter_playbooks(mock_db)

        assert results["created"] == []
        assert results["skipped"] == []

    @pytest.mark.asyncio
    async def test_seed_creates_playbook(self):
        """Test that seeding creates a playbook from file."""
        mock_db = AsyncMock()

        # First call for system user check, second for playbook check
        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = None  # No system user

        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = None  # No existing playbook

        mock_db.execute.side_effect = [mock_result1, mock_result2]

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test playbook file
            playbook_path = Path(tmpdir) / "test_agent.md"
            playbook_path.write_text(
                """# Test Agent

A test playbook.

## STRATEGIES
[str-00001] helpful=1 harmful=0 :: Test strategy
"""
            )

            with patch("ace_platform.db.seed.PLAYBOOKS_DIR", Path(tmpdir)):
                results = await seed_starter_playbooks(mock_db)

        assert "Test Agent" in results["created"]
        assert results["skipped"] == []
        assert results["errors"] == []

        # Verify playbook was added
        add_calls = mock_db.add.call_args_list
        # Should have: system user, playbook, version
        assert len(add_calls) >= 2

    @pytest.mark.asyncio
    async def test_seed_skips_existing_playbook(self):
        """Test that seeding skips existing playbooks."""
        mock_db = AsyncMock()

        # System user exists
        mock_user = MagicMock()
        mock_user.id = SYSTEM_USER_ID
        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = mock_user

        # Playbook exists
        mock_playbook = MagicMock()
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = mock_playbook

        mock_db.execute.side_effect = [mock_result1, mock_result2]

        with tempfile.TemporaryDirectory() as tmpdir:
            playbook_path = Path(tmpdir) / "existing.md"
            playbook_path.write_text("# Existing\nContent")

            with patch("ace_platform.db.seed.PLAYBOOKS_DIR", Path(tmpdir)):
                results = await seed_starter_playbooks(mock_db)

        assert results["created"] == []
        assert "Existing" in results["skipped"]


class TestSystemUserConstants:
    """Tests for system user constants."""

    def test_system_user_id_is_valid_uuid(self):
        """Test that SYSTEM_USER_ID is a valid UUID."""
        assert isinstance(SYSTEM_USER_ID, type(uuid4()))

    def test_system_user_email_format(self):
        """Test that SYSTEM_USER_EMAIL looks like an email."""
        assert "@" in SYSTEM_USER_EMAIL
        assert "." in SYSTEM_USER_EMAIL
