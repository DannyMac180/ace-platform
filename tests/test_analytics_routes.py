"""Tests for first-party analytics ingestion routes."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from ace_platform.api.routes.analytics import AnalyticsEventRequest, ingest_analytics_event
from ace_platform.core.rate_limit import RATE_LIMITS, rate_limit_analytics_events


class _DummyUser:
    def __init__(self):
        self.id = uuid4()


def _build_request(path: str = "/analytics/events") -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "scheme": "http",
        "server": ("testserver", 80),
    }
    return Request(scope)


class TestAnalyticsEventRequest:
    """Schema tests for analytics payloads."""

    def test_accepts_valid_event_type(self):
        payload = AnalyticsEventRequest(
            event_type="landing_view",
            event_id="evt_1",
            source="twitter",
        )
        assert payload.event_type.value == "landing_view"

    def test_rejects_invalid_event_type(self):
        with pytest.raises(ValidationError):
            AnalyticsEventRequest(event_type="not_real")


class TestAnalyticsIngestion:
    """Route-level ingestion tests with mocked DB session."""

    @pytest.mark.asyncio
    async def test_dedupes_by_event_id(self):
        db = AsyncMock()
        db.scalar = AsyncMock(return_value=uuid4())

        response = await ingest_analytics_event(
            payload=AnalyticsEventRequest(
                event_type="landing_view",
                event_id="evt_dedupe_1",
                source="x",
            ),
            request=_build_request(),
            db=db,
            user=None,
            _rate_limit=None,
        )

        assert response.accepted is True
        assert response.deduped is True
        assert response.event_id == "evt_dedupe_1"
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_normalizes_source_and_persists_event(self):
        db = AsyncMock()
        db.scalar = AsyncMock(return_value=None)

        response = await ingest_analytics_event(
            payload=AnalyticsEventRequest(
                event_type="register_start",
                event_id="evt_register_start_1",
                source="twitter",
                attribution={"utm_campaign": "launch"},
            ),
            request=_build_request(),
            db=db,
            user=_DummyUser(),
            _rate_limit=None,
        )

        assert response.accepted is True
        assert response.deduped is False
        db.add.assert_called_once()
        added_event = db.add.call_args.args[0]
        assert added_event.source == "x"
        assert added_event.channel == "social"
        assert added_event.campaign == "launch"
        db.commit.assert_awaited_once()


class TestAnalyticsRateLimit:
    """Tests for analytics rate limit configuration and dependency wiring."""

    def test_analytics_bucket_configured(self):
        assert RATE_LIMITS["analytics_events"]["limit"] == 120
        assert RATE_LIMITS["analytics_events"]["window_seconds"] == 60

    @pytest.mark.asyncio
    async def test_rate_limit_dependency_uses_analytics_bucket(self):
        request = _build_request()

        with patch(
            "ace_platform.core.rate_limit._check_rate_limit", new_callable=AsyncMock
        ) as check:
            await rate_limit_analytics_events(request)

            check.assert_awaited_once()
            await_args = check.await_args.kwargs
            assert await_args["action"] == "analytics_events"
            assert await_args["limit"] == 120
            assert await_args["window_seconds"] == 60
