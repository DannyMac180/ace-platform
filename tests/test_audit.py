"""Tests for audit logging functionality."""

from unittest.mock import MagicMock

from ace_platform.core.audit import (
    get_client_ip,
    get_user_agent,
)
from ace_platform.db.models import AuditEventType, AuditLog, AuditSeverity


class MockRequest:
    """Mock FastAPI Request for testing."""

    def __init__(
        self,
        client_host: str = "127.0.0.1",
        user_agent: str = "TestAgent/1.0",
        forwarded_for: str | None = None,
        real_ip: str | None = None,
    ):
        self.client = MagicMock()
        self.client.host = client_host
        self.headers = {}
        if user_agent:
            self.headers["User-Agent"] = user_agent
        if forwarded_for:
            self.headers["X-Forwarded-For"] = forwarded_for
        if real_ip:
            self.headers["X-Real-IP"] = real_ip

    def get(self, key: str, default=None):
        return self.headers.get(key, default)


class TestClientIPExtraction:
    """Tests for get_client_ip function."""

    def test_get_client_ip_direct(self):
        """Direct client IP is returned when no proxy headers."""
        request = MockRequest(client_host="192.168.1.100")
        assert get_client_ip(request) == "192.168.1.100"

    def test_get_client_ip_x_forwarded_for(self):
        """X-Forwarded-For header takes precedence."""
        request = MockRequest(
            client_host="127.0.0.1",
            forwarded_for="203.0.113.50, 70.41.3.18, 150.172.238.178",
        )
        assert get_client_ip(request) == "203.0.113.50"

    def test_get_client_ip_x_real_ip(self):
        """X-Real-IP is used when X-Forwarded-For is not present."""
        request = MockRequest(client_host="127.0.0.1", real_ip="203.0.113.50")
        assert get_client_ip(request) == "203.0.113.50"

    def test_get_client_ip_no_client(self):
        """Returns None when no client info available."""
        request = MockRequest()
        request.client = None
        assert get_client_ip(request) is None


class TestUserAgentExtraction:
    """Tests for get_user_agent function."""

    def test_get_user_agent_normal(self):
        """Normal user agent is returned."""
        request = MockRequest(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)")
        assert get_user_agent(request) == "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"

    def test_get_user_agent_truncation(self):
        """Long user agents are truncated to 512 characters."""
        long_ua = "A" * 1000
        request = MockRequest(user_agent=long_ua)
        result = get_user_agent(request)
        assert len(result) == 512
        assert result == "A" * 512

    def test_get_user_agent_missing(self):
        """Returns None when no user agent header."""
        request = MockRequest(user_agent=None)
        assert get_user_agent(request) is None


class TestAuditLogModel:
    """Tests for AuditLog model and enums."""

    def test_audit_event_types_exist(self):
        """All expected audit event types are defined."""
        expected_types = [
            "LOGIN_SUCCESS",
            "LOGIN_FAILURE",
            "LOGOUT",
            "OAUTH_LOGIN_SUCCESS",
            "OAUTH_LOGIN_FAILURE",
            "PASSWORD_CHANGE",
            "PASSWORD_RESET_REQUEST",
            "PASSWORD_RESET_COMPLETE",
            "EMAIL_VERIFICATION_SENT",
            "EMAIL_VERIFIED",
            "API_KEY_CREATED",
            "API_KEY_REVOKED",
            "ACCOUNT_CREATED",
            "ACCOUNT_LOCKED",
            "ACCOUNT_UNLOCKED",
            "PERMISSION_DENIED",
            "SUBSCRIPTION_CREATED",
            "SUBSCRIPTION_UPDATED",
            "SUBSCRIPTION_CANCELED",
            "PAYMENT_METHOD_ADDED",
            "PAYMENT_METHOD_REMOVED",
            "OAUTH_ACCOUNT_LINKED",
            "OAUTH_ACCOUNT_UNLINKED",
        ]
        for event_type in expected_types:
            assert hasattr(AuditEventType, event_type)

    def test_audit_severity_levels(self):
        """All severity levels are defined."""
        assert AuditSeverity.INFO.value == "info"
        assert AuditSeverity.WARNING.value == "warning"
        assert AuditSeverity.CRITICAL.value == "critical"

    def test_audit_log_model_fields(self):
        """AuditLog model has expected fields."""
        # These are class-level mapped columns
        assert hasattr(AuditLog, "id")
        assert hasattr(AuditLog, "user_id")
        assert hasattr(AuditLog, "event_type")
        assert hasattr(AuditLog, "severity")
        assert hasattr(AuditLog, "ip_address")
        assert hasattr(AuditLog, "user_agent")
        assert hasattr(AuditLog, "details")
        assert hasattr(AuditLog, "created_at")


