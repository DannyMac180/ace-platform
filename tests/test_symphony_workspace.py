from __future__ import annotations

from pathlib import Path

import pytest

from ace_platform.symphony.config import HookConfig, WorkspaceConfig
from ace_platform.symphony.errors import HookError, WorkspaceError
from ace_platform.symphony.workspace import WorkspaceManager


@pytest.mark.asyncio
async def test_workspace_manager_creates_and_reuses_workspace(tmp_path: Path):
    manager = WorkspaceManager(WorkspaceConfig(root=tmp_path / "workspaces"), HookConfig())

    created = await manager.create_for_issue("ACE/1")
    reused = await manager.create_for_issue("ACE/1")

    assert created.created_now is True
    assert reused.created_now is False
    assert created.workspace_key == "ACE_1"
    assert created.path.is_dir()


@pytest.mark.asyncio
async def test_workspace_after_create_failure_removes_workspace(tmp_path: Path):
    manager = WorkspaceManager(
        WorkspaceConfig(root=tmp_path / "workspaces"),
        HookConfig(after_create="exit 2"),
    )

    with pytest.raises(HookError, match="after_create"):
        await manager.create_for_issue("ACE-2")

    assert not (tmp_path / "workspaces" / "ACE-2").exists()


@pytest.mark.asyncio
async def test_workspace_rejects_non_directory_collision(tmp_path: Path):
    root = tmp_path / "workspaces"
    root.mkdir()
    collision = root / "ACE-3"
    collision.write_text("not a dir", encoding="utf-8")
    manager = WorkspaceManager(WorkspaceConfig(root=root), HookConfig())

    with pytest.raises(WorkspaceError, match="not a directory"):
        await manager.create_for_issue("ACE-3")


def test_workspace_temp_artifacts_removed(tmp_path: Path):
    path = tmp_path / "workspace"
    (path / "tmp").mkdir(parents=True)
    (path / ".elixir_ls").mkdir()

    WorkspaceManager.remove_temp_artifacts(path)

    assert not (path / "tmp").exists()
    assert not (path / ".elixir_ls").exists()
