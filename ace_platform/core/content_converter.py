"""Content-to-bullets conversion for ACE playbooks.

This module provides hybrid (rule-based + LLM refinement) conversion
of markdown content into ACE bullet format.

ACE Bullet Format:
    [semantic-slug] helpful=0 harmful=0 :: Actionable instruction content

Example:
    [venv-activation] helpful=0 harmful=0 :: Always activate the virtual environment before running Python commands.
"""

import json
import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.config import Settings, get_settings

# Constants
CONVERSION_MODEL = "gpt-5-mini"
CONVERSION_MAX_TOKENS = 4096
# Note: gpt-5-mini doesn't support custom temperature, uses default (1.0)

# Regex patterns for rule-based extraction
BULLET_LIST_PATTERN = r"^[\s]*[-*]\s+(.+)$"
NUMBERED_LIST_PATTERN = r"^[\s]*\d+[.)]\s+(.+)$"
BOLD_INSTRUCTION_PATTERN = r"\*\*([^*]+)\*\*"
COLON_INSTRUCTION_PATTERN = r"^#+\s*[^:]+:\s*(.+)$"

# Imperative verb indicators
IMPERATIVE_VERBS = {
    "use",
    "run",
    "add",
    "create",
    "ensure",
    "always",
    "never",
    "avoid",
    "check",
    "verify",
    "make",
    "set",
    "configure",
    "install",
    "update",
    "remove",
    "delete",
    "follow",
    "apply",
    "include",
    "exclude",
    "prefer",
    "consider",
    "test",
    "validate",
    "handle",
    "catch",
    "throw",
    "return",
    "import",
    "export",
    "initialize",
    "start",
    "stop",
    "enable",
    "disable",
}


@dataclass
class ConversionResult:
    """Result from content-to-bullets conversion."""

    original_content: str
    converted_content: str
    bullets_extracted: int
    conversion_succeeded: bool
    error_message: str | None = None

    @property
    def has_changes(self) -> bool:
        """Check if conversion produced different content."""
        return self.original_content != self.converted_content


@dataclass
class CandidateBullet:
    """A candidate bullet extracted by rule-based processing."""

    content: str
    source: str  # "list", "bold", "colon", "sentence"
    line_number: int


def extract_candidates(content: str) -> list[CandidateBullet]:
    """Extract candidate bullets using rule-based patterns.

    This is the first phase of the hybrid approach - extract all
    potentially actionable content from the markdown.

    Args:
        content: Raw markdown content.

    Returns:
        List of candidate bullets with their source type.
    """
    candidates = []
    lines = content.split("\n")
    in_code_block = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        # Track code blocks
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue

        # Skip content inside code blocks
        if in_code_block:
            continue

        # Skip headers without colons (just section markers)
        if stripped.startswith("#") and ":" not in stripped:
            continue

        # Pattern 1: Bullet points (- or *)
        bullet_match = re.match(BULLET_LIST_PATTERN, line)
        if bullet_match:
            candidate_content = bullet_match.group(1).strip()
            # Skip very short items or items that look like headers
            if len(candidate_content) > 10 and not candidate_content.startswith("#"):
                candidates.append(
                    CandidateBullet(
                        content=candidate_content,
                        source="list",
                        line_number=i + 1,
                    )
                )
            continue

        # Pattern 2: Numbered lists
        numbered_match = re.match(NUMBERED_LIST_PATTERN, line)
        if numbered_match:
            candidate_content = numbered_match.group(1).strip()
            if len(candidate_content) > 10:
                candidates.append(
                    CandidateBullet(
                        content=candidate_content,
                        source="list",
                        line_number=i + 1,
                    )
                )
            continue

        # Pattern 3: Bold instructions (standalone)
        if stripped.startswith("**") and "**" in stripped[2:]:
            # Extract content between ** markers
            bold_match = re.search(r"\*\*([^*]+)\*\*", stripped)
            if bold_match:
                inner = bold_match.group(1).strip()
                if inner and len(inner) > 10:
                    candidates.append(
                        CandidateBullet(
                            content=inner,
                            source="bold",
                            line_number=i + 1,
                        )
                    )
                    continue

        # Pattern 4: Header with colon content
        colon_match = re.match(COLON_INSTRUCTION_PATTERN, line)
        if colon_match:
            candidate_content = colon_match.group(1).strip()
            if len(candidate_content) > 10:
                candidates.append(
                    CandidateBullet(
                        content=candidate_content,
                        source="colon",
                        line_number=i + 1,
                    )
                )
            continue

        # Pattern 5: Sentences starting with imperative verbs
        words = stripped.split()
        if words:
            first_word = words[0].lower().rstrip(",:")
            if first_word in IMPERATIVE_VERBS:
                # Only if it's a reasonable instruction length
                if 20 < len(stripped) < 500:
                    candidates.append(
                        CandidateBullet(
                            content=stripped,
                            source="sentence",
                            line_number=i + 1,
                        )
                    )

    return candidates


