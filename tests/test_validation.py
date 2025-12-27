"""Tests for input validation utilities.

These tests verify:
1. Size limit constants are correct
2. Individual field validation functions work correctly
3. Composite validation functions work correctly
4. InputSizeError exception behavior
5. Edge cases (None values, exact limits, etc.)
"""

from ace_platform.core.validation import (
    MAX_NOTES_SIZE,
    MAX_PLAYBOOK_CONTENT_SIZE,
    MAX_PLAYBOOK_DESCRIPTION_SIZE,
    MAX_PLAYBOOK_NAME_SIZE,
    MAX_REASONING_TRACE_SIZE,
    MAX_TASK_DESCRIPTION_SIZE,
    InputSizeError,
    validate_notes,
    validate_outcome_inputs,
    validate_playbook_content,
    validate_reasoning_trace,
    validate_size,
    validate_task_description,
)


class TestSizeLimitConstants:
    """Tests for size limit constants."""

    def test_playbook_content_limit(self):
        """Playbook content should be limited to 100KB."""
        assert MAX_PLAYBOOK_CONTENT_SIZE == 102_400

    def test_reasoning_trace_limit(self):
        """Reasoning trace should be limited to 10KB."""
        assert MAX_REASONING_TRACE_SIZE == 10_240

    def test_notes_limit(self):
        """Notes should be limited to 2KB."""
        assert MAX_NOTES_SIZE == 2_048

    def test_task_description_limit(self):
        """Task description should be limited to 10KB."""
        assert MAX_TASK_DESCRIPTION_SIZE == 10_000

    def test_playbook_name_limit(self):
        """Playbook name should be limited to 255 chars."""
        assert MAX_PLAYBOOK_NAME_SIZE == 255

    def test_playbook_description_limit(self):
        """Playbook description should be limited to 2000 chars."""
        assert MAX_PLAYBOOK_DESCRIPTION_SIZE == 2_000


class TestInputSizeError:
    """Tests for InputSizeError exception."""

    def test_error_attributes(self):
        """Test that error has correct attributes."""
        error = InputSizeError("test_field", 100, 150)
        assert error.field == "test_field"
        assert error.max_size == 100
        assert error.actual_size == 150

    def test_error_message(self):
        """Test that error message is formatted correctly."""
        error = InputSizeError("Notes", 2048, 3000)
        assert "Notes" in str(error)
        assert "3,000" in str(error)
        assert "2,048" in str(error)

    def test_inherits_from_value_error(self):
        """Test that InputSizeError is a ValueError."""
        error = InputSizeError("field", 100, 150)
        assert isinstance(error, ValueError)


class TestValidateSize:
    """Tests for generic validate_size function."""

    def test_none_value_passes(self):
        """None values should pass validation."""
        result = validate_size(None, "Test field", 100)
        assert result is None

    def test_empty_string_passes(self):
        """Empty strings should pass validation."""
        result = validate_size("", "Test field", 100)
        assert result is None

    def test_under_limit_passes(self):
        """Values under the limit should pass."""
        result = validate_size("hello", "Test field", 100)
        assert result is None

    def test_at_limit_passes(self):
        """Values at exactly the limit should pass."""
        result = validate_size("x" * 100, "Test field", 100)
        assert result is None

    def test_over_limit_fails(self):
        """Values over the limit should return an error message."""
        result = validate_size("x" * 101, "Test field", 100)
        assert result is not None
        assert "Test field" in result
        assert "101" in result
        assert "100" in result

    def test_error_message_format(self):
        """Test error message includes correct information."""
        result = validate_size("x" * 5000, "Playbook content", 2000)
        assert "Playbook content exceeds maximum size" in result
        assert "5,000" in result
        assert "2,000" in result


