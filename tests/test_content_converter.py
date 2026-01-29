"""Tests for content-to-bullets conversion.

These tests verify:
1. Rule-based candidate extraction
2. LLM refinement prompt generation
3. Bullet formatting
4. Full conversion flow
5. Error handling
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ace_platform.core.content_converter import (
    CandidateBullet,
    ConversionResult,
    build_refinement_prompt,
    convert_content_to_bullets,
    extract_candidates,
    format_bullets_output,
)


class TestExtractCandidates:
    """Tests for rule-based candidate extraction."""

    def test_extract_bullet_list(self):
        """Test extraction from bullet lists."""
        content = """
# Guide

- Always activate the venv before running Python
- Never commit secrets to git
"""
        candidates = extract_candidates(content)

        assert len(candidates) == 2
        assert candidates[0].content == "Always activate the venv before running Python"
        assert candidates[0].source == "list"
        assert candidates[1].content == "Never commit secrets to git"

    def test_extract_numbered_list(self):
        """Test extraction from numbered lists."""
        content = """
## Steps

1. Install dependencies first
2. Run database migrations next
3) Start the development server
"""
        candidates = extract_candidates(content)

        assert len(candidates) == 3
        assert all(c.source == "list" for c in candidates)

    def test_extract_imperative_sentences(self):
        """Test extraction of sentences starting with imperative verbs."""
        content = """
Use meaningful variable names in all code.
This is just a description.
Always run tests before committing code.
"""
        candidates = extract_candidates(content)

        assert len(candidates) == 2
        assert candidates[0].content == "Use meaningful variable names in all code."
        assert candidates[1].content == "Always run tests before committing code."

    def test_skip_headers_without_content(self):
        """Test that plain headers are skipped."""
        content = """
# Main Title

## Section Header

Some regular text.
"""
        candidates = extract_candidates(content)

        # Should not include headers
        assert not any("Title" in c.content or "Header" in c.content for c in candidates)

    def test_extract_colon_instructions(self):
        """Test extraction of header: instruction patterns."""
        content = """
## Database Setup: Run alembic upgrade head to migrate
"""
        candidates = extract_candidates(content)

        assert len(candidates) == 1
        assert candidates[0].content == "Run alembic upgrade head to migrate"
        assert candidates[0].source == "colon"

    def test_empty_content(self):
        """Test extraction from empty content."""
        candidates = extract_candidates("")
        assert candidates == []

    def test_skip_code_blocks(self):
        """Test that code blocks are skipped."""
        content = """
```bash
npm install
```
- Use npm for package management always
"""
        candidates = extract_candidates(content)

        # Should skip code block, only get the bullet
        assert len(candidates) == 1
        assert "npm install" not in candidates[0].content
        assert "Use npm" in candidates[0].content

    def test_skip_short_bullets(self):
        """Test that very short bullets are skipped."""
        content = """
- x
- Short
- This is a longer instruction that should be kept
"""
        candidates = extract_candidates(content)

        # Should only keep the longer one
        assert len(candidates) == 1
        assert "longer instruction" in candidates[0].content

    def test_multiline_code_block(self):
        """Test that multi-line code blocks are fully skipped."""
        content = """
```python
def foo():
    # Always do this
    return True
```

