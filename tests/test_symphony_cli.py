from __future__ import annotations

import subprocess
from pathlib import Path

from ace_platform.symphony.cli import main


def test_main_bootstraps_and_runs_default_workflow(tmp_path: Path, monkeypatch):
    elixir_root = tmp_path / "vendor" / "symphony-elixir"
    elixir_root.mkdir(parents=True)
    workflow_path = tmp_path / "WORKFLOW.md"
    workflow_path.write_text("---\ntracker:\n  kind: linear\n---\n", encoding="utf-8")
    calls: list[tuple[tuple[str, ...], Path, bool]] = []

    monkeypatch.setenv("ACE_SYMPHONY_ELIXIR_ROOT", str(elixir_root))
    monkeypatch.setattr("ace_platform.symphony.cli.shutil.which", lambda name: "/usr/bin/mise")
    monkeypatch.chdir(tmp_path)

    def fake_run(command: list[str], cwd: Path, check: bool = False):
        calls.append((tuple(command), cwd, check))
        if command == ["mise", "exec", "--", "mix", "build"]:
            bin_dir = elixir_root / "bin"
            bin_dir.mkdir()
            binary_path = bin_dir / "symphony"
            binary_path.write_text("#!/bin/sh\n", encoding="utf-8")
            binary_path.chmod(0o755)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("ace_platform.symphony.cli.subprocess.run", fake_run)

    exit_code = main([])

    assert exit_code == 0
    assert calls == [
        (("mise", "trust"), elixir_root, True),
        (("mise", "install"), elixir_root, True),
        (("mise", "exec", "--", "mix", "setup"), elixir_root, True),
        (("mise", "exec", "--", "mix", "build"), elixir_root, True),
        (
            ("mise", "exec", "--", "./bin/symphony", str(workflow_path.resolve())),
            elixir_root,
            False,
        ),
    ]


def test_main_resolves_relative_workflow_and_logs_root_paths(tmp_path: Path, monkeypatch):
    elixir_root = tmp_path / "vendor" / "symphony-elixir"
    bin_dir = elixir_root / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "symphony").write_text("#!/bin/sh\n", encoding="utf-8")
    workflow_path = tmp_path / "config" / "WORKFLOW.md"
    workflow_path.parent.mkdir()
    workflow_path.write_text("---\ntracker:\n  kind: linear\n---\n", encoding="utf-8")
    calls: list[tuple[tuple[str, ...], Path, bool]] = []

    monkeypatch.setenv("ACE_SYMPHONY_ELIXIR_ROOT", str(elixir_root))
    monkeypatch.setattr("ace_platform.symphony.cli.shutil.which", lambda name: "/usr/bin/mise")
    monkeypatch.chdir(tmp_path)

    def fake_run(command: list[str], cwd: Path, check: bool = False):
        calls.append((tuple(command), cwd, check))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("ace_platform.symphony.cli.subprocess.run", fake_run)

    exit_code = main(
        [
            "--i-understand-that-this-will-be-running-without-the-usual-guardrails",
            "--port",
            "4000",
            "--logs-root",
            "log",
            "config/WORKFLOW.md",
        ]
    )

    assert exit_code == 0
    assert calls == [
        (
            (
                "mise",
                "exec",
                "--",
                "./bin/symphony",
                "--i-understand-that-this-will-be-running-without-the-usual-guardrails",
                "--port",
                "4000",
                "--logs-root",
                str((tmp_path / "log").resolve()),
                str(workflow_path.resolve()),
            ),
            elixir_root,
            False,
        )
    ]


def test_setup_command_requires_mise(tmp_path: Path, monkeypatch, capsys):
    elixir_root = tmp_path / "vendor" / "symphony-elixir"
    elixir_root.mkdir(parents=True)

    monkeypatch.setenv("ACE_SYMPHONY_ELIXIR_ROOT", str(elixir_root))
    monkeypatch.setattr("ace_platform.symphony.cli.shutil.which", lambda name: None)

    exit_code = main(["setup"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "requires `mise`" in captured.err