def build_refinement_prompt(candidates: list[CandidateBullet], original_content: str) -> str:
    """Build the LLM prompt for refining candidates into bullets.

    Args:
        candidates: Rule-based extracted candidates.
        original_content: Original markdown for context.

    Returns:
        Formatted prompt string.
    """
    candidates_text = "\n".join(f"- [{c.source}] {c.content}" for c in candidates)

    # Truncate original content if too long
    max_context_length = 3000
    context = original_content[:max_context_length]
    if len(original_content) > max_context_length:
        context += "..."

    return f"""You are converting documentation into ACE playbook bullets.

## ACE Bullet Format
Each bullet must follow this exact format:
[semantic-slug] helpful=0 harmful=0 :: Actionable instruction content

Requirements:
1. semantic-slug: 2-4 word kebab-case identifier describing the instruction (e.g., "venv-activation", "pr-workflow", "error-handling")
2. helpful=0 harmful=0: Initial scores (always 0 for new bullets)
3. Actionable instruction: Clear, imperative guidance that an AI agent can follow

## Rules
- ONLY include actionable instructions (things to DO or AVOID)
- DISCARD non-actionable content (descriptions, explanations, background info)
- Each bullet should be self-contained and complete
- Slugs must be unique and descriptive
- Keep instruction content concise but complete (aim for 1-2 sentences)

## Candidates Extracted (may include non-actionable content to filter)
{candidates_text}

## Original Context
{context}

## Output Format
Return a JSON object with this structure:
{{
    "bullets": [
        {{
            "slug": "semantic-slug-here",
            "content": "Actionable instruction content here."
        }}
    ],
    "discarded_count": 3,
    "discarded_reasons": ["Not actionable - just a description", "Duplicate of another bullet", "Too vague"]
}}

Return ONLY the JSON object, no other text."""


def format_bullets_output(bullets: list[dict[str, str]]) -> str:
    """Format refined bullets into ACE playbook format.

    Args:
        bullets: List of dicts with 'slug' and 'content' keys.

    Returns:
        Formatted playbook content string.
    """
    lines = ["## INSTRUCTIONS\n"]

    for bullet in bullets:
        slug = bullet.get("slug", "unknown")
        content = bullet.get("content", "")

        # Clean up the slug - ensure lowercase, hyphens only
        slug = re.sub(r"[^a-z0-9-]", "-", slug.lower())
        slug = re.sub(r"-+", "-", slug).strip("-")

        # Fallback to "unknown" if slug is empty after sanitization
        if not slug:
            slug = "unknown"

        # Format the bullet
        lines.append(f"[{slug}] helpful=0 harmful=0 :: {content}")

    return "\n".join(lines)


async def convert_content_to_bullets(
    content: str,
    db: AsyncSession,
    user_id: UUID,
    playbook_id: UUID | None = None,
    settings: Settings | None = None,
) -> ConversionResult:
    """Convert markdown content to ACE bullet format.

    This is the main entry point for the hybrid conversion process:
    1. Rule-based extraction of candidate bullets
    2. LLM refinement to filter and format bullets

    Args:
        content: Raw markdown content to convert.
        db: Async database session for metering.
        user_id: User ID for usage tracking.
        playbook_id: Optional playbook ID for usage tracking.
        settings: Platform settings (uses default if None).

    Returns:
        ConversionResult with converted content and metadata.
    """
    # Import here to avoid circular imports
    from ace_platform.core.llm_proxy import AsyncMeteredLLMClient

    settings = settings or get_settings()

    # Phase 1: Rule-based extraction
    candidates = extract_candidates(content)

    if not candidates:
        # No candidates found - return original content
        return ConversionResult(
            original_content=content,
            converted_content=content,
            bullets_extracted=0,
            conversion_succeeded=True,
            error_message="No candidate bullets found in content",
        )

    # Phase 2: LLM refinement
    try:
        client = AsyncMeteredLLMClient(
            api_key=settings.openai_api_key,
            db_session=db,
            user_id=user_id,
        )

        prompt = build_refinement_prompt(candidates, content)

        response, _usage_info = await client.chat_completion(
            model=CONVERSION_MODEL,
            messages=[{"role": "user", "content": prompt}],
            operation="content_to_bullets",
            playbook_id=playbook_id,
            max_completion_tokens=CONVERSION_MAX_TOKENS,
            response_format={"type": "json_object"},
        )

        # Parse LLM response
        result_data = json.loads(response)
        bullets = result_data.get("bullets", [])

        if not bullets:
            return ConversionResult(
                original_content=content,
                converted_content=content,
                bullets_extracted=0,
                conversion_succeeded=True,
                error_message="LLM found no actionable bullets in content",
            )

        # Format the bullets
        converted = format_bullets_output(bullets)

        return ConversionResult(
            original_content=content,
            converted_content=converted,
            bullets_extracted=len(bullets),
            conversion_succeeded=True,
        )

    except json.JSONDecodeError as e:
        return ConversionResult(
            original_content=content,
            converted_content=content,
            bullets_extracted=0,
            conversion_succeeded=False,
            error_message=f"Failed to parse LLM response: {e}",
        )
    except Exception as e:
        return ConversionResult(
            original_content=content,
            converted_content=content,
            bullets_extracted=0,
            conversion_succeeded=False,
            error_message=f"Conversion failed: {e}",
        )
