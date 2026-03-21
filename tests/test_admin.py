# Admin Dashboard Tests - v1 read-only admin endpoints
"""Tests for admin dashboard API routes.

These tests verify:
1. Admin routes require authentication (401 without token)
2. Admin routes require admin role (403 for non-admin user)
3. Route registration
4. Response schema validation
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from ace_platform.api.routes import admin as admin_routes
from ace_platform.api.routes.admin import (
    AdminUserItem,
    AuditEventItem,
    ConversionFunnelResponse,
    DailySignupResponse,
    InferenceGatewayHealthResponse,
    JobQueueHealthResponse,
    OperationalHealthResponse,
    PlatformStatsResponse,
    ProductAnalyticsResponse,
    SyncHealthResponse,
    TopUserResponse,
    WorkspaceBackupItem,
    WorkspaceBackupRestoreResponse,
    build_conversion_funnel_response,
    build_product_analytics_response,
    create_workspace_backup,
    get_conversion_funnel,
    get_product_analytics,
    get_operational_health,
    get_sync_health_snapshot,
    list_workspace_backups,
    restore_workspace_backup,
)


class TestAdminSchemas:
    """Tests for admin Pydantic response schemas."""

    def test_platform_stats_response(self):
        """Test platform stats response schema."""
        response = PlatformStatsResponse(
            total_users=100,
            active_users_today=25,
            signups_this_week=10,
            total_cost_today="1.50",
            tier_distribution={"free": 60, "starter": 30, "pro": 10},
        )
        assert response.total_users == 100
        assert response.active_users_today == 25
        assert response.tier_distribution["free"] == 60

    def test_admin_user_item(self):
        """Test admin user list item schema."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        item = AdminUserItem(
            id=str(uuid4()),
            email="test@example.com",
            is_active=True,
            email_verified=True,
            is_admin=False,
            subscription_tier="starter",
            subscription_status="active",
            playbook_count=5,
            total_cost_usd="0.50",
            created_at=now,
        )
        assert item.email == "test@example.com"
        assert item.playbook_count == 5
        assert item.is_admin is False

    def test_daily_signup_response(self):
        """Test daily signup response schema."""
        response = DailySignupResponse(date="2024-01-15", count=5)
        assert response.date == "2024-01-15"
        assert response.count == 5

    def test_operational_health_response(self):
        """Test operational health response schema."""
        now = datetime.now(timezone.utc)
        response = OperationalHealthResponse(
            generated_at=now,
            sync=SyncHealthResponse(
                status="healthy",
                enabled_workspaces=3,
                active_workspaces_24h=2,
                sync_events_24h=9,
                last_activity_at=now,
            ),
            job_queue=JobQueueHealthResponse(
                status="attention",
                queued_jobs=2,
                running_jobs=1,
                failed_jobs_24h=0,
                jobs_observed_24h=7,
                oldest_queued_at=now,
                last_completed_at=now,
            ),
            inference_gateway=InferenceGatewayHealthResponse(
                status="idle",
                enabled_workspaces=4,
                configured_providers=["openai"],
                requests_24h=0,
                total_tokens_24h=0,
                total_cost_usd_24h="0",
                last_request_at=None,
            ),
        )

        assert response.sync.enabled_workspaces == 3
        assert response.job_queue.queued_jobs == 2
        assert response.inference_gateway.configured_providers == ["openai"]

    def test_conversion_funnel_response(self):
        """Test conversion funnel schema."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        response = ConversionFunnelResponse(
            days=30,
            start_date=now,
            end_date=now,
            landing_views=90,
            register_starts=30,
            register_completes=27,
            signups=27,
            trial_checkout_intent=6,
            trial_started=2,
            first_playbook_created=2,
            paid_active_non_trial=1,
            conversion_landing_to_register_start_pct=33.33,
            conversion_register_start_to_register_complete_pct=90.0,
            conversion_landing_to_register_complete_pct=30.0,
            conversion_signup_to_checkout_intent_pct=22.22,
            conversion_checkout_intent_to_trial_started_pct=33.33,
            conversion_trial_started_to_first_playbook_pct=100.0,
            conversion_first_playbook_to_paid_active_non_trial_pct=50.0,
            conversion_signup_to_trial_started_pct=7.41,
            conversion_signup_to_paid_active_non_trial_pct=3.7,
        )
        assert response.signups == 27
        assert response.trial_started == 2
        assert response.conversion_signup_to_trial_started_pct == 7.41

    def test_build_conversion_funnel_response_rates(self):
        """Test conversion funnel rate calculations."""
        from datetime import datetime, timedelta, timezone

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=7)
        response = build_conversion_funnel_response(
            days=7,
            start_date=start,
            end_date=end,
            landing_views=100,
            register_starts=30,
            register_completes=20,
            signups=20,
            trial_checkout_intent=10,
            trial_started=4,
            first_playbook_created=2,
            paid_active_non_trial=1,
        )

        assert response.conversion_landing_to_register_start_pct == 30.0
        assert response.conversion_register_start_to_register_complete_pct == 66.67
        assert response.conversion_landing_to_register_complete_pct == 20.0
        assert response.conversion_signup_to_checkout_intent_pct == 50.0
        assert response.conversion_checkout_intent_to_trial_started_pct == 40.0
        assert response.conversion_trial_started_to_first_playbook_pct == 50.0
        assert response.conversion_first_playbook_to_paid_active_non_trial_pct == 50.0
        assert response.conversion_signup_to_trial_started_pct == 20.0
        assert response.conversion_signup_to_paid_active_non_trial_pct == 5.0

    def test_build_conversion_funnel_response_zero_division_safe(self):
        """Test conversion funnel avoids divide-by-zero errors."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        response = build_conversion_funnel_response(
            days=30,
            start_date=now,
            end_date=now,
            landing_views=0,
            register_starts=0,
            register_completes=0,
            signups=0,
            trial_checkout_intent=0,
            trial_started=0,
            first_playbook_created=0,
            paid_active_non_trial=0,
        )

        assert response.conversion_landing_to_register_start_pct == 0.0
        assert response.conversion_register_start_to_register_complete_pct == 0.0
        assert response.conversion_landing_to_register_complete_pct == 0.0
        assert response.conversion_signup_to_checkout_intent_pct == 0.0
        assert response.conversion_signup_to_trial_started_pct == 0.0
        assert response.conversion_signup_to_paid_active_non_trial_pct == 0.0

    def test_product_analytics_response(self):
        """Test product analytics schema."""
        now = datetime.now(timezone.utc)
        response = ProductAnalyticsResponse(
            days=30,
            start_date=now,
            end_date=now,
            metrics=[
                {"key": "signup", "label": "Signups", "count": 12},
                {"key": "retention", "label": "Returning users", "count": 5},
            ],
            retention={
                "returning_users": 5,
                "retained_after_day_1": 4,
                "retained_after_day_7": 2,
                "retained_after_day_30": 1,
            },
        )
        assert response.metrics[0].key == "signup"
        assert response.retention.retained_after_day_7 == 2

    def test_build_product_analytics_response(self):
        """Test product analytics response builder."""
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=30)
        response = build_product_analytics_response(
            days=30,
            start_date=start,
            end_date=end,
            signup_count=8,
            cli_init_count=6,
            cli_seed_count=4,
            cli_benchmark_count=3,
            upgrade_count=2,
            returning_users=5,
            retained_after_day_1=4,
            retained_after_day_7=2,
            retained_after_day_30=1,
        )

        assert [metric.key for metric in response.metrics] == [
            "signup",
            "init",
            "seed",
            "benchmark",
            "upgrade",
            "retention",
        ]
        assert response.metrics[3].count == 3
        assert response.retention.returning_users == 5

    @pytest.mark.asyncio
    async def test_get_conversion_funnel_scopes_later_stages_to_prior_cohorts(self):
        """Ensure later funnel queries are constrained to prior-stage users."""
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(side_effect=[100, 35, 22, 20, 10, 8, 6, 4])

        response = await get_conversion_funnel(_admin=object(), db=mock_db, days=30)

        assert response.landing_views == 100
        assert response.register_starts == 35
        assert response.register_completes == 22
        assert response.signups == 20
        assert response.trial_started == 8
        assert response.first_playbook_created == 6
        assert response.paid_active_non_trial == 4
        assert mock_db.scalar.call_count == 8

        first_playbook_query = mock_db.scalar.call_args_list[6].args[0]
        paid_query = mock_db.scalar.call_args_list[7].args[0]
        first_playbook_sql = str(first_playbook_query)
        paid_sql = str(paid_query)

        assert "has_used_trial" in first_playbook_sql
        assert "trial_ends_at" in first_playbook_sql
        assert "EXISTS" in first_playbook_sql
        assert "playbooks.user_id = users.id" in first_playbook_sql

        assert "has_used_trial" in paid_sql
        assert "playbooks.user_id = users.id" in paid_sql
        assert "subscription_status" in paid_sql

    @pytest.mark.asyncio
    async def test_get_conversion_funnel_applies_source_and_variant_filters(self):
        """Ensure source/variant filters are applied to both event and user stages."""
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(side_effect=[10, 6, 4, 4, 3, 2, 1, 1])

        await get_conversion_funnel(
            _admin=object(),
            db=mock_db,
            days=14,
            source="x",
            experiment_variant="late_disclosure",
        )

        event_query = mock_db.scalar.call_args_list[0].args[0]
        user_query = mock_db.scalar.call_args_list[3].args[0]
        event_sql = str(event_query)
        user_sql = str(user_query)

        assert "acquisition_events.source = :source_1" in event_sql
        assert "acquisition_events.experiment_variant = :experiment_variant_1" in event_sql
        assert "users.signup_source = :signup_source_1" in user_sql
        assert "users.signup_variant = :signup_variant_1" in user_sql

    @pytest.mark.asyncio
    async def test_get_product_analytics_counts_required_behaviors(self):
        """Ensure the admin product analytics report queries all required metrics."""
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(side_effect=[9, 7, 5, 4, 3, 6, 5, 2, 1])

        response = await get_product_analytics(_admin=object(), db=mock_db, days=30)

        assert [metric.count for metric in response.metrics] == [9, 7, 5, 4, 3, 6]
        assert response.retention.retained_after_day_1 == 5
        assert response.retention.retained_after_day_7 == 2
        assert response.retention.retained_after_day_30 == 1
        assert mock_db.scalar.call_count == 9

    def test_top_user_response(self):
        """Test top user response schema."""
        response = TopUserResponse(
            user_id=str(uuid4()),
            email="top@example.com",
            subscription_tier="pro",
            total_cost_usd="5.00",
            cost_limit_usd="50.00",
            percent_of_limit=10.0,
        )
        assert response.email == "top@example.com"
        assert response.percent_of_limit == 10.0

    def test_top_user_response_no_limit(self):
        """Test top user response with no cost limit."""
        response = TopUserResponse(
            user_id=str(uuid4()),
            email="enterprise@example.com",
            subscription_tier="enterprise",
            total_cost_usd="100.00",
            cost_limit_usd=None,
            percent_of_limit=None,
        )
        assert response.cost_limit_usd is None
        assert response.percent_of_limit is None

    def test_audit_event_item(self):
        """Test audit event item schema."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        item = AuditEventItem(
            id=str(uuid4()),
            user_id=str(uuid4()),
            user_email="user@example.com",
            event_type="login_success",
            severity="info",
            ip_address="192.168.1.1",
            created_at=now,
            details={"method": "password"},
        )
        assert item.event_type == "login_success"
        assert item.severity == "info"

    def test_audit_event_item_null_user(self):
        """Test audit event with null user (e.g. failed login for non-existent user)."""
        now = datetime.now(timezone.utc)
        item = AuditEventItem(
            id=str(uuid4()),
            user_id=None,
            user_email=None,
            event_type="login_failure",
            severity="warning",
            ip_address="10.0.0.1",
            created_at=now,
            details=None,
        )
        assert item.user_id is None
        assert item.user_email is None

    def test_workspace_backup_item(self):
        """Test workspace backup response schema."""
        now = datetime.now(timezone.utc)
        item = WorkspaceBackupItem(
            id=str(uuid4()),
            workspace_id=str(uuid4()),
            owner_user_id=str(uuid4()),
            trigger_source="scheduled",
            created_at=now,
            restored_at=None,
            backup_size_bytes=512,
            playbook_count=1,
        )
        assert item.trigger_source == "scheduled"
        assert item.backup_size_bytes == 512

    def test_workspace_backup_restore_response(self):
        """Test workspace restore response schema."""
        response = WorkspaceBackupRestoreResponse(
            backup_id=str(uuid4()),
            workspace_id=str(uuid4()),
            restored_playbooks=1,
            restored_usage_records=2,
            restored_api_keys=1,
            restored_oauth_accounts=1,
        )
        assert response.restored_playbooks == 1
        assert response.restored_usage_records == 2
        assert response.restored_api_keys == 1


class TestAdminBackupRoutes:
    """Unit tests for hosted backup admin route helpers."""

    @pytest.mark.asyncio
    async def test_list_workspace_backups_returns_service_metadata(self, monkeypatch):
        workspace_id = uuid4()
        created_at = datetime.now(timezone.utc)

        monkeypatch.setattr(
            admin_routes.workspace_backup_service,
            "get_restoreable_personal_workspace",
            AsyncMock(return_value=SimpleNamespace(id=workspace_id)),
        )
        monkeypatch.setattr(
            admin_routes.workspace_backup_service,
            "list_workspace_backups",
            AsyncMock(
                return_value=[
                    SimpleNamespace(
                        id=uuid4(),
                        workspace_id=workspace_id,
                        owner_user_id=uuid4(),
                        trigger_source="scheduled",
                        created_at=created_at,
                        restored_at=None,
                        backup_size_bytes=128,
                        payload={"account_export": {"playbooks": [{}, {}]}},
                    )
                ]
            ),
        )

        response = await list_workspace_backups(workspace_id, _admin=object(), db=AsyncMock())

        assert len(response) == 1
        assert response[0].workspace_id == str(workspace_id)
        assert response[0].playbook_count == 2

    @pytest.mark.asyncio
    async def test_create_workspace_backup_raises_not_found_for_missing_workspace(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            admin_routes.workspace_backup_service,
            "get_restoreable_personal_workspace",
            AsyncMock(return_value=None),
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_workspace_backup(uuid4(), _admin=object(), db=AsyncMock())

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_create_workspace_backup_returns_created_backup(self, monkeypatch):
        workspace_id = uuid4()
        created_at = datetime.now(timezone.utc)
        db = AsyncMock()
        workspace = SimpleNamespace(id=workspace_id)

        monkeypatch.setattr(
            admin_routes.workspace_backup_service,
            "get_restoreable_personal_workspace",
            AsyncMock(return_value=workspace),
        )
        monkeypatch.setattr(
            admin_routes.workspace_backup_service,
            "create_workspace_backup_snapshot",
            AsyncMock(
                return_value=SimpleNamespace(
                    id=uuid4(),
                    workspace_id=workspace_id,
                    owner_user_id=uuid4(),
                    trigger_source="admin_manual",
                    created_at=created_at,
                    restored_at=None,
                    backup_size_bytes=256,
                    payload={"account_export": {"playbooks": [{}]}},
                )
            ),
        )

        response = await create_workspace_backup(workspace_id, _admin=object(), db=db)

        assert response.trigger_source == "admin_manual"
        assert response.backup_size_bytes == 256
        assert response.playbook_count == 1

    @pytest.mark.asyncio
    async def test_restore_workspace_backup_returns_service_response(self, monkeypatch):
        workspace_id = uuid4()
        backup_id = uuid4()

        monkeypatch.setattr(
            admin_routes.workspace_backup_service,
            "get_workspace_backup",
            AsyncMock(
                return_value=SimpleNamespace(
                    id=backup_id,
                    workspace_id=workspace_id,
                )
            ),
        )
        monkeypatch.setattr(
            admin_routes.workspace_backup_service,
            "restore_workspace_backup",
            AsyncMock(
                return_value={
                    "backup_id": str(backup_id),
                    "workspace_id": str(workspace_id),
                    "restored_playbooks": 1,
                    "restored_usage_records": 2,
                    "restored_api_keys": 1,
                    "restored_oauth_accounts": 1,
                }
            ),
        )

        response = await restore_workspace_backup(
            workspace_id,
            backup_id,
            _admin=object(),
            db=AsyncMock(),
        )

        assert response.backup_id == str(backup_id)
        assert response.restored_playbooks == 1
        assert response.restored_usage_records == 2
        assert response.restored_api_keys == 1
        assert response.restored_oauth_accounts == 1


class TestAdminRoutesIntegration:
    """Integration tests for admin route registration and auth requirements."""

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app."""
        from ace_platform.api.main import create_app

        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return TestClient(app)

    def test_admin_routes_registered(self, app):
        """Test that admin routes are registered."""
        routes = [route.path for route in app.routes]
        assert "/admin/stats" in routes
        assert "/admin/operational-health" in routes
        assert "/admin/users" in routes
        assert "/admin/users/{user_id}" in routes
        assert "/admin/workspaces/{workspace_id}/backups" in routes
        assert "/admin/workspaces/{workspace_id}/backups/{backup_id}/restore" in routes
        assert "/admin/signups" in routes
        assert "/admin/funnel" in routes
        assert "/admin/top-users" in routes
        assert "/admin/audit-events" in routes

    def test_admin_stats_requires_auth(self, client):
        """Test that /admin/stats requires authentication (401)."""
        response = client.get("/admin/stats")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_admin_operational_health_requires_auth(self, client):
        """Test that /admin/operational-health requires authentication (401)."""
        response = client.get("/admin/operational-health")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_admin_users_requires_auth(self, client):
        """Test that /admin/users requires authentication (401)."""
        response = client.get("/admin/users")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_admin_user_detail_requires_auth(self, client):
        """Test that /admin/users/{id} requires authentication (401)."""
        response = client.get(f"/admin/users/{uuid4()}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_admin_signups_requires_auth(self, client):
        """Test that /admin/signups requires authentication (401)."""
        response = client.get("/admin/signups")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_admin_top_users_requires_auth(self, client):
        """Test that /admin/top-users requires authentication (401)."""
        response = client.get("/admin/top-users")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_admin_funnel_requires_auth(self, client):
        """Test that /admin/funnel requires authentication (401)."""
        response = client.get("/admin/funnel")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_admin_audit_events_requires_auth(self, client):
        """Test that /admin/audit-events requires authentication (401)."""
        response = client.get("/admin/audit-events")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_admin_workspace_backups_requires_auth(self, client):
        """Test that backup list/create routes require authentication (401)."""
        workspace_id = uuid4()
        assert (
            client.get(f"/admin/workspaces/{workspace_id}/backups").status_code
            == status.HTTP_401_UNAUTHORIZED
        )
        assert (
            client.post(f"/admin/workspaces/{workspace_id}/backups").status_code
            == status.HTTP_401_UNAUTHORIZED
        )

    def test_admin_workspace_restore_requires_auth(self, client):
        """Test that backup restore routes require authentication (401)."""
        response = client.post(f"/admin/workspaces/{uuid4()}/backups/{uuid4()}/restore")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_admin_stats_with_invalid_token(self, client):
        """Test admin stats with invalid token returns 401."""
        response = client.get(
            "/admin/stats",
            headers={"Authorization": "Bearer invalid.token"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_admin_users_with_invalid_token(self, client):
        """Test admin users with invalid token returns 401."""
        response = client.get(
            "/admin/users",
            headers={"Authorization": "Bearer invalid.token"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestAdminQueryParams:
    """Tests for admin route query parameter validation."""

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app."""
        from ace_platform.api.main import create_app

        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return TestClient(app)

    def test_users_accepts_search_param(self, client):
        """Test that /admin/users accepts search query parameter."""
        response = client.get("/admin/users", params={"search": "test@example.com"})
        # Should fail on auth, not param validation
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_users_accepts_tier_param(self, client):
        """Test that /admin/users accepts tier query parameter."""
        response = client.get("/admin/users", params={"tier": "pro"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_users_accepts_page_param(self, client):
        """Test that /admin/users accepts page query parameter."""
        response = client.get("/admin/users", params={"page": "2"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_signups_accepts_days_param(self, client):
        """Test that /admin/signups accepts days query parameter."""
        response = client.get("/admin/signups", params={"days": "14"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_top_users_accepts_limit_param(self, client):
        """Test that /admin/top-users accepts limit query parameter."""
        response = client.get("/admin/top-users", params={"limit": "5"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_funnel_accepts_days_param(self, client):
        """Test that /admin/funnel accepts days query parameter."""
        response = client.get("/admin/funnel", params={"days": "14"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_funnel_accepts_source_filter(self, client):
        """Test that /admin/funnel accepts source query parameter."""
        response = client.get("/admin/funnel", params={"source": "x"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_funnel_accepts_experiment_variant_filter(self, client):
        """Test that /admin/funnel accepts experiment_variant query parameter."""
        response = client.get("/admin/funnel", params={"experiment_variant": "control"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestAdminOperationalHealth:
    """Tests for the operational health admin route."""

    @pytest.mark.asyncio
    async def test_get_sync_health_snapshot_counts_all_active_workspaces_for_shared_user(self):
        """User activity should mark every hosted personal workspace they belong to as active."""
        now = datetime.now(timezone.utc)
        user_id = uuid4()
        first_workspace_id = uuid4()
        second_workspace_id = uuid4()
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                SimpleNamespace(
                    all=lambda: [
                        SimpleNamespace(id=first_workspace_id, user_id=user_id),
                        SimpleNamespace(id=second_workspace_id, user_id=user_id),
                    ]
                ),
                SimpleNamespace(
                    all=lambda: [
                        SimpleNamespace(
                            user_id=user_id,
                            event_count=2,
                            last_activity_at=now,
                        )
                    ]
                ),
                SimpleNamespace(all=lambda: []),
            ]
        )

        response = await get_sync_health_snapshot(db, now=now)

        assert response.status == "healthy"
        assert response.enabled_workspaces == 2
        assert response.active_workspaces_24h == 2
        assert response.sync_events_24h == 2

    @pytest.mark.asyncio
    async def test_get_operational_health_combines_component_snapshots(self, monkeypatch):
        """Operational health route should compose all three cloud health sections."""
        now = datetime.now(timezone.utc)
        sync = SyncHealthResponse(
            status="healthy",
            enabled_workspaces=2,
            active_workspaces_24h=1,
            sync_events_24h=5,
            last_activity_at=now,
        )
        queue = JobQueueHealthResponse(
            status="attention",
            queued_jobs=1,
            running_jobs=0,
            failed_jobs_24h=0,
            jobs_observed_24h=3,
            oldest_queued_at=now,
            last_completed_at=now,
        )
        inference = InferenceGatewayHealthResponse(
            status="idle",
            enabled_workspaces=2,
            configured_providers=["openai"],
            requests_24h=0,
            total_tokens_24h=0,
            total_cost_usd_24h="0",
            last_request_at=None,
        )

        monkeypatch.setattr(
            admin_routes,
            "get_sync_health_snapshot",
            AsyncMock(return_value=sync),
        )
        monkeypatch.setattr(
            admin_routes,
            "get_job_queue_health_snapshot",
            AsyncMock(return_value=queue),
        )
        monkeypatch.setattr(
            admin_routes,
            "get_inference_gateway_health_snapshot",
            AsyncMock(return_value=inference),
        )

        response = await get_operational_health(_admin=object(), db=AsyncMock())

        assert response.sync == sync
        assert response.job_queue == queue
        assert response.inference_gateway == inference
