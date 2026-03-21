from __future__ import annotations

import argparse

import uvicorn

from ace_platform.config import get_settings

from .main import create_app


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for the API service entrypoint."""
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Run the ACE Platform API via an installed package entrypoint."
    )
    parser.add_argument("--host", default=settings.api_host)
    parser.add_argument("--port", type=int, default=settings.api_port)
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Run the API with uvicorn reload support for local development.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the FastAPI service using package-owned defaults."""
    args = build_parser().parse_args(argv)
    if args.reload:
        uvicorn.run(
            "ace_platform.api.main:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            reload=True,
        )
    else:
        uvicorn.run(create_app(), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
