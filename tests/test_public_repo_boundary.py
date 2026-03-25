from __future__ import annotations

import logging
from pathlib import Path

import pytest

import scripts.migrate_hosted_solo_users_to_personal_workspaces as migration_shim
from ace_platform.workers.workspace_backups_task import (
    backup_hosted_personal_workspaces_task,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_hosted_workspace_migration_script_redirects_to_private_repo(capsys) -> None:
    assert migration_shim.main([]) == 1

    captured = capsys.readouterr()
    assert "ace-private" in captured.err
    assert "public shim" in captured.err


def test_hosted_workspace_backup_task_redirects_to_private_repo(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="ace_platform.workers.workspace_backups_task")
    result = backup_hosted_personal_workspaces_task.run()

    assert result["status"] == "moved"
    assert "ace-private" in result["message"]
    assert "public repo shim" in caplog.text


def test_public_docs_point_hosted_implementation_to_private_repo() -> None:
    required_paths = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "docs" / "oss-overview.md",
        REPO_ROOT / "docs" / "local-quickstart.md",
        REPO_ROOT / "docs" / "SELF_HOSTED_DEPLOYMENT.md",
        REPO_ROOT / "web" / "README.md",
    ]

    for path in required_paths:
        assert "ace-private" in path.read_text(encoding="utf-8"), path


def test_public_repo_no_longer_carries_hosted_deploy_workflows_or_fly_configs() -> None:
    removed_paths = [
        REPO_ROOT / ".github" / "workflows" / "staging.yml",
        REPO_ROOT / ".github" / "workflows" / "production.yml",
        REPO_ROOT / "fly.toml",
        REPO_ROOT / "fly.staging.toml",
    ]

    for path in removed_paths:
        assert not path.exists(), path


def test_hosted_migration_docs_keep_private_repo_as_canonical_owner() -> None:
    migration_runbook = (
        REPO_ROOT / "docs" / "runbooks" / "hosted-personal-workspace-migration.md"
    ).read_text(encoding="utf-8")
    auth_cutover_runbook = (
        REPO_ROOT / "docs" / "runbooks" / "hosted-auth-cutover-compatibility.md"
    ).read_text(encoding="utf-8")

    assert "Owner:" in migration_runbook
    assert "Cleanup note:" in migration_runbook
    assert "ace-private" in auth_cutover_runbook
    assert "python scripts/migrate_hosted_solo_users_to_personal_workspaces.py" not in (
        auth_cutover_runbook
    )
