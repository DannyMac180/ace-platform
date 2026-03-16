from __future__ import annotations

from pathlib import Path

import pytest

from ace_platform.symphony.config import config_from_workflow, validate_dispatch_config
from ace_platform.symphony.errors import ConfigError, WorkflowError
from ace_platform.symphony.models import Issue
from ace_platform.symphony.workflow import load_workflow_definition, render_issue_prompt


def test_load_workflow_with_front_matter(tmp_path: Path):
    workflow_path = tmp_path / "WORKFLOW.md"
    workflow_path.write_text(
        "---\ntracker:\n  kind: linear\n  api_key: test\n  project_slug: ace\n---\nHello {{ issue.identifier }}",
        encoding="utf-8",
    )

    workflow = load_workflow_definition(workflow_path)

    assert workflow.config["tracker"]["kind"] == "linear"
    assert workflow.prompt_template == "Hello {{ issue.identifier }}"


def test_load_workflow_rejects_non_map_front_matter(tmp_path: Path):
    workflow_path = tmp_path / "WORKFLOW.md"
    workflow_path.write_text("---\n- nope\n---\nbody", encoding="utf-8")

    with pytest.raises(WorkflowError, match="front matter"):
        load_workflow_definition(workflow_path)


def test_render_issue_prompt_is_strict(tmp_path: Path):
    workflow_path = tmp_path / "WORKFLOW.md"
    workflow_path.write_text(
        "---\ntracker:\n  kind: linear\n  api_key: test\n  project_slug: ace\n---\n{{ issue.missing_field }}",
        encoding="utf-8",
    )
    workflow = load_workflow_definition(workflow_path)

    with pytest.raises(WorkflowError, match="missing_field"):
        render_issue_prompt(
            workflow,
            Issue(id="1", identifier="ACE-1", title="Title", state="Todo"),
            attempt=None,
        )


def test_config_defaults_and_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workflow_path = tmp_path / "WORKFLOW.md"
    workflow_path.write_text(
        "---\ntracker:\n  kind: linear\n  api_key: $LINEAR_API_KEY\n  project_slug: ace\n---\nbody",
        encoding="utf-8",
    )
    monkeypatch.setenv("LINEAR_API_KEY", "env-token")

    workflow = load_workflow_definition(workflow_path)
    config = config_from_workflow(workflow, workflow_path)
    validate_dispatch_config(config)

    assert config.tracker.endpoint == "https://api.linear.app/graphql"
    assert config.agent.max_turns == 20
    assert config.codex.command == "codex app-server"
    assert config.tracker.api_key == "env-token"


def test_config_validation_rejects_missing_tracker_kind(tmp_path: Path):
    workflow_path = tmp_path / "WORKFLOW.md"
    workflow_path.write_text("---\ntracker:\n  api_key: test\n---\nbody", encoding="utf-8")
    workflow = load_workflow_definition(workflow_path)
    config = config_from_workflow(workflow, workflow_path)

    with pytest.raises(ConfigError, match="tracker.kind"):
        validate_dispatch_config(config)
