#!/usr/bin/env python3
"""Backfill hosted solo users into hosted personal workspaces."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def normalize_database_url(database_url: str) -> str:
    """Normalize DB URLs for SQLAlchemy async usage."""

    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    else:
        return database_url

    parsed = urlsplit(database_url)
    query_params = parse_qsl(parsed.query, keep_blank_values=True)
    sslmode_values = [value for key, value in query_params if key == "sslmode"]
    filtered_params = [(key, value) for key, value in query_params if key != "sslmode"]

    if "disable" in sslmode_values and not any(key == "ssl" for key, _ in filtered_params):
        filtered_params.append(("ssl", "disable"))

    return urlunsplit(parsed._replace(query=urlencode(filtered_params, doseq=True)))


def load_database_url() -> str:
    """Resolve the database URL from environment or .env."""

    load_dotenv()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("ERROR: DATABASE_URL is not set.")
    return normalize_database_url(database_url)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(
        description="Migrate existing hosted solo users to hosted personal workspaces.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("migrate", "validate"),
        default="migrate",
        help="Run the backfill or validation mode.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute migration actions without writing any database changes.",
    )
    parser.add_argument(
        "--email",
        dest="emails",
        action="append",
        default=[],
        help="Restrict the run to one or more user emails.",
    )
    return parser.parse_args(argv)


async def run(args: argparse.Namespace) -> int:
    """Execute the requested command."""

    from ace_platform.core.workspaces import (
        migrate_existing_hosted_solo_users_to_personal_workspaces,
        validate_hosted_solo_users_personal_workspaces,
    )

    engine = create_async_engine(load_database_url())
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            if args.command == "validate":
                summary = await validate_hosted_solo_users_personal_workspaces(
                    session,
                    emails=args.emails,
                )
                print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
                return 0 if summary.invalid_count == 0 else 1

            summary = await migrate_existing_hosted_solo_users_to_personal_workspaces(
                session,
                emails=args.emails,
                dry_run=args.dry_run,
            )
            if args.dry_run:
                await session.rollback()
            else:
                await session.commit()
            print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
            return 0
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""

    return asyncio.run(run(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
