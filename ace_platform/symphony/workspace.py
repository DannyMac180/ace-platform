"""Workspace lifecycle management for Symphony."""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from pathlib import Path

from ace_platform.symphony.config import HookConfig, WorkspaceConfig
from ace_platform.symphony.errors import HookError, WorkspaceError
from ace_platform.symphony.models import Workspace

logger = logging.getLogger(__name__)
SANITIZE_PATTERN = re.compile(r"[^A-Za-z0-9._-]")
TEMP_ARTIFACTS = ("tmp", ".elixir_ls")


class WorkspaceManager:
    """Create, validate, and clean per-issue workspaces."""

    def __init__(self, config: WorkspaceConfig, hooks: HookConfig) -> None:
        self._config = config
        self._hooks = hooks

    @property
    def root(self) -> Path:
        return self._config.root.expanduser().resolve()

    @staticmethod
    def sanitize_identifier(identifier: str) -> str:
        return SANITIZE_PATTERN.sub("_", identifier)

    def workspace_path_for_identifier(self, identifier: str) -> Path:
        key = self.sanitize_identifier(identifier)
        return (self.root / key).resolve()

    def _assert_within_root(self, path: Path) -> None:
        root = self.root
        if path == root:
            return
        if root not in path.parents:
            raise WorkspaceError(
                "invalid_workspace_cwd",
                f"Workspace path escapes configured root: {path}",
            )

    async def create_for_issue(self, identifier: str) -> Workspace:
        root = self.root
        root.mkdir(parents=True, exist_ok=True)
        path = self.workspace_path_for_identifier(identifier)
        self._assert_within_root(path)

        created_now = False
        if path.exists() and not path.is_dir():
            raise WorkspaceError(
                "invalid_workspace_path",
                f"Workspace path exists but is not a directory: {path}",
            )
        if not path.exists():
            path.mkdir(parents=True, exist_ok=False)
            created_now = True

        workspace = Workspace(
            path=path,
            workspace_key=self.sanitize_identifier(identifier),
            created_now=created_now,
        )
        if created_now and self._hooks.after_create:
            try:
                await self.run_hook("after_create", self._hooks.after_create, path, fatal=True)
            except HookError:
                shutil.rmtree(path, ignore_errors=True)
                raise
        return workspace

    async def prepare_for_run(self, workspace: Workspace) -> None:
        self._assert_within_root(workspace.path)
        self.remove_temp_artifacts(workspace.path)
        if self._hooks.before_run:
            await self.run_hook("before_run", self._hooks.before_run, workspace.path, fatal=True)

    async def after_run(self, workspace: Workspace) -> None:
        if self._hooks.after_run:
            await self.run_hook("after_run", self._hooks.after_run, workspace.path, fatal=False)

    async def remove_for_issue(self, identifier: str) -> None:
        path = self.workspace_path_for_identifier(identifier)
        if not path.exists():
            return
        self._assert_within_root(path)
        if self._hooks.before_remove:
            await self.run_hook("before_remove", self._hooks.before_remove, path, fatal=False)
        shutil.rmtree(path, ignore_errors=True)

    @staticmethod
    def remove_temp_artifacts(path: Path) -> None:
        for name in TEMP_ARTIFACTS:
            candidate = path / name
            if candidate.is_dir():
                shutil.rmtree(candidate, ignore_errors=True)
            elif candidate.exists():
                candidate.unlink(missing_ok=True)

    async def run_hook(self, name: str, script: str, cwd: Path, *, fatal: bool) -> None:
        logger.info("hook_started hook=%s cwd=%s", name, cwd)
        try:
            proc = await asyncio.create_subprocess_exec(
                "bash",
                "-lc",
                script,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise HookError("hook_spawn_failed", f"{name} hook failed to start: {exc}") from exc

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self._hooks.timeout_ms / 1000,
            )
        except asyncio.TimeoutError as exc:
            proc.kill()
            await proc.communicate()
            message = f"{name} hook timed out after {self._hooks.timeout_ms}ms"
            logger.warning("hook_timeout hook=%s cwd=%s", name, cwd)
            if fatal:
                raise HookError("hook_timeout", message) from exc
            return

        if proc.returncode != 0:
            message = (
                f"{name} hook failed with exit code {proc.returncode}: "
                f"{_truncate_hook_output(stdout, stderr)}"
            )
            logger.warning("hook_failed hook=%s cwd=%s returncode=%s", name, cwd, proc.returncode)
            if fatal:
                raise HookError("hook_failed", message)
            return

        logger.info("hook_completed hook=%s cwd=%s", name, cwd)


def _truncate_hook_output(stdout: bytes, stderr: bytes) -> str:
    merged = b"\n".join(part for part in (stdout, stderr) if part)
    text = merged.decode("utf-8", errors="replace").strip()
    if len(text) > 500:
        return f"{text[:497]}..."
    return text
