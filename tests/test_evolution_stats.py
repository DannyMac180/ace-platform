"""Tests for evolution statistics aggregation.

These tests verify:
1. Evolution summary aggregation
2. Daily evolution breakdown
3. Evolution stats grouped by playbook
4. Recent evolution activity formatting

These are unit tests that mock the database layer to ensure the
query construction and response mapping are correct.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ace_platform.core.evolution_stats import (
    get_evolution_by_day,
    get_evolution_by_playbook,
    get_evolution_summary,
    get_recent_evolutions,
)
from ace_platform.db.models import EvolutionJobStatus


class TestEvolutionSummary:
    """Tests for get_evolution_summary."""

    @pytest.mark.asyncio
    async def test_returns_summary_with_data(self):
        user_id = uuid4()
        mock_db = AsyncMock()

        mock_row = MagicMock()
        mock_row.total_evolutions = 12
        mock_row.completed_evolutions = 9
        mock_row.failed_evolutions = 2
        mock_row.running_evolutions = 1
        mock_row.queued_evolutions = 0
        mock_row.total_outcomes_processed = 34

        mock_result = MagicMock()
        mock_result.one.return_value = mock_row
        mock_db.execute.return_value = mock_result

        start = datetime(2026, 1, 1, tzinfo=UTC)
        end = datetime(2026, 2, 1, tzinfo=UTC)

        summary = await get_evolution_summary(mock_db, user_id, start, end)

        assert summary.user_id == user_id
        assert summary.start_date == start
        assert summary.end_date == end
        assert summary.total_evolutions == 12
        assert summary.completed_evolutions == 9
        assert summary.failed_evolutions == 2
        assert summary.running_evolutions == 1
        assert summary.queued_evolutions == 0
        assert summary.total_outcomes_processed == 34
        assert summary.success_rate == 9 / 12


class TestDailyEvolution:
    """Tests for get_evolution_by_day."""

    @pytest.mark.asyncio
    async def test_returns_daily_rows(self):
        user_id = uuid4()
        mock_db = AsyncMock()

        day1 = MagicMock()
        day1.date = datetime(2026, 2, 1, tzinfo=UTC)
        day1.total_evolutions = 3
        day1.completed = 2
        day1.failed = 1
        day1.running = 0
        day1.queued = 0

        day2 = MagicMock()
        day2.date = datetime(2026, 2, 2, tzinfo=UTC)
        day2.total_evolutions = 1
        day2.completed = 1
        day2.failed = 0
        day2.running = 0
        day2.queued = 0

        mock_result = MagicMock()
        mock_result.all.return_value = [day1, day2]
        mock_db.execute.return_value = mock_result

        daily = await get_evolution_by_day(mock_db, user_id)

        assert len(daily) == 2
        assert daily[0].total_evolutions == 3
        assert daily[0].completed == 2
        assert daily[1].date == day2.date
        assert daily[1].completed == 1


class TestEvolutionByPlaybook:
    """Tests for get_evolution_by_playbook."""

    @pytest.mark.asyncio
    async def test_returns_playbook_stats(self):
        user_id = uuid4()
        mock_db = AsyncMock()

        pb_id = uuid4()
        row = MagicMock()
        row.playbook_id = pb_id
        row.playbook_name = "My Playbook"
        row.total_evolutions = 4
        row.completed = 3
        row.failed = 1
        row.last_evolution_at = datetime(2026, 2, 2, tzinfo=UTC)

        mock_result = MagicMock()
        mock_result.all.return_value = [row]
        mock_db.execute.return_value = mock_result

        stats = await get_evolution_by_playbook(mock_db, user_id, limit=5)

        assert len(stats) == 1
        assert stats[0].playbook_id == pb_id
        assert stats[0].playbook_name == "My Playbook"
        assert stats[0].total_evolutions == 4
        assert stats[0].success_rate == 3 / 4
        assert stats[0].last_evolution_at == row.last_evolution_at


class TestRecentEvolutions:
    """Tests for get_recent_evolutions."""

    @pytest.mark.asyncio
    async def test_returns_recent_activity(self):
        user_id = uuid4()
        mock_db = AsyncMock()

        job_id = uuid4()
        playbook_id = uuid4()

        row = MagicMock()
        row.id = job_id
        row.playbook_id = playbook_id
        row.playbook_name = "Example Playbook"
        row.status = EvolutionJobStatus.COMPLETED
        row.outcomes_processed = 5
        row.from_version_number = 1
        row.to_version_number = 2
        row.activity_at = datetime(2026, 2, 2, tzinfo=UTC)
        row.completed_at = datetime(2026, 2, 2, tzinfo=UTC)
        row.error_message = None

        mock_result = MagicMock()
        mock_result.all.return_value = [row]
        mock_db.execute.return_value = mock_result

        recent = await get_recent_evolutions(mock_db, user_id, limit=10)

        assert len(recent) == 1
        assert recent[0].id == job_id
        assert recent[0].playbook_id == playbook_id
        assert recent[0].playbook_name == "Example Playbook"
        assert recent[0].status == EvolutionJobStatus.COMPLETED
        assert recent[0].started_at == row.activity_at
        assert recent[0].completed_at == row.completed_at

