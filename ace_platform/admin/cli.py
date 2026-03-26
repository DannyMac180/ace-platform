"""CLI entrypoints for ACE Platform admin operations."""

from __future__ import annotations

import argparse


def _run_promote_superuser(args: argparse.Namespace) -> int:
    from ace_platform.admin.promote_superuser import main as promote_superuser_main

    return promote_superuser_main([args.email])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ace-admin",
        description="Package-owned admin commands for ACE Platform operators.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    promote_superuser_parser = subparsers.add_parser(
        "promote-superuser",
        help="Promote a user to a superuser with enterprise access.",
    )
    promote_superuser_parser.add_argument("email", help="User email to promote.")
    promote_superuser_parser.set_defaults(handler=_run_promote_superuser)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)
