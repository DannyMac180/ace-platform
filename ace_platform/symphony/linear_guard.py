"""Validate that Symphony is pointed at the expected Linear workspace context."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_LINEAR_ENDPOINT = "https://api.linear.app/graphql"
WORKFLOW_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
PROBE_QUERY = """
query SymphonyWorkspaceGuard($projectSlug: String!, $teamKey: String!) {
  viewer {
    id
    name
    organization {
      id
      name
      urlKey
    }
  }
  teams(filter: {key: {eq: $teamKey}}, first: 5) {
    nodes {
      id
      key
      name
    }
  }
  projects(filter: {slugId: {eq: $projectSlug}}, first: 5) {
    nodes {
      id
      name
      slugId
      teams {
        nodes {
          id
          key
          name
        }
      }
    }
  }
}
"""


class LinearGuardError(RuntimeError):
    """Raised when the current Linear context does not match expectations."""


@dataclass(frozen=True)
class LinearGuardResult:
    workspace_name: str
    workspace_url_key: str
    project_name: str
    project_slug_id: str
    team_key: str


def load_workflow_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    match = WORKFLOW_RE.match(text)
    if not match:
        raise LinearGuardError(f"{path} is missing YAML frontmatter")
    frontmatter_text, _body = match.groups()
    data = yaml.safe_load(frontmatter_text) or {}
    if not isinstance(data, dict):
        raise LinearGuardError(f"{path} frontmatter must decode to a mapping")
    return data


def workflow_project_slug(path: Path) -> str:
    frontmatter = load_workflow_frontmatter(path)
    tracker = frontmatter.get("tracker")
    if not isinstance(tracker, dict):
        raise LinearGuardError(f"{path} is missing a tracker mapping")

    project_slug = tracker.get("project_slug")
    if not isinstance(project_slug, str) or not project_slug.strip():
        raise LinearGuardError(f"{path} is missing tracker.project_slug")
    return project_slug.strip()


def build_probe_payload(project_slug: str, team_key: str) -> dict[str, Any]:
    return {
        "query": PROBE_QUERY,
        "variables": {
            "projectSlug": project_slug,
            "teamKey": team_key,
        },
    }


def post_graphql_request(
    endpoint: str,
    token: str,
    payload: dict[str, Any],
    timeout: float = 30.0,
) -> dict[str, Any]:
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": token,
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise LinearGuardError(
            f"Linear workspace guard request failed with HTTP {exc.code}: {detail or 'no response body'}"
        ) from exc
    except urllib.error.URLError as exc:
        raise LinearGuardError(f"Linear workspace guard request failed: {exc.reason}") from exc

    errors = body.get("errors")
    if isinstance(errors, list) and errors:
        messages = [
            error.get("message", "unknown GraphQL error")
            for error in errors
            if isinstance(error, dict)
        ]
        raise LinearGuardError(
            "Linear workspace guard received GraphQL errors: "
            + "; ".join(messages or ["unknown error"])
        )

    data = body.get("data")
    if not isinstance(data, dict):
        raise LinearGuardError("Linear workspace guard received an unexpected GraphQL payload")
    return data


def validate_probe_data(
    data: dict[str, Any],
    expected_workspace_url_key: str,
    expected_team_key: str,
    project_slug: str,
) -> LinearGuardResult:
    viewer = data.get("viewer")
    organization = viewer.get("organization") if isinstance(viewer, dict) else None
    workspace_url_key = organization.get("urlKey") if isinstance(organization, dict) else None
    workspace_name = organization.get("name") if isinstance(organization, dict) else None

    normalized_expected_workspace = expected_workspace_url_key.strip().lower()
    normalized_expected_team = expected_team_key.strip().upper()
    actual_workspace = (
        workspace_url_key.strip().lower() if isinstance(workspace_url_key, str) else None
    )

    problems: list[str] = []

    if actual_workspace != normalized_expected_workspace:
        problems.append(
            "expected Linear workspace "
            f"'{expected_workspace_url_key}', got '{workspace_url_key or 'unknown'}'"
        )

    team_nodes = data.get("teams", {}).get("nodes", [])
    matching_team = next(
        (
            team
            for team in team_nodes
            if isinstance(team, dict)
            and str(team.get("key", "")).upper() == normalized_expected_team
        ),
        None,
    )
    if matching_team is None:
        problems.append(
            f"expected Linear team key '{expected_team_key}' was not found in the connected workspace"
        )

    project_nodes = data.get("projects", {}).get("nodes", [])
    if not isinstance(project_nodes, list) or not project_nodes:
        problems.append(
            f"configured project slug '{project_slug}' was not found in the connected workspace"
        )
    elif len(project_nodes) > 1:
        problems.append(
            f"configured project slug '{project_slug}' resolved to multiple projects in the connected workspace"
        )

    project = project_nodes[0] if isinstance(project_nodes, list) and project_nodes else None
    if isinstance(project, dict):
        project_team_nodes = project.get("teams", {}).get("nodes", [])
        project_team_keys = {
            str(team.get("key", "")).upper()
            for team in project_team_nodes
            if isinstance(team, dict) and isinstance(team.get("key"), str)
        }
        if normalized_expected_team not in project_team_keys:
            problems.append(
                "configured project "
                f"'{project.get('name', project_slug)}' is not attached to Linear team '{expected_team_key}'"
            )

    if problems:
        raise LinearGuardError("Linear workspace guard failed: " + "; ".join(problems))

    return LinearGuardResult(
        workspace_name=str(workspace_name or expected_workspace_url_key),
        workspace_url_key=str(workspace_url_key or expected_workspace_url_key),
        project_name=str(project.get("name") if isinstance(project, dict) else project_slug),
        project_slug_id=str(project.get("slugId") if isinstance(project, dict) else project_slug),
        team_key=normalized_expected_team,
    )


def run_guard(
    workflow_path: Path,
    expected_workspace_url_key: str,
    expected_team_key: str,
    *,
    endpoint: str = DEFAULT_LINEAR_ENDPOINT,
    token: str | None = None,
    request_fn: Any = post_graphql_request,
) -> LinearGuardResult:
    effective_token = token or os.environ.get("LINEAR_API_KEY")
    if not effective_token:
        raise LinearGuardError("LINEAR_API_KEY is not set in the current shell")

    project_slug = workflow_project_slug(workflow_path)
    payload = build_probe_payload(project_slug, expected_team_key)
    data = request_fn(endpoint, effective_token, payload)
    return validate_probe_data(data, expected_workspace_url_key, expected_team_key, project_slug)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate that the current Linear API key points Symphony at the expected workspace.",
    )
    parser.add_argument(
        "--workflow", required=True, type=Path, help="Rendered Symphony workflow file to inspect."
    )
    parser.add_argument(
        "--expected-workspace-url-key",
        required=True,
        help="Expected Linear workspace URL key, for example 'danmac'.",
    )
    parser.add_argument(
        "--expected-team-key",
        required=True,
        help="Expected Linear team key for the configured project, for example 'DAN'.",
    )
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_LINEAR_ENDPOINT,
        help="Linear GraphQL endpoint to probe.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = run_guard(
            args.workflow,
            args.expected_workspace_url_key,
            args.expected_team_key,
            endpoint=args.endpoint,
        )
    except LinearGuardError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(
        "Linear workspace guard passed: "
        f"workspace='{result.workspace_url_key}' "
        f"project='{result.project_name}' "
        f"team='{result.team_key}'"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
