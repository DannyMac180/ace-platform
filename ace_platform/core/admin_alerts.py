"""Admin alerting for high-spend users and daily summaries.

This module provides functions to send admin alerts for:
- Daily spend summaries (total platform spend, top users)
- Users approaching or exceeding their tier limits
- Unusual spending spikes

Alerts can be sent via:
- Email (using Resend)
- Slack webhook (optional)
"""

import logging
from dataclasses import dataclass
from html import escape as html_escape

import httpx
import resend
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.config import get_settings
from ace_platform.core.metering import (
    PlatformDailySummary,
    UserSpendSummary,
    get_platform_daily_summary,
    get_top_users_by_spend,
    get_users_over_threshold,
)

logger = logging.getLogger(__name__)


@dataclass
class AlertResult:
    """Result of sending an alert."""

    success: bool
    email_sent: bool = False
    slack_sent: bool = False
    error: str | None = None


def is_admin_alerts_enabled() -> bool:
    """Check if admin alerts are enabled (admin email configured)."""
    settings = get_settings()
    return bool(settings.admin_alert_email)


async def send_daily_spend_summary(db: AsyncSession) -> AlertResult:
    """Generate and send daily spend summary to admin.

    This function:
    1. Gets platform-wide spend for today
    2. Gets top 5 users by spend this month
    3. Gets users who exceeded the configured threshold
    4. Sends summary via email and/or Slack

    Args:
        db: Database session.

    Returns:
        AlertResult with status of alert delivery.
    """
    settings = get_settings()

    if not is_admin_alerts_enabled():
        logger.debug("Admin alerts not enabled, skipping daily summary")
        return AlertResult(success=False, error="Admin alerts not configured")

    try:
        # Gather data
        today_summary = await get_platform_daily_summary(db)
        top_users = await get_top_users_by_spend(db, limit=5)
        users_over_threshold = await get_users_over_threshold(
            db, threshold_percent=settings.admin_alert_spend_threshold_pct
        )

        # Send alerts
        email_sent = False
        slack_sent = False
        errors = []

        # Send email
        if settings.admin_alert_email:
            try:
                email_sent = await _send_summary_email(
                    settings.admin_alert_email,
                    today_summary,
                    top_users,
                    users_over_threshold,
                    settings.admin_alert_spend_threshold_pct,
                )
            except Exception as e:
                logger.error(f"Failed to send admin summary email: {e}")
                errors.append(f"Email: {e}")

        # Send Slack notification
        if settings.admin_alert_slack_webhook:
            try:
                slack_sent = await _send_summary_slack(
                    settings.admin_alert_slack_webhook,
                    today_summary,
                    top_users,
                    users_over_threshold,
                    settings.admin_alert_spend_threshold_pct,
                )
            except Exception as e:
                logger.error(f"Failed to send admin summary to Slack: {e}")
                errors.append(f"Slack: {e}")

        success = email_sent or slack_sent
        error = "; ".join(errors) if errors else None

        if success:
            logger.info(
                "Daily spend summary sent",
                extra={
                    "email_sent": email_sent,
                    "slack_sent": slack_sent,
                    "total_spend": str(today_summary.total_cost_usd),
                    "users_over_threshold": len(users_over_threshold),
                },
            )

        return AlertResult(
            success=success,
            email_sent=email_sent,
            slack_sent=slack_sent,
            error=error,
        )

    except Exception as e:
        logger.error(f"Failed to generate daily spend summary: {e}", exc_info=True)
        return AlertResult(success=False, error=str(e))


