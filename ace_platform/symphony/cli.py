"""Launch the vendored OpenAI Symphony Elixir runtime."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_WORKFLOW = "WORKFLOW.md"
ELIXIR_ROOT_ENV = "ACE_SYMPHONY_ELIXIR_ROOT"


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    elixir_root = _elixir_root()
    runtime_args = _normalize_runtime_args(args_list, Path.cwd())

    if args_list and args_list[0] == "setup":
        return _bootstrap(elixir_root)

    if _bootstrap_if_needed(elixir_root) != 0:
        return 1

    if shutil.which("mise") is None:
        print(
            "The official Symphony Elixir runtime requires `mise` on PATH. "
            "Install `mise`, then rerun `symphony`.",
            file=sys.stderr,
        )
        return 1

    command = ["mise", "exec", "--", "./bin/symphony", *runtime_args]
    try:
        completed = subprocess.run(command, cwd=elixir_root)
    except KeyboardInterrupt:
        return 0
    except OSError as exc:
        print(f"Unable to launch Symphony Elixir: {exc}", file=sys.stderr)
        return 1
    return completed.returncode


def _bootstrap_if_needed(elixir_root: Path) -> int:
    if _binary_path(elixir_root).exists():
        return 0
    print(
        "Bootstrapping the vendored OpenAI Symphony Elixir runtime...",
        file=sys.stderr,
    )
    return _bootstrap(elixir_root)


def _bootstrap(elixir_root: Path) -> int:
    if not elixir_root.exists():
        print(f"Symphony Elixir sources not found at {elixir_root}", file=sys.stderr)
        return 1

    if shutil.which("mise") is None:
        print(
            "The official Symphony Elixir runtime requires `mise` for setup. "
            "Install `mise`, then rerun `symphony setup`.",
            file=sys.stderr,
        )
        return 1

    for command in _bootstrap_commands():
        try:
            subprocess.run(command, cwd=elixir_root, check=True)
        except subprocess.CalledProcessError as exc:
            print(
                f"Symphony Elixir setup failed while running: {' '.join(command)}", file=sys.stderr
            )
            return exc.returncode or 1
        except OSError as exc:
            print(f"Unable to run {' '.join(command)}: {exc}", file=sys.stderr)
            return 1
    return 0


def _bootstrap_commands() -> tuple[list[str], ...]:
    return (
        ["mise", "trust"],
        ["mise", "install"],
        ["mise", "exec", "--", "mix", "setup"],
        ["mise", "exec", "--", "mix", "build"],
    )


def _binary_path(elixir_root: Path) -> Path:
    return elixir_root / "bin" / "symphony"


def _elixir_root() -> Path:
    override = os.environ.get(ELIXIR_ROOT_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "vendor" / "symphony-elixir"


def _normalize_runtime_args(args_list: list[str], invocation_cwd: Path) -> list[str]:
    if not args_list:
        return [str((invocation_cwd / DEFAULT_WORKFLOW).resolve())]

    normalized: list[str] = []
    index = 0

    while index < len(args_list):
        arg = args_list[index]

        if arg == "--logs-root":
            normalized.append(arg)
            if index + 1 < len(args_list):
                normalized.append(str((invocation_cwd / args_list[index + 1]).resolve()))
            index += 2
            continue

        if arg == "--port":
            normalized.append(arg)
            if index + 1 < len(args_list):
                normalized.append(args_list[index + 1])
            index += 2
            continue

        if arg.startswith("-"):
            normalized.append(arg)
            index += 1
            continue

        normalized.append(str((invocation_cwd / arg).resolve()))
        normalized.extend(args_list[index + 1 :])
        return normalized

    normalized.append(str((invocation_cwd / DEFAULT_WORKFLOW).resolve()))
    return normalized
