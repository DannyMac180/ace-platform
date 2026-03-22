#!/usr/bin/env python3
"""Compatibility shim for the hosted-workspace migration script."""

from __future__ import annotations

import sys

MOVED_MESSAGE = (
    "Hosted solo-user workspace migration moved to ace-private. "
    "Run the canonical migration script from the private repo instead of this public shim."
)


def main(argv: list[str] | None = None) -> int:
    """Print the hosted/private repo redirect and exit non-zero."""

    del argv
    print(MOVED_MESSAGE, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
