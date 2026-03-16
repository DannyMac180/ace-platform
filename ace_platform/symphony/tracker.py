"""Linear-compatible tracker client for Symphony."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any

import httpx

from ace_platform.symphony.config import TrackerConfig
from ace_platform.symphony.errors import TrackerError
from ace_platform.symphony.models import BlockerRef, Issue

CANDIDATE_QUERY = """
query SymphonyCandidateIssues($projectSlug: String!, $states: [String!]!, $first: Int!, $after: String) {
  issues(
    first: $first
    after: $after
    filter: {
      project: { slugId: { eq: $projectSlug } }
      state: { name: { in: $states } }
    }
  ) {
    nodes {
      id
      identifier
      title
      description
      priority
      branchName
      url
      createdAt
      updatedAt
      state { name }
      labels { nodes { name } }
      relations(filter: { type: { eq: blocks }, inverse: { eq: true } }) {
        nodes {
          relatedIssue {
            id
            identifier
            state { name }
          }
        }
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
""".strip()

STATE_QUERY = """
query SymphonyIssuesByStates($projectSlug: String!, $states: [String!]!, $first: Int!, $after: String) {
  issues(
    first: $first
    after: $after
    filter: {
      project: { slugId: { eq: $projectSlug } }
      state: { name: { in: $states } }
    }
  ) {
    nodes {
      id
      identifier
      title
      description
      priority
      branchName
      url
      createdAt
      updatedAt
      state { name }
      labels { nodes { name } }
      relations(filter: { type: { eq: blocks }, inverse: { eq: true } }) {
        nodes {
          relatedIssue {
            id
            identifier
            state { name }
          }
        }
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
""".strip()

STATE_REFRESH_QUERY = """
query SymphonyIssueStatesByIds($ids: [ID!]!) {
  issues(filter: { id: { in: $ids } }) {
    nodes {
      id
      identifier
      title
      description
      priority
      branchName
      url
      createdAt
      updatedAt
      state { name }
      labels { nodes { name } }
      relations(filter: { type: { eq: blocks }, inverse: { eq: true } }) {
        nodes {
          relatedIssue {
            id
            identifier
            state { name }
          }
        }
      }
    }
  }
}
""".strip()


class LinearTrackerClient:
    """Tracker adapter that reads issues from Linear."""

    def __init__(
        self,
        config: TrackerConfig,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config
        self._client = client

    async def fetch_candidate_issues(self) -> list[Issue]:
        return await self._paginate_issues(CANDIDATE_QUERY, self._config.active_states)

    async def fetch_issues_by_states(self, state_names: Sequence[str]) -> list[Issue]:
        if not state_names:
            return []
        return await self._paginate_issues(STATE_QUERY, tuple(state_names))

    async def fetch_issue_states_by_ids(self, issue_ids: Sequence[str]) -> list[Issue]:
        if not issue_ids:
            return []
        payload = await self.execute_graphql(
            STATE_REFRESH_QUERY,
            {"ids": list(issue_ids)},
        )
        issue_nodes = payload.get("issues", {}).get("nodes")
        if not isinstance(issue_nodes, list):
            raise TrackerError(
                "linear_unknown_payload", "Linear issue refresh payload was malformed"
            )
        return [normalize_issue(node) for node in issue_nodes]

    async def execute_raw_graphql(self, query: str, variables: Any = None) -> dict[str, Any]:
        """Execute one raw GraphQL operation for the optional dynamic tool bridge."""

        if not isinstance(query, str) or not query.strip():
            raise TrackerError("linear_graphql_errors", "GraphQL query must be a non-empty string")
        if isinstance(variables, dict) or variables is None:
            parsed_variables = variables
        else:
            raise TrackerError("linear_graphql_errors", "GraphQL variables must be an object")
        return await self.execute_graphql(query, parsed_variables)

    async def execute_graphql(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        client = self._client or httpx.AsyncClient(timeout=30.0)
        should_close = self._client is None
        headers = {
            "Authorization": self._config.api_key or "",
            "Content-Type": "application/json",
        }
        try:
            response = await client.post(
                self._config.endpoint,
                headers=headers,
                json={"query": query, "variables": variables or {}},
            )
        except httpx.HTTPError as exc:
            raise TrackerError("linear_api_request", str(exc)) from exc
        finally:
            if should_close:
                await client.aclose()

        if response.status_code != 200:
            raise TrackerError(
                "linear_api_status",
                f"Linear request failed with HTTP {response.status_code}",
            )

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise TrackerError(
                "linear_unknown_payload", "Linear response was not valid JSON"
            ) from exc

        if not isinstance(payload, dict):
            raise TrackerError("linear_unknown_payload", "Linear response payload was malformed")
        if payload.get("errors"):
            raise TrackerError("linear_graphql_errors", json.dumps(payload["errors"]))

        data = payload.get("data")
        if not isinstance(data, dict):
            raise TrackerError("linear_unknown_payload", "Linear response missing data object")
        return data

    async def _paginate_issues(self, query: str, states: Sequence[str]) -> list[Issue]:
        issues: list[Issue] = []
        after: str | None = None
        while True:
            payload = await self.execute_graphql(
                query,
                {
                    "projectSlug": self._config.project_slug,
                    "states": list(states),
                    "first": 50,
                    "after": after,
                },
            )
            container = payload.get("issues")
            if not isinstance(container, dict):
                raise TrackerError("linear_unknown_payload", "Linear issues payload was malformed")
            nodes = container.get("nodes")
            page_info = container.get("pageInfo")
            if not isinstance(nodes, list) or not isinstance(page_info, dict):
                raise TrackerError("linear_unknown_payload", "Linear issues page was malformed")
            issues.extend(normalize_issue(node) for node in nodes)
            has_next_page = bool(page_info.get("hasNextPage"))
            end_cursor = page_info.get("endCursor")
            if not has_next_page:
                return issues
            if not end_cursor:
                raise TrackerError(
                    "linear_missing_end_cursor",
                    "Linear pagination missing endCursor for next page",
                )
            after = str(end_cursor)


def normalize_issue(node: dict[str, Any]) -> Issue:
    """Normalize a Linear issue node into the Symphony issue model."""

    state = _nested_name(node.get("state"))
    if not state:
        raise TrackerError("linear_unknown_payload", "Issue missing state.name")

    labels_node = (
        node.get("labels", {}).get("nodes") if isinstance(node.get("labels"), dict) else []
    )
    labels = tuple(
        str(label.get("name")).strip().lower()
        for label in labels_node or []
        if isinstance(label, dict) and label.get("name")
    )

    blockers: list[BlockerRef] = []
    relations = (
        node.get("relations", {}).get("nodes") if isinstance(node.get("relations"), dict) else []
    )
    for relation in relations or []:
        if not isinstance(relation, dict):
            continue
        related_issue = relation.get("relatedIssue")
        if not isinstance(related_issue, dict):
            continue
        blockers.append(
            BlockerRef(
                id=str(related_issue.get("id")) if related_issue.get("id") else None,
                identifier=str(related_issue.get("identifier"))
                if related_issue.get("identifier")
                else None,
                state=_nested_name(related_issue.get("state")),
            )
        )

    priority = node.get("priority")
    normalized_priority = priority if isinstance(priority, int) else None
    return Issue(
        id=str(node["id"]),
        identifier=str(node["identifier"]),
        title=str(node["title"]),
        description=str(node["description"]) if node.get("description") is not None else None,
        priority=normalized_priority,
        state=state,
        branch_name=str(node["branchName"]) if node.get("branchName") is not None else None,
        url=str(node["url"]) if node.get("url") is not None else None,
        labels=labels,
        blocked_by=tuple(blockers),
        created_at=_parse_timestamp(node.get("createdAt")),
        updated_at=_parse_timestamp(node.get("updatedAt")),
    )


def _nested_name(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    name = value.get("name")
    if name is None:
        return None
    return str(name)


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