async def _send_summary_email(
    to_email: str,
    today_summary: PlatformDailySummary,
    top_users: list[UserSpendSummary],
    users_over_threshold: list[UserSpendSummary],
    threshold_pct: int,
) -> bool:
    """Send daily summary email to admin.

    Returns:
        True if email was sent successfully.
    """
    settings = get_settings()

    if not settings.resend_api_key:
        logger.warning("Resend API key not configured, skipping email")
        return False

    resend.api_key = settings.resend_api_key

    # Format date
    date_str = today_summary.date.strftime("%Y-%m-%d")

    # Build top users table
    top_users_html = ""
    if top_users:
        top_users_rows = ""
        for user in top_users:
            tier = html_escape(user.subscription_tier or "free")
            pct_str = f"{user.percent_of_limit:.1f}%" if user.percent_of_limit else "N/A"
            top_users_rows += f"""
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{html_escape(user.email)}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{tier}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">${user.total_cost_usd:.2f}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{pct_str}</td>
            </tr>
            """
        top_users_html = f"""
        <h2 style="color: #1a1a1a; font-size: 18px; margin-top: 24px;">Top 5 Users by Spend (This Month)</h2>
        <table style="width: 100%; border-collapse: collapse; margin-top: 12px;">
            <thead>
                <tr style="background: #f5f5f5;">
                    <th style="padding: 8px; text-align: left;">Email</th>
                    <th style="padding: 8px; text-align: left;">Tier</th>
                    <th style="padding: 8px; text-align: left;">Spend</th>
                    <th style="padding: 8px; text-align: left;">% of Limit</th>
                </tr>
            </thead>
            <tbody>
                {top_users_rows}
            </tbody>
        </table>
        """

    # Build threshold alert section
    threshold_html = ""
    if users_over_threshold:
        threshold_rows = ""
        for user in users_over_threshold:
            tier = html_escape(user.subscription_tier or "free")
            pct_str = f"{user.percent_of_limit:.1f}%" if user.percent_of_limit else "N/A"
            color = "#c41e3a" if (user.percent_of_limit or 0) >= 80 else "#b8860b"
            threshold_rows += f"""
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{html_escape(user.email)}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{tier}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">${user.total_cost_usd:.2f}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee; color: {color}; font-weight: bold;">{pct_str}</td>
            </tr>
            """
        threshold_html = f"""
        <h2 style="color: #c41e3a; font-size: 18px; margin-top: 24px;">
            Users Over {threshold_pct}% of Limit
        </h2>
        <table style="width: 100%; border-collapse: collapse; margin-top: 12px;">
            <thead>
                <tr style="background: #fff0f0;">
                    <th style="padding: 8px; text-align: left;">Email</th>
                    <th style="padding: 8px; text-align: left;">Tier</th>
                    <th style="padding: 8px; text-align: left;">Spend</th>
                    <th style="padding: 8px; text-align: left;">% of Limit</th>
                </tr>
            </thead>
            <tbody>
                {threshold_rows}
            </tbody>
        </table>
        """

    html_content = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h1 style="color: #1a1a1a; font-size: 24px; margin-bottom: 20px;">
            Daily Spend Summary - {date_str}
        </h1>

        <div style="background: #f8f8f8; padding: 20px; border-radius: 8px; margin-bottom: 24px;">
            <h2 style="color: #1a1a1a; font-size: 16px; margin: 0 0 16px 0;">Today's Platform Totals</h2>
            <table style="width: 100%;">
                <tr>
                    <td style="padding: 4px 0; color: #666;">Active Users</td>
                    <td style="padding: 4px 0; text-align: right; font-weight: bold;">{today_summary.total_users_active}</td>
                </tr>
                <tr>
                    <td style="padding: 4px 0; color: #666;">Total Requests</td>
                    <td style="padding: 4px 0; text-align: right; font-weight: bold;">{today_summary.total_requests:,}</td>
                </tr>
                <tr>
                    <td style="padding: 4px 0; color: #666;">Total Tokens</td>
                    <td style="padding: 4px 0; text-align: right; font-weight: bold;">{today_summary.total_tokens:,}</td>
                </tr>
                <tr>
                    <td style="padding: 4px 0; color: #666;">Total Spend</td>
                    <td style="padding: 4px 0; text-align: right; font-weight: bold; font-size: 18px; color: #1e7a4d;">${today_summary.total_cost_usd:.2f}</td>
                </tr>
            </table>
        </div>

        {threshold_html}
        {top_users_html}

        <p style="color: #9ca3af; font-size: 12px; margin-top: 30px;">
            This is an automated alert from ACE Platform.
            Threshold alerts are triggered at {threshold_pct}% of tier spending limits.
        </p>
    </div>
    """

    result = resend.Emails.send(
        {
            "from": f"{settings.email_from_name} <{settings.email_from_address}>",
            "to": [to_email],
            "subject": f"[ACE Platform] Daily Spend Summary - ${today_summary.total_cost_usd:.2f}",
            "html": html_content,
        }
    )

    logger.info(f"Daily summary email sent to {to_email}", extra={"message_id": result.get("id")})
    return True


async def _send_summary_slack(
    webhook_url: str,
    today_summary: PlatformDailySummary,
    top_users: list[UserSpendSummary],
    users_over_threshold: list[UserSpendSummary],
    threshold_pct: int,
) -> bool:
    """Send daily summary to Slack webhook.

    Returns:
        True if message was sent successfully.
    """
    date_str = today_summary.date.strftime("%Y-%m-%d")

    # Build message blocks
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Daily Spend Summary - {date_str}",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Active Users:* {today_summary.total_users_active}"},
                {"type": "mrkdwn", "text": f"*Total Requests:* {today_summary.total_requests:,}"},
                {"type": "mrkdwn", "text": f"*Total Tokens:* {today_summary.total_tokens:,}"},
                {"type": "mrkdwn", "text": f"*Total Spend:* ${today_summary.total_cost_usd:.2f}"},
            ],
        },
    ]

    # Add threshold alerts
    if users_over_threshold:
        user_list = "\n".join(
            f"- {u.email} ({u.subscription_tier or 'free'}): ${u.total_cost_usd:.2f} ({u.percent_of_limit:.1f}%)"
            for u in users_over_threshold[:5]
        )
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*:warning: Users Over {threshold_pct}% Limit:*\n{user_list}",
                },
            }
        )

    # Add top users
    if top_users:
        user_list = "\n".join(f"- {u.email}: ${u.total_cost_usd:.2f}" for u in top_users[:5])
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Top 5 Users (This Month):*\n{user_list}",
                },
            }
        )

    # Send to Slack
    async with httpx.AsyncClient() as client:
        response = await client.post(
            webhook_url,
            json={"blocks": blocks},
            timeout=10.0,
        )
        response.raise_for_status()

    logger.info("Daily summary sent to Slack")
    return True
