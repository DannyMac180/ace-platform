"""Tests for admin alerting functionality."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ace_platform.core.admin_alerts import (
    AlertResult,
    is_admin_alerts_enabled,
    send_daily_spend_summary,
)
from ace_platform.core.metering import (
    PlatformDailySummary,
    get_platform_daily_summary,
    get_top_users_by_spend,
    get_users_over_threshold,
)


class TestIsAdminAlertsEnabled:
    """Tests for is_admin_alerts_enabled."""

    def test_enabled_when_email_configured(self):
        """Test alerts are enabled when admin email is set."""
        with patch("ace_platform.core.admin_alerts.get_settings") as mock_settings:
            mock_settings.return_value.admin_alert_email = "admin@example.com"
            assert is_admin_alerts_enabled() is True

    def test_disabled_when_email_not_configured(self):
        """Test alerts are disabled when admin email is empty."""
        with patch("ace_platform.core.admin_alerts.get_settings") as mock_settings:
            mock_settings.return_value.admin_alert_email = ""
            assert is_admin_alerts_enabled() is False


class TestPlatformDailySummary:
    """Tests for get_platform_daily_summary."""

    @pytest.mark.asyncio
    async def test_returns_summary_for_day(self):
        """Test platform daily summary returns correct aggregations."""
        mock_db = AsyncMock()

        # Mock the query result
        mock_result = MagicMock()
        mock_result.one.return_value = MagicMock(
            total_users_active=10,
            total_requests=100,
            total_tokens=50000,
            total_cost_usd=Decimal("5.50"),
        )
        mock_db.execute.return_value = mock_result

        summary = await get_platform_daily_summary(mock_db)

        assert summary.total_users_active == 10
        assert summary.total_requests == 100
        assert summary.total_tokens == 50000
        assert summary.total_cost_usd == Decimal("5.50")

    @pytest.mark.asyncio
    async def test_defaults_to_today(self):
        """Test defaults to current day when no date provided."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one.return_value = MagicMock(
            total_users_active=0,
            total_requests=0,
            total_tokens=0,
            total_cost_usd=Decimal("0"),
        )
        mock_db.execute.return_value = mock_result

        summary = await get_platform_daily_summary(mock_db)

        # Should be today's date at midnight
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        assert summary.date.date() == today.date()


class TestTopUsersBySpend:
    """Tests for get_top_users_by_spend."""

    @pytest.mark.asyncio
    async def test_returns_users_ordered_by_spend(self):
        """Test returns users ordered by spend descending."""
        mock_db = AsyncMock()

        user1_id = uuid4()
        user2_id = uuid4()

        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(
                user_id=user1_id,
                email="highspender@example.com",
                subscription_tier="pro",
                total_cost_usd=Decimal("25.00"),
            ),
            MagicMock(
                user_id=user2_id,
                email="lowspender@example.com",
                subscription_tier="starter",
                total_cost_usd=Decimal("5.00"),
            ),
        ]
        mock_db.execute.return_value = mock_result

        users = await get_top_users_by_spend(mock_db, limit=5)

        assert len(users) == 2
        assert users[0].email == "highspender@example.com"
        assert users[0].total_cost_usd == Decimal("25.00")
        assert users[1].email == "lowspender@example.com"

    @pytest.mark.asyncio
    async def test_calculates_percent_of_limit(self):
        """Test calculates percentage of tier limit correctly."""
        mock_db = AsyncMock()

        user_id = uuid4()
        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(
                user_id=user_id,
                email="user@example.com",
                subscription_tier="starter",  # $9 limit
                total_cost_usd=Decimal("4.50"),  # 50% of limit
            ),
        ]
        mock_db.execute.return_value = mock_result

        users = await get_top_users_by_spend(mock_db, limit=5)

        assert len(users) == 1
        assert users[0].percent_of_limit == pytest.approx(50.0)


class TestUsersOverThreshold:
    """Tests for get_users_over_threshold."""

    @pytest.mark.asyncio
    async def test_returns_only_users_over_threshold(self):
        """Test only returns users over the specified threshold."""
        mock_db = AsyncMock()

        user1_id = uuid4()
        user2_id = uuid4()

        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(
                user_id=user1_id,
                email="over@example.com",
                subscription_tier="starter",  # $9 limit
                total_cost_usd=Decimal("5.00"),  # 55.5% - over 50%
            ),
            MagicMock(
                user_id=user2_id,
                email="under@example.com",
                subscription_tier="starter",  # $9 limit
                total_cost_usd=Decimal("4.00"),  # 44.4% - under 50%
            ),
        ]
        mock_db.execute.return_value = mock_result

        users = await get_users_over_threshold(mock_db, threshold_percent=50)

        assert len(users) == 1
        assert users[0].email == "over@example.com"

    @pytest.mark.asyncio
    async def test_sorted_by_percent_descending(self):
        """Test results are sorted by percentage descending."""
        mock_db = AsyncMock()

        user1_id = uuid4()
        user2_id = uuid4()

        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(
                user_id=user1_id,
                email="medium@example.com",
                subscription_tier="starter",  # $9 limit
                total_cost_usd=Decimal("6.00"),  # 66.7%
            ),
            MagicMock(
                user_id=user2_id,
                email="high@example.com",
                subscription_tier="starter",  # $9 limit
                total_cost_usd=Decimal("8.00"),  # 88.9%
            ),
        ]
        mock_db.execute.return_value = mock_result

        users = await get_users_over_threshold(mock_db, threshold_percent=50)

        assert len(users) == 2
        assert users[0].email == "high@example.com"  # Higher percentage first
        assert users[1].email == "medium@example.com"


