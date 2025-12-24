"""Database seeding for starter playbooks.

This module provides functionality to seed starter playbooks from the
playbooks/ directory into the database on application startup.

Starter playbooks are owned by a system user and marked with
source=PlaybookSource.STARTER. They are read-only templates that
users can view and copy but not modify.
"""

import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.db.models import (
    Playbook,
    PlaybookSource,
    PlaybookStatus,
    PlaybookVersion,
    User,
)

logger = logging.getLogger(__name__)

# Well-known UUID for the system user that owns starter playbooks
# This user is created automatically if it doesn't exist
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000000")
SYSTEM_USER_EMAIL = "system@ace-platform.local"

# Directory containing starter playbooks (relative to project root)
PLAYBOOKS_DIR = Path(__file__).parent.parent.parent / "playbooks"


def count_bullets(content: str) -> int:
    """Count the number of bullets in a playbook.

    Bullets are lines matching the pattern: [id] helpful=X harmful=Y :: content

    Args:
        content: The playbook content.

    Returns:
        Number of bullets found.
    """
    import re

    pattern = r"\[[^\]]+\]\s*helpful=\d+\s*harmful=\d+\s*::"
    return len(re.findall(pattern, content))


def extract_description(content: str) -> str | None:
    """Extract description from playbook content.

    Looks for the first paragraph after the title (# heading).

    Args:
        content: The playbook content.

    Returns:
        Description text or None if not found.
    """
    lines = content.strip().split("\n")
    in_header = False
    description_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# "):
            in_header = True
            continue
        if in_header:
            if stripped.startswith("##"):
                # Reached a section header, stop
                break
            if stripped:
                description_lines.append(stripped)
            elif description_lines:
                # Empty line after description, stop
                break

    return " ".join(description_lines) if description_lines else None


async def ensure_system_user(db: AsyncSession) -> User:
    """Ensure the system user exists, creating it if necessary.

    Args:
        db: Database session.

    Returns:
        The system user.
    """
    result = await db.execute(select(User).where(User.id == SYSTEM_USER_ID))
    system_user = result.scalar_one_or_none()

    if system_user is None:
        logger.info("Creating system user for starter playbooks")
        system_user = User(
            id=SYSTEM_USER_ID,
            email=SYSTEM_USER_EMAIL,
            hashed_password="",  # System user cannot log in
        )
        db.add(system_user)
        await db.flush()

    return system_user


async def seed_starter_playbooks(db: AsyncSession) -> dict:
    """Seed starter playbooks from the playbooks/ directory.

    This function:
    1. Ensures the system user exists
    2. Scans the playbooks/ directory for .md files
    3. Creates playbook records for any that don't exist
    4. Skips playbooks that already exist (by name)

    Args:
        db: Database session.

    Returns:
        Dict with seeding results (created, skipped, errors).
    """
    results = {"created": [], "skipped": [], "errors": []}

    # Ensure system user exists
    await ensure_system_user(db)

    # Find all .md files in playbooks directory
    if not PLAYBOOKS_DIR.exists():
        logger.warning(f"Playbooks directory not found: {PLAYBOOKS_DIR}")
        return results

    playbook_files = list(PLAYBOOKS_DIR.glob("*.md"))
    if not playbook_files:
        logger.info("No starter playbooks found to seed")
        return results

    logger.info(f"Found {len(playbook_files)} starter playbook(s) to check")

    for playbook_file in playbook_files:
        try:
            # Derive playbook name from filename (without extension)
            name = playbook_file.stem.replace("_", " ").title()

            # Check if playbook already exists
            result = await db.execute(
                select(Playbook).where(
                    Playbook.user_id == SYSTEM_USER_ID,
                    Playbook.name == name,
                    Playbook.source == PlaybookSource.STARTER,
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                logger.debug(f"Starter playbook '{name}' already exists, skipping")
                results["skipped"].append(name)
                continue

            # Read playbook content
            content = playbook_file.read_text(encoding="utf-8")
            description = extract_description(content)
            bullet_count = count_bullets(content)

            # Create playbook
            playbook = Playbook(
                user_id=SYSTEM_USER_ID,
                name=name,
                description=description,
                status=PlaybookStatus.ACTIVE,
                source=PlaybookSource.STARTER,
            )
            db.add(playbook)
            await db.flush()

            # Create initial version
            version = PlaybookVersion(
                playbook_id=playbook.id,
                version_number=1,
                content=content,
                bullet_count=bullet_count,
            )
            db.add(version)
            await db.flush()

            # Set current version
            playbook.current_version_id = version.id
            await db.flush()

            logger.info(f"Created starter playbook '{name}' with {bullet_count} bullets")
            results["created"].append(name)

        except Exception as e:
            logger.error(f"Error seeding playbook {playbook_file.name}: {e}")
            results["errors"].append({"file": playbook_file.name, "error": str(e)})

    await db.commit()
    return results
