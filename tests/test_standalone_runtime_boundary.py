from __future__ import annotations

import ast
import types
from pathlib import Path
from unittest.mock import patch

import tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
EVOLUTION_PATH = REPO_ROOT / "ace_platform" / "core" / "evolution.py"


def test_root_package_exposes_service_entrypoints() -> None:
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    scripts = pyproject["project"]["scripts"]

    assert scripts["ace-platform-api"] == "ace_platform.api.__main__:main"
    assert scripts["ace-platform-worker"] == "ace_platform.workers.__main__:worker_main"
    assert scripts["ace-platform-beat"] == "ace_platform.workers.__main__:beat_main"


def test_evolution_service_uses_packaged_ace_core_imports() -> None:
    tree = ast.parse(EVOLUTION_PATH.read_text(encoding="utf-8"), filename=str(EVOLUTION_PATH))
    imported_modules: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module or "")

    disallowed = {
        "playbook_utils",
        "ace.core.curator",
        "ace.core.reflector",
        "sys",
        "pathlib",
    }
    assert imported_modules.isdisjoint(disallowed)
    assert "ace_core.playbook_utils" in imported_modules
    assert "ace_core" in imported_modules


def test_api_entrypoint_runs_uvicorn_with_package_defaults(monkeypatch) -> None:
    from ace_platform.api import __main__ as api_main

    sentinel_app = object()
    monkeypatch.setattr(
        api_main,
        "get_settings",
        lambda: types.SimpleNamespace(api_host="127.0.0.1", api_port=9010),
    )
    monkeypatch.setattr(api_main, "create_app", lambda: sentinel_app)

    with patch.object(api_main.uvicorn, "run") as run_mock:
        assert api_main.main([]) == 0

    run_mock.assert_called_once_with(sentinel_app, host="127.0.0.1", port=9010)


def test_api_entrypoint_supports_reload(monkeypatch) -> None:
    from ace_platform.api import __main__ as api_main

    monkeypatch.setattr(
        api_main,
        "get_settings",
        lambda: types.SimpleNamespace(api_host="0.0.0.0", api_port=8000),
    )

    with patch.object(api_main.uvicorn, "run") as run_mock:
        assert api_main.main(["--reload", "--host", "127.0.0.1", "--port", "9020"]) == 0

    run_mock.assert_called_once_with(
        "ace_platform.api.main:create_app",
        factory=True,
        host="127.0.0.1",
        port=9020,
        reload=True,
    )


def test_worker_entrypoint_uses_celery_start() -> None:
    from ace_platform.workers import __main__ as workers_main

    with patch.object(workers_main.celery_app, "start") as start_mock:
        assert workers_main.worker_main([]) == 0

    start_mock.assert_called_once_with(["worker", "-l", "info"])


def test_worker_console_script_preserves_cli_args(monkeypatch) -> None:
    from ace_platform.workers import __main__ as workers_main

    monkeypatch.setattr(workers_main.sys, "argv", ["ace-platform-worker", "-Q", "evolution"])

    with patch.object(workers_main.celery_app, "start") as start_mock:
        assert workers_main.worker_main() == 0

    start_mock.assert_called_once_with(["worker", "-Q", "evolution"])


def test_worker_entrypoint_dispatches_beat_mode() -> None:
    from ace_platform.workers import __main__ as workers_main

    with patch.object(workers_main.celery_app, "start") as start_mock:
        assert workers_main.main(["beat", "-l", "debug"]) == 0

    start_mock.assert_called_once_with(["beat", "-l", "debug"])


def test_beat_console_script_preserves_cli_args(monkeypatch) -> None:
    from ace_platform.workers import __main__ as workers_main

    monkeypatch.setattr(workers_main.sys, "argv", ["ace-platform-beat", "-l", "warning"])

    with patch.object(workers_main.celery_app, "start") as start_mock:
        assert workers_main.beat_main() == 0

    start_mock.assert_called_once_with(["beat", "-l", "warning"])
