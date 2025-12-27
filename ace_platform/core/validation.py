"""Input validation utilities for ACE Platform.

This module provides centralized size limits and validation functions
for use across API endpoints and MCP tools.

Size limits:
- Playbook content: 100KB (102,400 bytes)
- Reasoning trace: 10KB (10,240 bytes)
- Notes: 2KB (2,048 bytes)
- Task description: 10KB (10,000 chars)

Usage:
    from ace_platform.core.validation import (
        MAX_PLAYBOOK_CONTENT_SIZE,
        validate_playbook_content,
        validate_reasoning_trace,
        validate_notes,
    )

    # Validate and get error message or None
    error = validate_playbook_content(content)
    if error:
        return f"Error: {error}"
"""

# Size limits in characters/bytes
MAX_PLAYBOOK_CONTENT_SIZE = 102_400  # 100KB
MAX_REASONING_TRACE_SIZE = 10_240  # 10KB
MAX_NOTES_SIZE = 2_048  # 2KB
MAX_TASK_DESCRIPTION_SIZE = 10_000  # 10KB
MAX_PLAYBOOK_NAME_SIZE = 255
MAX_PLAYBOOK_DESCRIPTION_SIZE = 2_000


class InputSizeError(ValueError):
    """Exception raised when input size exceeds limits."""

    def __init__(self, field: str, max_size: int, actual_size: int):
        self.field = field
        self.max_size = max_size
        self.actual_size = actual_size
        super().__init__(
            f"{field} exceeds maximum size: {actual_size:,} characters " f"(max: {max_size:,})"
        )


def validate_size(
    value: str | None,
    field_name: str,
    max_size: int,
) -> str | None:
    """Validate that a string value doesn't exceed the maximum size.

    Args:
        value: The value to validate (None is allowed and passes).
        field_name: Name of the field for error messages.
        max_size: Maximum allowed size in characters.

    Returns:
        Error message if validation fails, None if valid.

    Example:
        error = validate_size(content, "Playbook content", MAX_PLAYBOOK_CONTENT_SIZE)
        if error:
            return f"Error: {error}"
    """
    if value is None:
        return None

    actual_size = len(value)
    if actual_size > max_size:
        return (
            f"{field_name} exceeds maximum size: {actual_size:,} characters " f"(max: {max_size:,})"
        )

    return None


def validate_playbook_content(content: str | None) -> str | None:
    """Validate playbook content size.

    Args:
        content: The playbook content to validate.

    Returns:
        Error message if validation fails, None if valid.
    """
    return validate_size(content, "Playbook content", MAX_PLAYBOOK_CONTENT_SIZE)


def validate_reasoning_trace(reasoning_trace: str | None) -> str | None:
    """Validate reasoning trace size.

    Args:
        reasoning_trace: The reasoning trace to validate.

    Returns:
        Error message if validation fails, None if valid.
    """
    return validate_size(reasoning_trace, "Reasoning trace", MAX_REASONING_TRACE_SIZE)


def validate_notes(notes: str | None) -> str | None:
    """Validate notes size.

    Args:
        notes: The notes to validate.

    Returns:
        Error message if validation fails, None if valid.
    """
    return validate_size(notes, "Notes", MAX_NOTES_SIZE)


def validate_task_description(task_description: str | None) -> str | None:
    """Validate task description size.

    Args:
        task_description: The task description to validate.

    Returns:
        Error message if validation fails, None if valid.
    """
    return validate_size(task_description, "Task description", MAX_TASK_DESCRIPTION_SIZE)


def validate_outcome_inputs(
    task_description: str,
    notes: str | None = None,
    reasoning_trace: str | None = None,
) -> str | None:
    """Validate all outcome-related inputs at once.

    Args:
        task_description: The task description to validate.
        notes: Optional notes to validate.
        reasoning_trace: Optional reasoning trace to validate.

    Returns:
        First error message found, or None if all valid.
    """
    # Validate task description (required)
    error = validate_task_description(task_description)
    if error:
        return error

    # Validate optional fields
    error = validate_notes(notes)
    if error:
        return error

    error = validate_reasoning_trace(reasoning_trace)
    if error:
        return error

    return None