- Always write unit tests for new code
"""
        candidates = extract_candidates(content)

        assert len(candidates) == 1
        assert "Always write unit tests" in candidates[0].content


class TestBuildRefinementPrompt:
    """Tests for LLM prompt generation."""

    def test_prompt_includes_candidates(self):
        """Test that prompt includes all candidates."""
        candidates = [
            CandidateBullet(content="Test instruction 1", source="list", line_number=1),
            CandidateBullet(content="Test instruction 2", source="bold", line_number=5),
        ]
        prompt = build_refinement_prompt(candidates, "Original content here")

        assert "Test instruction 1" in prompt
        assert "Test instruction 2" in prompt
        assert "[list]" in prompt
        assert "[bold]" in prompt

    def test_prompt_includes_format_instructions(self):
        """Test that prompt includes ACE format instructions."""
        candidates = [CandidateBullet(content="Test", source="list", line_number=1)]
        prompt = build_refinement_prompt(candidates, "Content")

        assert "semantic-slug" in prompt
        assert "helpful=0 harmful=0" in prompt
        assert "JSON" in prompt

    def test_prompt_truncates_long_content(self):
        """Test that very long content is truncated."""
        long_content = "x" * 5000
        candidates = [CandidateBullet(content="Test", source="list", line_number=1)]
        prompt = build_refinement_prompt(candidates, long_content)

        assert "..." in prompt
        assert len(prompt) < len(long_content)


class TestFormatBulletsOutput:
    """Tests for bullet formatting."""

    def test_format_single_bullet(self):
        """Test formatting a single bullet."""
        bullets = [{"slug": "test-instruction", "content": "Do the thing."}]
        output = format_bullets_output(bullets)

        assert "[test-instruction]" in output
        assert "helpful=0 harmful=0" in output
        assert "Do the thing." in output

    def test_format_multiple_bullets(self):
        """Test formatting multiple bullets."""
        bullets = [
            {"slug": "first-thing", "content": "First instruction."},
            {"slug": "second-thing", "content": "Second instruction."},
        ]
        output = format_bullets_output(bullets)

        assert "[first-thing]" in output
        assert "[second-thing]" in output
        assert output.count("helpful=0") == 2

    def test_slug_cleanup(self):
        """Test that slugs are properly cleaned."""
        bullets = [{"slug": "Bad Slug With CAPS!", "content": "Test."}]
        output = format_bullets_output(bullets)

        # Should be lowercase, hyphens only
        assert "[bad-slug-with-caps]" in output

    def test_includes_section_header(self):
        """Test that output includes section header."""
        bullets = [{"slug": "test", "content": "Test."}]
        output = format_bullets_output(bullets)

        assert "## INSTRUCTIONS" in output

    def test_handles_empty_slug(self):
        """Test handling of empty slug."""
        bullets = [{"slug": "", "content": "Test content."}]
        output = format_bullets_output(bullets)

        # Should use 'unknown' as fallback after cleaning
        assert "[unknown]" in output
        assert "helpful=0 harmful=0" in output

    def test_handles_slug_that_sanitizes_to_empty(self):
        """Test handling of slug that becomes empty after sanitization."""
        # Slug with only punctuation/special chars becomes empty after sanitization
        bullets = [{"slug": "!!!", "content": "Test content."}]
        output = format_bullets_output(bullets)

        # Should use 'unknown' as fallback
        assert "[unknown]" in output
        assert "helpful=0 harmful=0" in output


class TestConversionResult:
    """Tests for ConversionResult dataclass."""

    def test_has_changes_true(self):
        """Test has_changes when content changed."""
        result = ConversionResult(
            original_content="original",
            converted_content="converted",
            bullets_extracted=1,
            conversion_succeeded=True,
        )
        assert result.has_changes is True

    def test_has_changes_false(self):
        """Test has_changes when content unchanged."""
        result = ConversionResult(
            original_content="same",
            converted_content="same",
            bullets_extracted=0,
            conversion_succeeded=True,
        )
        assert result.has_changes is False

    def test_error_message_optional(self):
        """Test that error_message is optional."""
        result = ConversionResult(
            original_content="a",
            converted_content="b",
            bullets_extracted=1,
            conversion_succeeded=True,
        )
        assert result.error_message is None


@pytest.mark.asyncio
class TestConvertContentToBullets:
    """Tests for the full conversion function."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock async database session."""
        session = MagicMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        return session

    @pytest.fixture
    def user_id(self):
        """Create a test user ID."""
        return uuid4()

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        settings.openai_api_key = "test-key"
        return settings

    async def test_no_candidates_returns_original(self, mock_db_session, user_id, mock_settings):
        """Test that content with no candidates returns original."""
        content = "Just some text."  # No instructions

        result = await convert_content_to_bullets(
            content=content,
            db=mock_db_session,
            user_id=user_id,
            settings=mock_settings,
        )

        assert result.converted_content == content
        assert result.bullets_extracted == 0
        assert result.conversion_succeeded is True
        assert "No candidate" in result.error_message

    async def test_successful_conversion(self, mock_db_session, user_id, mock_settings):
        """Test successful conversion with LLM."""
        content = "- Always run tests before committing code"

        mock_response = json.dumps(
            {
                "bullets": [
                    {"slug": "run-tests", "content": "Always run tests before committing."}
                ],
                "discarded_count": 0,
                "discarded_reasons": [],
            }
        )

        with patch("ace_platform.core.llm_proxy.AsyncMeteredLLMClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.chat_completion = AsyncMock(
                return_value=(
                    mock_response,
                    MagicMock(prompt_tokens=100, completion_tokens=50),
                )
            )
            mock_client_class.return_value = mock_client

            result = await convert_content_to_bullets(
                content=content,
                db=mock_db_session,
                user_id=user_id,
                settings=mock_settings,
            )

        assert result.conversion_succeeded is True
        assert result.bullets_extracted == 1
        assert "[run-tests]" in result.converted_content

    async def test_llm_error_returns_original(self, mock_db_session, user_id, mock_settings):
        """Test that LLM errors fall back to original content."""
        content = "- Test instruction here"

        with patch("ace_platform.core.llm_proxy.AsyncMeteredLLMClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.chat_completion = AsyncMock(side_effect=Exception("API error"))
            mock_client_class.return_value = mock_client

            result = await convert_content_to_bullets(
                content=content,
                db=mock_db_session,
                user_id=user_id,
                settings=mock_settings,
            )

        assert result.conversion_succeeded is False
        assert result.converted_content == content  # Falls back to original
        assert "API error" in result.error_message

    async def test_invalid_json_response(self, mock_db_session, user_id, mock_settings):
        """Test handling of invalid JSON from LLM."""
        content = "- Test instruction here"

        with patch("ace_platform.core.llm_proxy.AsyncMeteredLLMClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.chat_completion = AsyncMock(
                return_value=(
                    "Not valid JSON",
                    MagicMock(),
                )
            )
            mock_client_class.return_value = mock_client

            result = await convert_content_to_bullets(
                content=content,
                db=mock_db_session,
                user_id=user_id,
                settings=mock_settings,
            )

        assert result.conversion_succeeded is False
        assert "parse" in result.error_message.lower()

    async def test_empty_bullets_from_llm(self, mock_db_session, user_id, mock_settings):
        """Test handling when LLM returns no bullets."""
        content = "- Something that looks like instruction"

        mock_response = json.dumps(
            {
                "bullets": [],
                "discarded_count": 1,
                "discarded_reasons": ["Not actionable"],
            }
        )

        with patch("ace_platform.core.llm_proxy.AsyncMeteredLLMClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.chat_completion = AsyncMock(return_value=(mock_response, MagicMock()))
            mock_client_class.return_value = mock_client

            result = await convert_content_to_bullets(
                content=content,
                db=mock_db_session,
                user_id=user_id,
                settings=mock_settings,
            )

        assert result.conversion_succeeded is True
        assert result.bullets_extracted == 0
        assert result.converted_content == content
        assert "no actionable" in result.error_message.lower()

    async def test_passes_playbook_id_to_client(self, mock_db_session, user_id, mock_settings):
        """Test that playbook_id is passed for metering."""
        content = "- Always test your code"
        playbook_id = uuid4()

        mock_response = json.dumps({"bullets": [{"slug": "test-code", "content": "Always test."}]})

        with patch("ace_platform.core.llm_proxy.AsyncMeteredLLMClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.chat_completion = AsyncMock(return_value=(mock_response, MagicMock()))
            mock_client_class.return_value = mock_client

            await convert_content_to_bullets(
                content=content,
                db=mock_db_session,
                user_id=user_id,
                playbook_id=playbook_id,
                settings=mock_settings,
            )

            # Verify playbook_id was passed
            call_kwargs = mock_client.chat_completion.call_args[1]
            assert call_kwargs["playbook_id"] == playbook_id
            assert call_kwargs["operation"] == "content_to_bullets"
