from __future__ import annotations

import httpx
import pytest

from ace_platform.symphony.config import TrackerConfig
from ace_platform.symphony.errors import TrackerError
from ace_platform.symphony.tracker import LinearTrackerClient


def _tracker_config() -> TrackerConfig:
    return TrackerConfig(
        kind="linear",
        endpoint="https://api.linear.app/graphql",
        api_key="token",
        project_slug="ace",
        active_states=("Todo", "In Progress"),
        terminal_states=("Done",),
    )


@pytest.mark.asyncio
async def test_fetch_issues_by_states_empty_short_circuits():
    called = False

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"data": {}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tracker = LinearTrackerClient(_tracker_config(), client=client)

    issues = await tracker.fetch_issues_by_states([])

    assert issues == []
    assert called is False
    await client.aclose()


@pytest.mark.asyncio
async def test_candidate_fetch_paginates_and_normalizes_labels_and_blockers():
    responses = [
        {
            "data": {
                "issues": {
                    "nodes": [
                        {
                            "id": "1",
                            "identifier": "ACE-1",
                            "title": "First",
                            "description": None,
                            "priority": 2,
                            "branchName": "ace-1",
                            "url": "https://example.com/1",
                            "createdAt": "2026-03-01T10:00:00Z",
                            "updatedAt": "2026-03-01T12:00:00Z",
                            "state": {"name": "Todo"},
                            "labels": {"nodes": [{"name": "Bug"}]},
                            "relations": {
                                "nodes": [
                                    {
                                        "relatedIssue": {
                                            "id": "2",
                                            "identifier": "ACE-2",
                                            "state": {"name": "In Progress"},
                                        }
                                    }
                                ]
                            },
                        }
                    ],
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"},
                }
            }
        },
        {
            "data": {
                "issues": {
                    "nodes": [
                        {
                            "id": "3",
                            "identifier": "ACE-3",
                            "title": "Second",
                            "description": "desc",
                            "priority": None,
                            "branchName": None,
                            "url": None,
                            "createdAt": "2026-03-02T10:00:00Z",
                            "updatedAt": "2026-03-02T12:00:00Z",
                            "state": {"name": "In Progress"},
                            "labels": {"nodes": [{"name": "Feature"}]},
                            "relations": {"nodes": []},
                        }
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        },
    ]

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=responses.pop(0))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tracker = LinearTrackerClient(_tracker_config(), client=client)

    issues = await tracker.fetch_candidate_issues()

    assert [issue.identifier for issue in issues] == ["ACE-1", "ACE-3"]
    assert issues[0].labels == ("bug",)
    assert issues[0].blocked_by[0].identifier == "ACE-2"
    await client.aclose()


@pytest.mark.asyncio
async def test_tracker_raises_on_graphql_errors():
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errors": [{"message": "bad"}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tracker = LinearTrackerClient(_tracker_config(), client=client)

    with pytest.raises(TrackerError, match="bad"):
        await tracker.fetch_candidate_issues()

    await client.aclose()
