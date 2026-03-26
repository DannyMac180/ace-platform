"""Tests for package-owned superuser promotion entrypoints."""

from __future__ import annotations

import inspect
import sys
from types import SimpleNamespace

import ace_platform.admin.cli as admin_cli
import scripts.promote_superuser as promote_superuser_shim
from ace_platform.admin.promote_superuser import normalize_database_url


def test_normalize_database_url_converts_postgresql_scheme():
    url = "postgresql://user:pass@localhost:5432/ace_platform"
    assert (
        normalize_database_url(url) == "postgresql+asyncpg://user:pass@localhost:5432/ace_platform"
    )


def test_normalize_database_url_converts_postgres_scheme():
    url = "postgres://user:pass@localhost:5432/ace_platform"
    assert (
        normalize_database_url(url) == "postgresql+asyncpg://user:pass@localhost:5432/ace_platform"
    )


def test_normalize_database_url_leaves_async_urls_unchanged():
    url = "postgresql+asyncpg://user:pass@localhost:5432/ace_platform"
    assert normalize_database_url(url) == url


def test_admin_cli_dispatches_to_package_promote_superuser(monkeypatch):
    captured: dict[str, list[str]] = {}

    def fake_main(argv: list[str] | None = None) -> int:
        captured["argv"] = [] if argv is None else argv
        return 0

    monkeypatch.setattr("ace_platform.admin.promote_superuser.main", fake_main)

    assert admin_cli.main(["promote-superuser", "operator@example.com"]) == 0
    assert captured["argv"] == ["operator@example.com"]


def test_promote_superuser_script_is_a_package_wrapper_without_sys_path_injection(monkeypatch):
    observed: dict[str, object] = {}

    def fake_run(args: list[str], check: bool) -> SimpleNamespace:
        observed["args"] = args
        observed["check"] = check
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(promote_superuser_shim.subprocess, "run", fake_run)

    assert "sys.path.insert" not in inspect.getsource(promote_superuser_shim)
    assert promote_superuser_shim.main(["operator@example.com"]) == 0
    assert observed["args"] == [
        sys.executable,
        "-m",
        "ace_platform.admin",
        "promote-superuser",
        "operator@example.com",
    ]
    assert observed["check"] is False
