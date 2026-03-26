"""Promote a user to superuser (admin + enterprise tier)."""

from __future__ import annotations

import argparse
import asyncio
import os


def normalize_database_url(database_url: str) -> str:
    """Normalize DB URLs for SQLAlchemy async engine."""
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return database_url


def _load_database_url() -> str | None:
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return database_url

    from dotenv import load_dotenv

    load_dotenv()
    return os.environ.get("DATABASE_URL")


async def promote_user(email: str) -> int:
    from sqlalchemy import select, update
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    database_url = _load_database_url()
    if not database_url:
        print("ERROR: DATABASE_URL not set. Set it in .env or environment.")
        return 1

    engine = create_async_engine(normalize_database_url(database_url))
    try:
        async with AsyncSession(engine) as session:
            from ace_platform.db.models import User

            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()

            if not user:
                print(f"ERROR: No user found with email '{email}'")
                return 1

            print(f"Found user: {user.email} (id: {user.id})")
            print("  Current state:")
            print(f"    is_admin: {user.is_admin}")
            print(f"    subscription_tier: {user.subscription_tier}")
            print(f"    subscription_status: {user.subscription_status}")
            print(f"    email_verified: {user.email_verified}")

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

            result = await session.execute(select(User).where(User.id == user.id))
            user = result.scalar_one()
            print("\n  Updated state:")
            print(f"    is_admin: {user.is_admin}")
            print(f"    subscription_tier: {user.subscription_tier}")
            print(f"    subscription_status: {user.subscription_status}")
            print(f"    email_verified: {user.email_verified}")
            print(f"\nUser '{email}' promoted to superuser successfully!")
            return 0
    finally:
        await engine.dispose()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ace-admin promote-superuser",
        description="Promote a user to superuser (admin + enterprise tier).",
    )
    parser.add_argument("email", help="User email to promote.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(promote_user(args.email))