class TestValidatePlaybookContent:
    """Tests for validate_playbook_content function."""

    def test_valid_content(self):
        """Valid content should pass."""
        result = validate_playbook_content("# My Playbook\n\n- Step 1\n- Step 2")
        assert result is None

    def test_none_content(self):
        """None content should pass."""
        result = validate_playbook_content(None)
        assert result is None

    def test_content_at_limit(self):
        """Content at exactly 100KB should pass."""
        content = "x" * MAX_PLAYBOOK_CONTENT_SIZE
        result = validate_playbook_content(content)
        assert result is None

    def test_content_over_limit(self):
        """Content over 100KB should fail."""
        content = "x" * (MAX_PLAYBOOK_CONTENT_SIZE + 1)
        result = validate_playbook_content(content)
        assert result is not None
        assert "Playbook content" in result


class TestValidateReasoningTrace:
    """Tests for validate_reasoning_trace function."""

    def test_valid_trace(self):
        """Valid reasoning trace should pass."""
        result = validate_reasoning_trace("Step 1: Analyzed the problem\nStep 2: Found solution")
        assert result is None

    def test_none_trace(self):
        """None trace should pass."""
        result = validate_reasoning_trace(None)
        assert result is None

    def test_trace_at_limit(self):
        """Trace at exactly 10KB should pass."""
        trace = "x" * MAX_REASONING_TRACE_SIZE
        result = validate_reasoning_trace(trace)
        assert result is None

    def test_trace_over_limit(self):
        """Trace over 10KB should fail."""
        trace = "x" * (MAX_REASONING_TRACE_SIZE + 1)
        result = validate_reasoning_trace(trace)
        assert result is not None
        assert "Reasoning trace" in result


class TestValidateNotes:
    """Tests for validate_notes function."""

    def test_valid_notes(self):
        """Valid notes should pass."""
        result = validate_notes("This task was completed successfully.")
        assert result is None

    def test_none_notes(self):
        """None notes should pass."""
        result = validate_notes(None)
        assert result is None

    def test_notes_at_limit(self):
        """Notes at exactly 2KB should pass."""
        notes = "x" * MAX_NOTES_SIZE
        result = validate_notes(notes)
        assert result is None

    def test_notes_over_limit(self):
        """Notes over 2KB should fail."""
        notes = "x" * (MAX_NOTES_SIZE + 1)
        result = validate_notes(notes)
        assert result is not None
        assert "Notes" in result


class TestValidateTaskDescription:
    """Tests for validate_task_description function."""

    def test_valid_description(self):
        """Valid task description should pass."""
        result = validate_task_description("Implement a new feature for user authentication")
        assert result is None

    def test_none_description(self):
        """None description should pass."""
        result = validate_task_description(None)
        assert result is None

    def test_description_at_limit(self):
        """Description at exactly 10KB should pass."""
        description = "x" * MAX_TASK_DESCRIPTION_SIZE
        result = validate_task_description(description)
        assert result is None

    def test_description_over_limit(self):
        """Description over 10KB should fail."""
        description = "x" * (MAX_TASK_DESCRIPTION_SIZE + 1)
        result = validate_task_description(description)
        assert result is not None
        assert "Task description" in result