class TestSendDailySpendSummary:
    """Tests for send_daily_spend_summary."""

    @pytest.mark.asyncio
    async def test_returns_error_when_not_configured(self):
        """Test returns error when admin alerts not configured."""
        mock_db = AsyncMock()

        with patch("ace_platform.core.admin_alerts.is_admin_alerts_enabled", return_value=False):
            result = await send_daily_spend_summary(mock_db)

        assert result.success is False
        assert "not configured" in result.error

    @pytest.mark.asyncio
    async def test_sends_email_when_configured(self):
        """Test sends email when admin email is configured."""
        mock_db = AsyncMock()

        mock_settings = MagicMock()
        mock_settings.admin_alert_email = "admin@example.com"
        mock_settings.admin_alert_slack_webhook = ""
        mock_settings.admin_alert_spend_threshold_pct = 50
        mock_settings.resend_api_key = "test_key"
        mock_settings.email_from_name = "ACE Platform"
        mock_settings.email_from_address = "noreply@test.com"

        with (
            patch("ace_platform.core.admin_alerts.is_admin_alerts_enabled", return_value=True),
            patch("ace_platform.core.admin_alerts.get_settings", return_value=mock_settings),
            patch(
                "ace_platform.core.admin_alerts.get_platform_daily_summary",
                return_value=PlatformDailySummary(
                    date=datetime.now(UTC),
                    total_users_active=5,
                    total_requests=50,
                    total_tokens=10000,
                    total_cost_usd=Decimal("2.50"),
                ),
            ),
            patch("ace_platform.core.admin_alerts.get_top_users_by_spend", return_value=[]),
            patch("ace_platform.core.admin_alerts.get_users_over_threshold", return_value=[]),
            patch(
                "ace_platform.core.admin_alerts._send_summary_email", return_value=True
            ) as mock_email,
        ):
            result = await send_daily_spend_summary(mock_db)

        assert result.success is True
        assert result.email_sent is True
        mock_email.assert_called_once()

    @pytest.mark.asyncio
    async def test_sends_slack_when_webhook_configured(self):
        """Test sends Slack notification when webhook is configured."""
        mock_db = AsyncMock()

        mock_settings = MagicMock()
        mock_settings.admin_alert_email = ""
        mock_settings.admin_alert_slack_webhook = "https://hooks.slack.com/services/test"
        mock_settings.admin_alert_spend_threshold_pct = 50

        with (
            patch("ace_platform.core.admin_alerts.is_admin_alerts_enabled", return_value=True),
            patch("ace_platform.core.admin_alerts.get_settings", return_value=mock_settings),
            patch(
                "ace_platform.core.admin_alerts.get_platform_daily_summary",
                return_value=PlatformDailySummary(
                    date=datetime.now(UTC),
                    total_users_active=5,
                    total_requests=50,
                    total_tokens=10000,
                    total_cost_usd=Decimal("2.50"),
                ),
            ),
            patch("ace_platform.core.admin_alerts.get_top_users_by_spend", return_value=[]),
            patch("ace_platform.core.admin_alerts.get_users_over_threshold", return_value=[]),
            patch(
                "ace_platform.core.admin_alerts._send_summary_slack", return_value=True
            ) as mock_slack,
        ):
            result = await send_daily_spend_summary(mock_db)

        assert result.success is True
        assert result.slack_sent is True
        mock_slack.assert_called_once()

    @pytest.mark.asyncio
    async def test_sends_both_email_and_slack_when_both_configured(self):
        """Test sends both email and Slack when both are configured."""
        mock_db = AsyncMock()

        mock_settings = MagicMock()
        mock_settings.admin_alert_email = "admin@example.com"
        mock_settings.admin_alert_slack_webhook = "https://hooks.slack.com/services/test"
        mock_settings.admin_alert_spend_threshold_pct = 50
        mock_settings.resend_api_key = "test_key"
        mock_settings.email_from_name = "ACE Platform"
        mock_settings.email_from_address = "noreply@test.com"

        with (
            patch("ace_platform.core.admin_alerts.is_admin_alerts_enabled", return_value=True),
            patch("ace_platform.core.admin_alerts.get_settings", return_value=mock_settings),
            patch(
                "ace_platform.core.admin_alerts.get_platform_daily_summary",
                return_value=PlatformDailySummary(
                    date=datetime.now(UTC),
                    total_users_active=5,
                    total_requests=50,
                    total_tokens=10000,
                    total_cost_usd=Decimal("2.50"),
                ),
            ),
            patch("ace_platform.core.admin_alerts.get_top_users_by_spend", return_value=[]),
            patch("ace_platform.core.admin_alerts.get_users_over_threshold", return_value=[]),
            patch(
                "ace_platform.core.admin_alerts._send_summary_email", return_value=True
            ) as mock_email,
            patch(
                "ace_platform.core.admin_alerts._send_summary_slack", return_value=True
            ) as mock_slack,
        ):
            result = await send_daily_spend_summary(mock_db)

        assert result.success is True
        assert result.email_sent is True
        assert result.slack_sent is True
        mock_email.assert_called_once()
        mock_slack.assert_called_once()


class TestAlertResult:
    """Tests for AlertResult dataclass."""

    def test_default_values(self):
        """Test default values for AlertResult."""
        result = AlertResult(success=True)
        assert result.success is True
        assert result.email_sent is False
        assert result.slack_sent is False
        assert result.error is None

    def test_with_all_values(self):
        """Test AlertResult with all values set."""
        result = AlertResult(
            success=True,
            email_sent=True,
            slack_sent=True,
            error=None,
        )
        assert result.success is True
        assert result.email_sent is True
        assert result.slack_sent is True