class TestAuditEventTypeValues:
    """Tests for AuditEventType enum values."""

    def test_login_events(self):
        """Login-related event types have correct values."""
        assert AuditEventType.LOGIN_SUCCESS.value == "login_success"
        assert AuditEventType.LOGIN_FAILURE.value == "login_failure"
        assert AuditEventType.LOGOUT.value == "logout"

    def test_oauth_events(self):
        """OAuth-related event types have correct values."""
        assert AuditEventType.OAUTH_LOGIN_SUCCESS.value == "oauth_login_success"
        assert AuditEventType.OAUTH_LOGIN_FAILURE.value == "oauth_login_failure"
        assert AuditEventType.OAUTH_ACCOUNT_LINKED.value == "oauth_account_linked"
        assert AuditEventType.OAUTH_ACCOUNT_UNLINKED.value == "oauth_account_unlinked"

    def test_password_events(self):
        """Password-related event types have correct values."""
        assert AuditEventType.PASSWORD_CHANGE.value == "password_change"
        assert AuditEventType.PASSWORD_RESET_REQUEST.value == "password_reset_request"
        assert AuditEventType.PASSWORD_RESET_COMPLETE.value == "password_reset_complete"

    def test_email_events(self):
        """Email-related event types have correct values."""
        assert AuditEventType.EMAIL_VERIFICATION_SENT.value == "email_verification_sent"
        assert AuditEventType.EMAIL_VERIFIED.value == "email_verified"

    def test_api_key_events(self):
        """API key-related event types have correct values."""
        assert AuditEventType.API_KEY_CREATED.value == "api_key_created"
        assert AuditEventType.API_KEY_REVOKED.value == "api_key_revoked"

    def test_account_events(self):
        """Account-related event types have correct values."""
        assert AuditEventType.ACCOUNT_CREATED.value == "account_created"
        assert AuditEventType.ACCOUNT_LOCKED.value == "account_locked"
        assert AuditEventType.ACCOUNT_UNLOCKED.value == "account_unlocked"

    def test_subscription_events(self):
        """Subscription-related event types have correct values."""
        assert AuditEventType.SUBSCRIPTION_CREATED.value == "subscription_created"
        assert AuditEventType.SUBSCRIPTION_UPDATED.value == "subscription_updated"
        assert AuditEventType.SUBSCRIPTION_CANCELED.value == "subscription_canceled"
        assert AuditEventType.PAYMENT_METHOD_ADDED.value == "payment_method_added"
        assert AuditEventType.PAYMENT_METHOD_REMOVED.value == "payment_method_removed"

    def test_authorization_events(self):
        """Authorization-related event types have correct values."""
        assert AuditEventType.PERMISSION_DENIED.value == "permission_denied"


class TestAuditFunctionSignatures:
    """Tests to verify audit function signatures and imports work correctly."""

    def test_audit_functions_importable(self):
        """All audit functions can be imported."""
        from ace_platform.core.audit import (
            audit_account_created,
            audit_account_locked,
            audit_account_unlocked,
            audit_api_key_created,
            audit_api_key_revoked,
            audit_email_verification_sent,
            audit_email_verified,
            audit_login_failure,
            audit_login_success,
            audit_logout,
            audit_oauth_account_linked,
            audit_oauth_account_unlinked,
            audit_oauth_login_failure,
            audit_oauth_login_success,
            audit_password_change,
            audit_password_reset_complete,
            audit_password_reset_request,
            audit_payment_method_added,
            audit_payment_method_removed,
            audit_permission_denied,
            audit_subscription_canceled,
            audit_subscription_created,
            audit_subscription_updated,
            log_audit_event,
        )

        # Verify they're callable
        assert callable(log_audit_event)
        assert callable(audit_login_success)
        assert callable(audit_login_failure)
        assert callable(audit_logout)
        assert callable(audit_oauth_login_success)
        assert callable(audit_oauth_login_failure)
        assert callable(audit_account_created)
        assert callable(audit_account_locked)
        assert callable(audit_account_unlocked)
        assert callable(audit_api_key_created)
        assert callable(audit_api_key_revoked)
        assert callable(audit_email_verification_sent)
        assert callable(audit_email_verified)
        assert callable(audit_password_change)
        assert callable(audit_password_reset_request)
        assert callable(audit_password_reset_complete)
        assert callable(audit_permission_denied)
        assert callable(audit_subscription_created)
        assert callable(audit_subscription_updated)
        assert callable(audit_subscription_canceled)
        assert callable(audit_payment_method_added)
        assert callable(audit_payment_method_removed)
        assert callable(audit_oauth_account_linked)
        assert callable(audit_oauth_account_unlinked)

    def test_log_audit_event_is_async(self):
        """log_audit_event is an async function."""
        import inspect

        from ace_platform.core.audit import log_audit_event

        assert inspect.iscoroutinefunction(log_audit_event)

    def test_audit_login_success_is_async(self):
        """audit_login_success is an async function."""
        import inspect

        from ace_platform.core.audit import audit_login_success

        assert inspect.iscoroutinefunction(audit_login_success)


class TestAuditLogMigration:
    """Tests related to the audit_logs table schema."""

    def test_audit_log_table_name(self):
        """AuditLog model has correct table name."""
        assert AuditLog.__tablename__ == "audit_logs"

    def test_audit_log_has_indexes(self):
        """AuditLog model has expected indexes defined."""
        # Check that table_args includes indexes
        table_args = AuditLog.__table_args__
        index_names = [idx.name for idx in table_args if hasattr(idx, "name")]

        assert "ix_audit_logs_user_created" in index_names
        assert "ix_audit_logs_event_type" in index_names
        assert "ix_audit_logs_severity_created" in index_names
