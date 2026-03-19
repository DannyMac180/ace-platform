from __future__ import annotations

from pathlib import Path

import pytest

from ace_platform.symphony.linear_guard import (
    LinearGuardError,
    build_probe_payload,
    run_guard,
    validate_probe_data,
    workflow_project_slug,
)


def _write_workflow(path: Path, project_slug: str = "ace-v2-4fe95176a1f5") -> None:
    path.write_text(
        (f'---\ntracker:\n  kind: linear\n  project_slug: "{project_slug}"\n---\nPrompt body\n'),
        encoding="utf-8",
    )


def test_workflow_project_slug_reads_from_frontmatter(tmp_path: Path) -> None:
    workflow_path = tmp_path / "WORKFLOW.md"
    _write_workflow(workflow_path)

    assert workflow_project_slug(workflow_path) == "ace-v2-4fe95176a1f5"


def test_build_probe_payload_uses_project_slug_and_team_key() -> None:
    payload = build_probe_payload("ace-v2-4fe95176a1f5", "DAN")

    assert payload["variables"] == {
        "projectSlug": "ace-v2-4fe95176a1f5",
        "teamKey": "DAN",
    }
    assert "viewer" in payload["query"]
    assert "projects" in payload["query"]


def test_validate_probe_data_accepts_expected_workspace_and_team() -> None:
    result = validate_probe_data(
        {
            "viewer": {
                "organization": {
                    "name": "danmac",
                    "urlKey": "danmac",
                }
            },
            "teams": {
                "nodes": [
                    {"key": "DAN", "name": "Danmac"},
                ]
            },
            "projects": {
                "nodes": [
                    {
                        "name": "ACE v2",
                        "slugId": "4fe95176a1f5",
                        "teams": {
                            "nodes": [
                                {"key": "DAN", "name": "Danmac"},
                            ]
                        },
                    }
                ]
            },
        },
        "danmac",
        "DAN",
        "ace-v2-4fe95176a1f5",
    )

    assert result.workspace_url_key == "danmac"
    assert result.project_name == "ACE v2"
    assert result.team_key == "DAN"


def test_validate_probe_data_rejects_wrong_workspace() -> None:
    with pytest.raises(
        LinearGuardError, match="expected Linear workspace 'danmac', got 'dannymac'"
    ):
        validate_probe_data(
            {
                "viewer": {
                    "organization": {
                        "name": "dannymac",
                        "urlKey": "dannymac",
                    }
                },
                "teams": {"nodes": [{"key": "DAN", "name": "Danmac"}]},
                "projects": {
                    "nodes": [
                        {
                            "name": "ACE v2",
                            "slugId": "4fe95176a1f5",
                            "teams": {"nodes": [{"key": "DAN", "name": "Danmac"}]},
                        }
                    ]
                },
            },
            "danmac",
            "DAN",
            "ace-v2-4fe95176a1f5",
        )


def test_validate_probe_data_rejects_project_outside_expected_team() -> None:
    with pytest.raises(LinearGuardError, match="is not attached to Linear team 'DAN'"):
        validate_probe_data(
            {
                "viewer": {
                    "organization": {
                        "name": "danmac",
                        "urlKey": "danmac",
                    }
                },
                "teams": {"nodes": [{"key": "DAN", "name": "Danmac"}]},
                "projects": {
                    "nodes": [
                        {
                            "name": "ACE v2",
                            "slugId": "4fe95176a1f5",
                            "teams": {"nodes": [{"key": "OPS", "name": "Ops"}]},
                        }
                    ]
                },
            },
            "danmac",
            "DAN",
            "ace-v2-4fe95176a1f5",
        )


def test_run_guard_uses_workflow_project_slug_and_request_fn(tmp_path: Path) -> None:
    workflow_path = tmp_path / "WORKFLOW.md"
    _write_workflow(workflow_path)
    calls: list[tuple[str, str, dict[str, object]]] = []

    def fake_request(endpoint: str, token: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append((endpoint, token, payload))
        return {
            "viewer": {"organization": {"name": "danmac", "urlKey": "danmac"}},
            "teams": {"nodes": [{"key": "DAN", "name": "Danmac"}]},
            "projects": {
                "nodes": [
                    {
                        "name": "ACE v2",
                        "slugId": "4fe95176a1f5",
                        "teams": {"nodes": [{"key": "DAN", "name": "Danmac"}]},
                    }
                ]
            },
        }

    result = run_guard(
        workflow_path,
        "danmac",
        "DAN",
        endpoint="https://example.test/graphql",
        token="lin_api_test",
        request_fn=fake_request,
    )

    assert result.workspace_url_key == "danmac"
    assert calls == [
        (
            "https://example.test/graphql",
            "lin_api_test",
            build_probe_payload("ace-v2-4fe95176a1f5", "DAN"),
        )
    ]
