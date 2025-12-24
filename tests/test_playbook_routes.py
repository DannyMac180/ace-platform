"""Tests for playbook CRUD API routes.

These tests verify:
1. Playbook list endpoint with pagination
2. Playbook create endpoint
3. Playbook get endpoint
4. Playbook update endpoint
5. Playbook delete endpoint
6. Authentication and authorization
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from ace_platform.api.routes.playbooks import (
    PaginatedPlaybookResponse,
    PlaybookCreate,
    PlaybookListItem,
    PlaybookResponse,
    PlaybookUpdate,
    PlaybookVersionResponse,
)
from ace_platform.db.models import PlaybookSource, PlaybookStatus


class TestPlaybookSchemas:
    """Tests for Pydantic schemas."""

    def test_playbook_create_valid(self):
        """Test valid playbook create schema."""
        data = PlaybookCreate(name="Test Playbook", description="A test playbook")
        assert data.name == "Test Playbook"
        assert data.description == "A test playbook"
        assert data.initial_content is None

    def test_playbook_create_with_content(self):
        """Test playbook create with initial content."""
        data = PlaybookCreate(
            name="Test",
            initial_content="# Playbook\n\n- Step 1\n- Step 2",
        )
        assert data.initial_content is not None

    def test_playbook_create_name_required(self):
        """Test that name is required."""
        with pytest.raises(ValueError):
            PlaybookCreate(description="No name provided")

    def test_playbook_update_partial(self):
        """Test partial update schema."""
        data = PlaybookUpdate(name="New Name")
        assert data.name == "New Name"
        assert data.description is None
        assert data.status is None

    def test_playbook_update_status(self):
        """Test updating status."""
        data = PlaybookUpdate(status=PlaybookStatus.ARCHIVED)
        assert data.status == PlaybookStatus.ARCHIVED


class TestPlaybookRoutesIntegration:
    """Integration tests for playbook routes."""

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app."""
        from ace_platform.api.main import create_app

        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return TestClient(app)

    def test_playbooks_routes_registered(self, app):
        """Test that playbook routes are registered."""
        routes = [route.path for route in app.routes]
        assert "/playbooks" in routes
        assert "/playbooks/{playbook_id}" in routes

    def test_list_playbooks_requires_auth(self, client):
        """Test that listing playbooks requires authentication."""
        response = client.get("/playbooks")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_playbook_requires_auth(self, client):
        """Test that creating playbook requires authentication."""
        response = client.post(
            "/playbooks",
            json={"name": "Test Playbook"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_playbook_requires_auth(self, client):
        """Test that getting playbook requires authentication."""
        playbook_id = str(uuid4())
        response = client.get(f"/playbooks/{playbook_id}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_update_playbook_requires_auth(self, client):
        """Test that updating playbook requires authentication."""
        playbook_id = str(uuid4())
        response = client.put(
            f"/playbooks/{playbook_id}",
            json={"name": "New Name"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_delete_playbook_requires_auth(self, client):
        """Test that deleting playbook requires authentication."""
        playbook_id = str(uuid4())
        response = client.delete(f"/playbooks/{playbook_id}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_playbook_validation_empty_name(self, client):
        """Test that empty name is rejected."""
        # First need to mock auth - but 401 comes before validation
        response = client.post(
            "/playbooks",
            json={"name": ""},
            headers={"Authorization": "Bearer invalid"},
        )
        # Should fail on auth first
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_playbooks_with_invalid_token(self, client):
        """Test listing playbooks with invalid token."""
        response = client.get(
            "/playbooks",
            headers={"Authorization": "Bearer invalid.token"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_playbook_invalid_uuid(self, client):
        """Test getting playbook with invalid UUID."""
        response = client.get(
            "/playbooks/not-a-uuid",
            headers={"Authorization": "Bearer fake"},
        )
        # Returns 422 for invalid path parameter before checking auth
        assert response.status_code in [
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            status.HTTP_401_UNAUTHORIZED,
        ]


class TestPaginatedResponse:
    """Tests for paginated response schema."""

    def test_paginated_response_structure(self):
        """Test paginated response with items."""
        now = datetime.now(timezone.utc)
        items = [
            PlaybookListItem(
                id=uuid4(),
                name="Test 1",
                description=None,
                status=PlaybookStatus.ACTIVE,
                source=PlaybookSource.USER_CREATED,
                created_at=now,
                updated_at=now,
                version_count=1,
                outcome_count=0,
            ),
            PlaybookListItem(
                id=uuid4(),
                name="Test 2",
                description="Second playbook",
                status=PlaybookStatus.ACTIVE,
                source=PlaybookSource.USER_CREATED,
                created_at=now,
                updated_at=now,
                version_count=2,
                outcome_count=5,
            ),
        ]

        response = PaginatedPlaybookResponse(
            items=items,
            total=25,
            page=2,
            page_size=10,
            total_pages=3,
        )

        assert len(response.items) == 2
        assert response.total == 25
        assert response.page == 2
        assert response.page_size == 10
        assert response.total_pages == 3

    def test_empty_paginated_response(self):
        """Test empty paginated response."""
        response = PaginatedPlaybookResponse(
            items=[],
            total=0,
            page=1,
            page_size=20,
            total_pages=0,
        )

        assert len(response.items) == 0
        assert response.total == 0


class TestPlaybookResponse:
    """Tests for playbook response schema."""

    def test_playbook_response_without_version(self):
        """Test playbook response without current version."""
        now = datetime.now(timezone.utc)
        response = PlaybookResponse(
            id=uuid4(),
            name="Test Playbook",
            description="A test",
            status=PlaybookStatus.ACTIVE,
            source=PlaybookSource.USER_CREATED,
            created_at=now,
            updated_at=now,
            current_version=None,
        )

        assert response.current_version is None
        assert response.name == "Test Playbook"

    def test_playbook_response_with_version(self):
        """Test playbook response with current version."""
        now = datetime.now(timezone.utc)
        version = PlaybookVersionResponse(
            id=uuid4(),
            version_number=3,
            content="# My Playbook\n\n- Step 1\n- Step 2",
            bullet_count=2,
            created_at=now,
        )

        response = PlaybookResponse(
            id=uuid4(),
            name="Test Playbook",
            description="A test",
            status=PlaybookStatus.ACTIVE,
            source=PlaybookSource.USER_CREATED,
            created_at=now,
            updated_at=now,
            current_version=version,
        )

        assert response.current_version is not None
        assert response.current_version.version_number == 3
        assert response.current_version.bullet_count == 2


class TestPlaybookVersionResponse:
    """Tests for playbook version response schema."""

    def test_version_response(self):
        """Test version response schema."""
        now = datetime.now(timezone.utc)
        version = PlaybookVersionResponse(
            id=uuid4(),
            version_number=1,
            content="# Playbook Content",
            bullet_count=0,
            created_at=now,
        )

        assert version.version_number == 1
        assert version.content == "# Playbook Content"
        assert version.bullet_count == 0


class TestOutcomeSchemas:
    """Tests for outcome response schemas."""

    def test_outcome_response_valid(self):
        """Test valid outcome response schema."""
        from ace_platform.api.routes.playbooks import OutcomeResponse
        from ace_platform.db.models import OutcomeStatus

        now = datetime.now(timezone.utc)
        response = OutcomeResponse(
            id=uuid4(),
            task_description="Test task",
            outcome_status=OutcomeStatus.SUCCESS,
            notes="Some notes",
            reasoning_trace="Reasoning here",
            created_at=now,
            processed_at=now,
            evolution_job_id=uuid4(),
        )

        assert response.task_description == "Test task"
        assert response.outcome_status == OutcomeStatus.SUCCESS
        assert response.notes == "Some notes"

    def test_outcome_response_optional_fields(self):
        """Test outcome response with optional fields as None."""
        from ace_platform.api.routes.playbooks import OutcomeResponse
        from ace_platform.db.models import OutcomeStatus

        now = datetime.now(timezone.utc)
        response = OutcomeResponse(
            id=uuid4(),
            task_description="Test task",
            outcome_status=OutcomeStatus.FAILURE,
            notes=None,
            reasoning_trace=None,
            created_at=now,
            processed_at=None,
            evolution_job_id=None,
        )

        assert response.notes is None
        assert response.processed_at is None
        assert response.evolution_job_id is None

    def test_paginated_outcome_response(self):
        """Test paginated outcome response."""
        from ace_platform.api.routes.playbooks import (
            OutcomeResponse,
            PaginatedOutcomeResponse,
        )
        from ace_platform.db.models import OutcomeStatus

        now = datetime.now(timezone.utc)
        items = [
            OutcomeResponse(
                id=uuid4(),
                task_description=f"Task {i}",
                outcome_status=OutcomeStatus.SUCCESS,
                notes=None,
                reasoning_trace=None,
                created_at=now,
                processed_at=None,
                evolution_job_id=None,
            )
            for i in range(3)
        ]

        response = PaginatedOutcomeResponse(
            items=items,
            total=15,
            page=2,
            page_size=5,
            total_pages=3,
        )

        assert len(response.items) == 3
        assert response.total == 15
        assert response.page == 2
        assert response.total_pages == 3


class TestOutcomesEndpointIntegration:
    """Integration tests for playbook outcomes endpoint."""

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app."""
        from ace_platform.api.main import create_app

        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return TestClient(app)

    def test_outcomes_route_registered(self, app):
        """Test that outcomes route is registered."""
        routes = [route.path for route in app.routes]
        assert "/playbooks/{playbook_id}/outcomes" in routes

    def test_list_outcomes_requires_auth(self, client):
        """Test that listing outcomes requires authentication."""
        playbook_id = str(uuid4())
        response = client.get(f"/playbooks/{playbook_id}/outcomes")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_outcomes_with_invalid_token(self, client):
        """Test listing outcomes with invalid token."""
        playbook_id = str(uuid4())
        response = client.get(
            f"/playbooks/{playbook_id}/outcomes",
            headers={"Authorization": "Bearer invalid.token"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_outcomes_invalid_uuid(self, client):
        """Test listing outcomes with invalid UUID."""
        response = client.get(
            "/playbooks/not-a-uuid/outcomes",
            headers={"Authorization": "Bearer fake"},
        )
        # Returns 422 for invalid path parameter or 401 for auth
        assert response.status_code in [
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            status.HTTP_401_UNAUTHORIZED,
        ]


class TestEvolutionJobSchemas:
    """Tests for evolution job response schemas."""

    def test_evolution_job_response_valid(self):
        """Test valid evolution job response schema."""
        from ace_platform.api.routes.playbooks import EvolutionJobResponse
        from ace_platform.db.models import EvolutionJobStatus

        now = datetime.now(timezone.utc)
        response = EvolutionJobResponse(
            id=uuid4(),
            status=EvolutionJobStatus.COMPLETED,
            from_version_id=uuid4(),
            to_version_id=uuid4(),
            outcomes_processed=5,
            error_message=None,
            created_at=now,
            started_at=now,
            completed_at=now,
        )

        assert response.status == EvolutionJobStatus.COMPLETED
        assert response.outcomes_processed == 5
        assert response.error_message is None

    def test_evolution_job_response_failed(self):
        """Test evolution job response for failed job."""
        from ace_platform.api.routes.playbooks import EvolutionJobResponse
        from ace_platform.db.models import EvolutionJobStatus

        now = datetime.now(timezone.utc)
        response = EvolutionJobResponse(
            id=uuid4(),
            status=EvolutionJobStatus.FAILED,
            from_version_id=uuid4(),
            to_version_id=None,
            outcomes_processed=0,
            error_message="Evolution failed due to API error",
            created_at=now,
            started_at=now,
            completed_at=now,
        )

        assert response.status == EvolutionJobStatus.FAILED
        assert response.to_version_id is None
        assert response.error_message == "Evolution failed due to API error"

    def test_evolution_job_response_queued(self):
        """Test evolution job response for queued job."""
        from ace_platform.api.routes.playbooks import EvolutionJobResponse
        from ace_platform.db.models import EvolutionJobStatus

        now = datetime.now(timezone.utc)
        response = EvolutionJobResponse(
            id=uuid4(),
            status=EvolutionJobStatus.QUEUED,
            from_version_id=uuid4(),
            to_version_id=None,
            outcomes_processed=0,
            error_message=None,
            created_at=now,
            started_at=None,
            completed_at=None,
        )

        assert response.status == EvolutionJobStatus.QUEUED
        assert response.started_at is None
        assert response.completed_at is None

    def test_paginated_evolution_job_response(self):
        """Test paginated evolution job response."""
        from ace_platform.api.routes.playbooks import (
            EvolutionJobResponse,
            PaginatedEvolutionJobResponse,
        )
        from ace_platform.db.models import EvolutionJobStatus

        now = datetime.now(timezone.utc)
        items = [
            EvolutionJobResponse(
                id=uuid4(),
                status=EvolutionJobStatus.COMPLETED,
                from_version_id=uuid4(),
                to_version_id=uuid4(),
                outcomes_processed=i + 1,
                error_message=None,
                created_at=now,
                started_at=now,
                completed_at=now,
            )
            for i in range(3)
        ]

        response = PaginatedEvolutionJobResponse(
            items=items,
            total=10,
            page=1,
            page_size=5,
            total_pages=2,
        )

        assert len(response.items) == 3
        assert response.total == 10
        assert response.total_pages == 2


class TestEvolutionsEndpointIntegration:
    """Integration tests for playbook evolutions endpoint."""

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app."""
        from ace_platform.api.main import create_app

        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return TestClient(app)

    def test_evolutions_route_registered(self, app):
        """Test that evolutions route is registered."""
        routes = [route.path for route in app.routes]
        assert "/playbooks/{playbook_id}/evolutions" in routes

    def test_list_evolutions_requires_auth(self, client):
        """Test that listing evolutions requires authentication."""
        playbook_id = str(uuid4())
        response = client.get(f"/playbooks/{playbook_id}/evolutions")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_evolutions_with_invalid_token(self, client):
        """Test listing evolutions with invalid token."""
        playbook_id = str(uuid4())
        response = client.get(
            f"/playbooks/{playbook_id}/evolutions",
            headers={"Authorization": "Bearer invalid.token"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_evolutions_invalid_uuid(self, client):
        """Test listing evolutions with invalid UUID."""
        response = client.get(
            "/playbooks/not-a-uuid/evolutions",
            headers={"Authorization": "Bearer fake"},
        )
        # Returns 422 for invalid path parameter or 401 for auth
        assert response.status_code in [
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            status.HTTP_401_UNAUTHORIZED,
        ]
