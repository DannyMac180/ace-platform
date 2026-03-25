"""Support `python -m ace_platform.admin ...` package-owned admin commands."""

from ace_platform.admin.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
