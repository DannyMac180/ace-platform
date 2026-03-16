"""Module entrypoint for `python -m ace_platform.symphony`."""

from __future__ import annotations

from ace_platform.symphony.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
