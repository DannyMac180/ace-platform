#!/usr/bin/env python3
"""Compatibility shim for the package-owned superuser promotion entrypoint.

Supported invocation:
    source venv/bin/activate && pip install -e .
    source venv/bin/activate && ace-admin promote-superuser mcateerd2@gmail.com

Compatibility shim:
    source venv/bin/activate && python scripts/promote_superuser.py mcateerd2@gmail.com
"""

from __future__ import annotations

import subprocess
import sys

PACKAGE_COMMAND = ["-m", "ace_platform.admin", "promote-superuser"]


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    completed = subprocess.run([sys.executable, *PACKAGE_COMMAND, *args], check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