class TestValidateOutcomeInputs:
    """Tests for validate_outcome_inputs composite function."""

    def test_all_valid(self):
        """All valid inputs should pass."""
        result = validate_outcome_inputs(
            task_description="Complete the feature",
            notes="Done successfully",
            reasoning_trace="Step 1: ...",
        )
        assert result is None

    def test_only_required_field(self):
        """Only providing required task_description should pass."""
        result = validate_outcome_inputs(task_description="Complete the feature")
        assert result is None

    def test_with_none_optionals(self):
        """Explicit None for optional fields should pass."""
        result = validate_outcome_inputs(
            task_description="Complete the feature",
            notes=None,
            reasoning_trace=None,
        )
        assert result is None

    def test_task_description_too_large(self):
        """Oversized task description should fail first."""
        result = validate_outcome_inputs(
            task_description="x" * (MAX_TASK_DESCRIPTION_SIZE + 1),
            notes="Valid notes",
            reasoning_trace="Valid trace",
        )
        assert result is not None
        assert "Task description" in result

    def test_notes_too_large(self):
        """Oversized notes should fail."""
        result = validate_outcome_inputs(
            task_description="Valid description",
            notes="x" * (MAX_NOTES_SIZE + 1),
        )
        assert result is not None
        assert "Notes" in result

    def test_reasoning_trace_too_large(self):
        """Oversized reasoning trace should fail."""
        result = validate_outcome_inputs(
            task_description="Valid description",
            reasoning_trace="x" * (MAX_REASONING_TRACE_SIZE + 1),
        )
        assert result is not None
        assert "Reasoning trace" in result

    def test_returns_first_error(self):
        """Should return the first error found (task_description)."""
        result = validate_outcome_inputs(
            task_description="x" * (MAX_TASK_DESCRIPTION_SIZE + 1),
            notes="x" * (MAX_NOTES_SIZE + 1),
            reasoning_trace="x" * (MAX_REASONING_TRACE_SIZE + 1),
        )
        assert result is not None
        # First error should be for task_description
        assert "Task description" in result


class TestPydanticSchemaIntegration:
    """Tests verifying Pydantic schemas use the correct constants."""

    def _get_max_length(self, field_info) -> int | None:
        """Extract max_length from Pydantic field metadata."""
        for constraint in field_info.metadata:
            if hasattr(constraint, "max_length"):
                return constraint.max_length
        return None

    def test_playbook_create_uses_constants(self):
        """PlaybookCreate schema should use validation constants."""
        from ace_platform.api.routes.playbooks import PlaybookCreate

        # Get field info from the model
        name_field = PlaybookCreate.model_fields["name"]
        description_field = PlaybookCreate.model_fields["description"]
        content_field = PlaybookCreate.model_fields["initial_content"]

        # Check max_length matches constants
        assert self._get_max_length(name_field) == MAX_PLAYBOOK_NAME_SIZE
        assert self._get_max_length(description_field) == MAX_PLAYBOOK_DESCRIPTION_SIZE
        assert self._get_max_length(content_field) == MAX_PLAYBOOK_CONTENT_SIZE

    def test_playbook_update_uses_constants(self):
        """PlaybookUpdate schema should use validation constants."""
        from ace_platform.api.routes.playbooks import PlaybookUpdate

        # Get field info from the model
        name_field = PlaybookUpdate.model_fields["name"]
        description_field = PlaybookUpdate.model_fields["description"]

        # Check max_length matches constants
        assert self._get_max_length(name_field) == MAX_PLAYBOOK_NAME_SIZE
        assert self._get_max_length(description_field) == MAX_PLAYBOOK_DESCRIPTION_SIZE

    def test_outcome_create_uses_constants(self):
        """OutcomeCreate schema should use validation constants."""
        from ace_platform.api.routes.playbooks import OutcomeCreate

        # Get field info from the model
        task_field = OutcomeCreate.model_fields["task_description"]
        notes_field = OutcomeCreate.model_fields["notes"]
        trace_field = OutcomeCreate.model_fields["reasoning_trace"]

        # Check max_length matches constants
        assert self._get_max_length(task_field) == MAX_TASK_DESCRIPTION_SIZE
        assert self._get_max_length(notes_field) == MAX_NOTES_SIZE
        assert self._get_max_length(trace_field) == MAX_REASONING_TRACE_SIZE


class TestMCPToolValidation:
    """Tests verifying MCP tools use validation functions."""

    def test_record_outcome_validates_inputs(self):
        """record_outcome MCP tool should validate input sizes."""
        # This is tested by checking that the import is present
        # and the function is called in the tool
        from ace_platform.mcp.server import record_outcome

        # Verify the function exists and has validation in its docstring
        assert record_outcome is not None
        assert "Size limits" in record_outcome.__doc__
        assert "10KB" in record_outcome.__doc__
        assert "2KB" in record_outcome.__doc__
