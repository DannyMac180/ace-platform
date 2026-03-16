"""Module entrypoint for the vendored Symphony Elixir launcher."""

from __future__ import annotations

from ace_platform.symphony.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
