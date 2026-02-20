#!/usr/bin/env python3
"""Promote a user to superuser (admin + enterprise tier).

This sets:
- is_admin = True
- subscription_tier = "enterprise"
- subscription_status = "active"
- email_verified = True

Usage:
    # Using DATABASE_URL from environment or .env file
    source venv/bin/activate && python scripts/promote_superuser.py mcateerd2@gmail.com

    # With explicit database URL
    DATABASE_URL=postgresql://... python scripts/promote_superuser.py mcateerd2@gmail.com
"""

import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def normalize_database_url(database_url: str) -> str:
    """Normalize DB URLs for SQLAlchemy async engine."""
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return database_url


async def promote_user(email: str) -> None:
    from sqlalchemy import select, update
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    # Load DATABASE_URL from environment or .env
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        from dotenv import load_dotenv

        load_dotenv()
        database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        print("ERROR: DATABASE_URL not set. Set it in .env or environment.")
        sys.exit(1)

    # Convert to async URL if needed
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(database_url)

    async with AsyncSession(engine) as session:
        from ace_platform.db.models import User

        # Find the user
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            print(f"ERROR: No user found with email '{email}'")
            await engine.dispose()
            sys.exit(1)

        print(f"Found user: {user.email} (id: {user.id})")
        print("  Current state:")
        print(f"    is_admin: {user.is_admin}")
        print(f"    subscription_tier: {user.subscription_tier}")
        print(f"    subscription_status: {user.subscription_status}")
        print(f"    email_verified: {user.email_verified}")

        # Promote to superuser
        await session.execute(
            update(User)
            .where(User.id == user.id)
            .values(
                is_admin=True,
                subscription_tier="enterprise",
                subscription_status="active",
                email_verified=True,
            )
        )
        await session.commit()

        # Verify
        result = await session.execute(select(User).where(User.id == user.id))
        user = result.scalar_one()
        print("\n  Updated state:")
        print(f"    is_admin: {user.is_admin}")
        print(f"    subscription_tier: {user.subscription_tier}")
        print(f"    subscription_status: {user.subscription_status}")
        print(f"    email_verified: {user.email_verified}")
        print(f"\nUser '{email}' promoted to superuser successfully!")

    await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <email>")
        sys.exit(1)

    asyncio.run(promote_user(sys.argv[1]))
