from __future__ import annotations

import sys

from .celery_app import celery_app

DEFAULT_LOG_LEVEL_ARGS = ["-l", "info"]


def _run(command: str, argv: list[str] | None = None) -> int:
    """Start a Celery service without exposing module-path launch strings."""
    args = list(sys.argv[1:]) if argv is None else list(argv)
    if not args:
        args = DEFAULT_LOG_LEVEL_ARGS.copy()
    result = celery_app.start([command, *args])
    return 0 if result is None else int(result)


def worker_main(argv: list[str] | None = None) -> int:
    """Run the default worker service."""
    return _run("worker", argv)


def beat_main(argv: list[str] | None = None) -> int:
    """Run the periodic task scheduler service."""
    return _run("beat", argv)


def main(argv: list[str] | None = None) -> int:
    """Dispatch to the worker or beat entrypoint."""
    args = list(argv) if argv is not None else sys.argv[1:]
    if args and args[0] == "beat":
        return beat_main(args[1:])
    if args and args[0] == "worker":
        return worker_main(args[1:])
    return worker_main(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
