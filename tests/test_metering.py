"""Tests for usage metering and aggregation.

These tests verify:
1. Usage summary aggregation
2. Daily usage breakdown
3. Usage grouped by playbook
4. Usage grouped by operation
5. Usage grouped by model
6. Billing period comprehensive data
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ace_platform.core.metering import (
    DailyUsage,
    OperationUsage,
    PlaybookUsage,
    UsageSummary,
    get_billing_period_usage,
    get_usage_by_model,
    get_usage_by_operation,
    get_usage_by_playbook,
    get_user_usage_by_day,
    get_user_usage_summary,
)


class TestUsageSummary:
    """Tests for get_user_usage_summary."""

    @pytest.mark.asyncio
    async def test_returns_summary_with_data(self):
        """Test that summary returns aggregated data."""
        user_id = uuid4()
        mock_db = AsyncMock()

        # Mock the query result
        mock_row = MagicMock()
        mock_row.total_requests = 100
        mock_row.total_prompt_tokens = 50000
        mock_row.total_completion_tokens = 25000
        mock_row.total_tokens = 75000
        mock_row.total_cost_usd = Decimal("1.50")

        mock_result = MagicMock()
        mock_result.one.return_value = mock_row
        mock_db.execute.return_value = mock_result

        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 31, tzinfo=UTC)

        summary = await get_user_usage_summary(mock_db, user_id, start, end)

        assert isinstance(summary, UsageSummary)
        assert summary.user_id == user_id
        assert summary.total_requests == 100
        assert summary.total_prompt_tokens == 50000
        assert summary.total_completion_tokens == 25000
        assert summary.total_tokens == 75000
        assert summary.total_cost_usd == Decimal("1.50")

    @pytest.mark.asyncio
    async def test_defaults_to_30_days(self):
        """Test that default date range is 30 days."""
        user_id = uuid4()
        mock_db = AsyncMock()

        mock_row = MagicMock()
        mock_row.total_requests = 0
        mock_row.total_prompt_tokens = 0
        mock_row.total_completion_tokens = 0
        mock_row.total_tokens = 0
        mock_row.total_cost_usd = Decimal("0")

        mock_result = MagicMock()
        mock_result.one.return_value = mock_row
        mock_db.execute.return_value = mock_result

        summary = await get_user_usage_summary(mock_db, user_id)

        # Check that dates were set
        assert summary.start_date is not None
        assert summary.end_date is not None
        # End date should be close to now
        assert (datetime.now(UTC) - summary.end_date).total_seconds() < 5
        # Start date should be ~30 days before end
        delta = summary.end_date - summary.start_date
        assert 29 <= delta.days <= 31

    @pytest.mark.asyncio
    async def test_zero_usage_returns_zeros(self):
        """Test that zero usage returns zero values."""
        user_id = uuid4()
        mock_db = AsyncMock()

        mock_row = MagicMock()
        mock_row.total_requests = 0
        mock_row.total_prompt_tokens = 0
        mock_row.total_completion_tokens = 0
        mock_row.total_tokens = 0
        mock_row.total_cost_usd = Decimal("0")

        mock_result = MagicMock()
        mock_result.one.return_value = mock_row
        mock_db.execute.return_value = mock_result

        summary = await get_user_usage_summary(mock_db, user_id)

        assert summary.total_requests == 0
        assert summary.total_tokens == 0
        assert summary.total_cost_usd == Decimal("0")


class TestDailyUsage:
    """Tests for get_user_usage_by_day."""

    @pytest.mark.asyncio
    async def test_returns_daily_breakdown(self):
        """Test that daily breakdown returns list of DailyUsage."""
        user_id = uuid4()
        mock_db = AsyncMock()

        # Mock multiple days of data
        day1 = datetime(2024, 1, 1, tzinfo=UTC)
        day2 = datetime(2024, 1, 2, tzinfo=UTC)

        mock_rows = [
            MagicMock(
                date=day1,
                request_count=10,
                prompt_tokens=5000,
                completion_tokens=2500,
                total_tokens=7500,
                cost_usd=Decimal("0.15"),
            ),
            MagicMock(
                date=day2,
                request_count=20,
                prompt_tokens=10000,
                completion_tokens=5000,
                total_tokens=15000,
                cost_usd=Decimal("0.30"),
            ),
        ]

        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows
        mock_db.execute.return_value = mock_result

        daily = await get_user_usage_by_day(mock_db, user_id, day1, day2)

        assert len(daily) == 2
        assert all(isinstance(d, DailyUsage) for d in daily)
        assert daily[0].date == day1
        assert daily[0].request_count == 10
        assert daily[1].date == day2
        assert daily[1].request_count == 20

    @pytest.mark.asyncio
    async def test_empty_period_returns_empty_list(self):
        """Test that empty period returns empty list."""
        user_id = uuid4()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        daily = await get_user_usage_by_day(mock_db, user_id)

        assert daily == []


class TestPlaybookUsage:
    """Tests for get_usage_by_playbook."""

    @pytest.mark.asyncio
    async def test_returns_usage_by_playbook(self):
        """Test that usage is grouped by playbook."""
        user_id = uuid4()
        playbook_id = uuid4()
        mock_db = AsyncMock()

        mock_rows = [
            MagicMock(
                playbook_id=playbook_id,
                playbook_name="My Playbook",
                request_count=50,
                total_tokens=50000,
                cost_usd=Decimal("1.00"),
            ),
            MagicMock(
                playbook_id=None,
                playbook_name=None,
                request_count=10,
                total_tokens=5000,
                cost_usd=Decimal("0.10"),
            ),
        ]

        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows
        mock_db.execute.return_value = mock_result

        by_playbook = await get_usage_by_playbook(mock_db, user_id)

        assert len(by_playbook) == 2
        assert all(isinstance(p, PlaybookUsage) for p in by_playbook)
        assert by_playbook[0].playbook_id == playbook_id
        assert by_playbook[0].playbook_name == "My Playbook"
        assert by_playbook[1].playbook_id is None


class TestOperationUsage:
    """Tests for get_usage_by_operation."""

    @pytest.mark.asyncio
    async def test_returns_usage_by_operation(self):
        """Test that usage is grouped by operation."""
        user_id = uuid4()
        mock_db = AsyncMock()

        mock_rows = [
            MagicMock(
                operation="evolution_generator",
                request_count=30,
                total_tokens=30000,
                cost_usd=Decimal("0.60"),
            ),
            MagicMock(
                operation="evolution_reflector",
                request_count=30,
                total_tokens=20000,
                cost_usd=Decimal("0.40"),
            ),
            MagicMock(
                operation="evolution_curator",
                request_count=10,
                total_tokens=10000,
                cost_usd=Decimal("0.20"),
            ),
        ]

        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows
        mock_db.execute.return_value = mock_result

        by_operation = await get_usage_by_operation(mock_db, user_id)

        assert len(by_operation) == 3
        assert all(isinstance(o, OperationUsage) for o in by_operation)
        assert by_operation[0].operation == "evolution_generator"
        assert by_operation[1].operation == "evolution_reflector"
        assert by_operation[2].operation == "evolution_curator"


class TestModelUsage:
    """Tests for get_usage_by_model."""

    @pytest.mark.asyncio
    async def test_returns_usage_by_model(self):
        """Test that usage is grouped by model."""
        user_id = uuid4()
        mock_db = AsyncMock()

        mock_rows = [
            MagicMock(
                model="gpt-4o",
                request_count=50,
                total_tokens=50000,
                cost_usd=Decimal("0.75"),
            ),
            MagicMock(
                model="gpt-4o-mini",
                request_count=100,
                total_tokens=100000,
                cost_usd=Decimal("0.10"),
            ),
        ]

        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows
        mock_db.execute.return_value = mock_result

        by_model = await get_usage_by_model(mock_db, user_id)

        assert len(by_model) == 2
        assert by_model[0]["model"] == "gpt-4o"
        assert by_model[0]["request_count"] == 50
        assert by_model[1]["model"] == "gpt-4o-mini"


class TestBillingPeriodUsage:
    """Tests for get_billing_period_usage."""

    @pytest.mark.asyncio
    async def test_returns_comprehensive_data(self):
        """Test that billing period returns all usage data."""
        user_id = uuid4()
        mock_db = AsyncMock()

        # Mock all the query results
        mock_summary_row = MagicMock()
        mock_summary_row.total_requests = 100
        mock_summary_row.total_prompt_tokens = 50000
        mock_summary_row.total_completion_tokens = 25000
        mock_summary_row.total_tokens = 75000
        mock_summary_row.total_cost_usd = Decimal("1.50")

        mock_summary_result = MagicMock()
        mock_summary_result.one.return_value = mock_summary_row

        mock_empty_result = MagicMock()
        mock_empty_result.all.return_value = []

        # Return different results for each query
        mock_db.execute.side_effect = [
            mock_summary_result,  # Summary
            mock_empty_result,  # Daily
            mock_empty_result,  # By playbook
            mock_empty_result,  # By operation
            mock_empty_result,  # By model
        ]

        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 31, tzinfo=UTC)

        result = await get_billing_period_usage(mock_db, user_id, start, end)

        assert "summary" in result
        assert "daily" in result
        assert "by_playbook" in result
        assert "by_operation" in result
        assert "by_model" in result
        assert isinstance(result["summary"], UsageSummary)
        assert result["summary"].total_requests == 100


class TestDataclasses:
    """Tests for dataclass structure."""

    def test_usage_summary_fields(self):
        """Test UsageSummary has expected fields."""
        user_id = uuid4()
        now = datetime.now(UTC)
        summary = UsageSummary(
            user_id=user_id,
            start_date=now,
            end_date=now,
            total_requests=10,
            total_prompt_tokens=1000,
            total_completion_tokens=500,
            total_tokens=1500,
            total_cost_usd=Decimal("0.05"),
        )
        assert summary.user_id == user_id
        assert summary.total_requests == 10

    def test_daily_usage_fields(self):
        """Test DailyUsage has expected fields."""
        now = datetime.now(UTC)
        daily = DailyUsage(
            date=now,
            request_count=5,
            prompt_tokens=500,
            completion_tokens=250,
            total_tokens=750,
            cost_usd=Decimal("0.02"),
        )
        assert daily.request_count == 5

    def test_playbook_usage_fields(self):
        """Test PlaybookUsage has expected fields."""
        playbook_id = uuid4()
        usage = PlaybookUsage(
            playbook_id=playbook_id,
            playbook_name="Test",
            request_count=10,
            total_tokens=1000,
            cost_usd=Decimal("0.03"),
        )
        assert usage.playbook_name == "Test"

    def test_operation_usage_fields(self):
        """Test OperationUsage has expected fields."""
        usage = OperationUsage(
            operation="test_op",
            request_count=10,
            total_tokens=1000,
            cost_usd=Decimal("0.03"),
        )
        assert usage.operation == "test_op"
