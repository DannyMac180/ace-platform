"""Tests for the EvolutionService."""

from unittest.mock import MagicMock, patch

import pytest

from ace_platform.core.evolution import EvolutionResult, EvolutionService, OutcomeData


class TestOutcomeData:
    """Tests for OutcomeData dataclass."""

    def test_successful_outcome(self):
        """Test successful outcome properties."""
        outcome = OutcomeData(
            task_description="Complete task",
            outcome_status="success",
        )
        assert outcome.is_successful is True
        assert "successfully" in outcome.environment_feedback

    def test_failed_outcome(self):
        """Test failed outcome properties."""
        outcome = OutcomeData(
            task_description="Failed task",
            outcome_status="failure",
            notes="Something went wrong",
        )
        assert outcome.is_successful is False
        assert "failed" in outcome.environment_feedback

    def test_partial_outcome(self):
        """Test partial outcome properties."""
        outcome = OutcomeData(
            task_description="Partial task",
            outcome_status="partial",
        )
        assert outcome.is_successful is False
        assert "partially" in outcome.environment_feedback


class TestEvolutionResult:
    """Tests for EvolutionResult dataclass."""

    def test_has_changes_true(self):
        """Test has_changes when playbook changed."""
        result = EvolutionResult(
            original_playbook="## STRATEGIES\n",
            evolved_playbook="## STRATEGIES\n[strat-00001] helpful=0 harmful=0 :: New tip",
            outcomes_processed=1,
            operations_applied=[{"type": "ADD"}],
            token_usage={"total_tokens": 100},
        )
        assert result.has_changes is True

    def test_has_changes_false(self):
        """Test has_changes when no changes made."""
        playbook = "## STRATEGIES\n"
        result = EvolutionResult(
            original_playbook=playbook,
            evolved_playbook=playbook,
            outcomes_processed=0,
            operations_applied=[],
            token_usage={},
        )
        assert result.has_changes is False


class TestEvolutionService:
    """Tests for EvolutionService."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings for testing."""
        settings = MagicMock()
        settings.evolution_api_provider = "openai"
        settings.openai_api_key = "test-key"
        settings.evolution_reflector_model = "gpt-4o"
        settings.evolution_curator_model = "gpt-4o"
        settings.evolution_max_tokens = 4096
        settings.evolution_playbook_token_budget = 80000
        return settings

    @pytest.fixture
    def service(self, mock_settings):
        """Create EvolutionService with mock settings."""
        return EvolutionService(settings=mock_settings)

    def test_init(self, service, mock_settings):
        """Test service initialization."""
        assert service.settings == mock_settings
        assert service._api_client is None
        assert service._reflector is None
        assert service._curator is None

    def test_evolve_playbook_empty_outcomes(self, service):
        """Test evolve_playbook with no outcomes returns unchanged playbook."""
        playbook = "## STRATEGIES\n\n## COMMON MISTAKES TO AVOID\n"
        result = service.evolve_playbook(playbook, [])

        assert result.original_playbook == playbook
        assert result.evolved_playbook == playbook
        assert result.outcomes_processed == 0
        assert result.operations_applied == []
        assert result.has_changes is False

    def test_format_outcomes_for_reflection(self, service):
        """Test formatting outcomes for reflection."""
        outcomes = [
            OutcomeData(
                task_description="Task 1",
                outcome_status="success",
                reasoning_trace="Did thing A",
                notes="Worked well",
            ),
            OutcomeData(
                task_description="Task 2",
                outcome_status="failure",
            ),
        ]
        formatted = service._format_outcomes_for_reflection(outcomes)

        assert "Task 1" in formatted
        assert "Task 2" in formatted
        assert "success" in formatted
        assert "failure" in formatted
        assert "Did thing A" in formatted
        assert "Worked well" in formatted

    def test_create_aggregated_reflection(self, service):
        """Test creating aggregated reflection from outcomes."""
        outcomes = [
            OutcomeData(task_description="Success 1", outcome_status="success"),
            OutcomeData(task_description="Success 2", outcome_status="success"),
            OutcomeData(task_description="Failure 1", outcome_status="failure", notes="Error X"),
            OutcomeData(task_description="Partial 1", outcome_status="partial"),
        ]
        reflection = service._create_aggregated_reflection(outcomes)

        assert "Total outcomes analyzed: 4" in reflection
        assert "Successful: 2" in reflection
        assert "Failed: 1" in reflection
        assert "Partial: 1" in reflection
        assert "Failure 1" in reflection
        assert "Error X" in reflection

    @patch("ace_platform.core.evolution.EvolutionService._get_curator")
    @patch("ace_platform.core.evolution.EvolutionService._get_playbook_stats")
    @patch("ace_platform.core.evolution.EvolutionService._get_next_global_id")
    def test_evolve_playbook_with_outcomes(
        self,
        mock_next_id,
        mock_stats,
        mock_get_curator,
        service,
    ):
        """Test evolve_playbook processes outcomes through curator."""
        # Setup mocks
        mock_next_id.return_value = 1
        mock_stats.return_value = {"total_bullets": 0}

        mock_curator = MagicMock()
        evolved_content = "## STRATEGIES\n[strat-00001] helpful=0 harmful=0 :: New insight"
        mock_curator.curate.return_value = (
            evolved_content,
            2,
            [{"type": "ADD", "section": "strategies", "content": "New insight"}],
            {"prompt_num_tokens": 100, "response_num_tokens": 50},
        )
        mock_get_curator.return_value = mock_curator

        # Run test
        playbook = "## STRATEGIES\n\n## COMMON MISTAKES TO AVOID\n"
        outcomes = [
            OutcomeData(task_description="Failed task", outcome_status="failure"),
        ]
        result = service.evolve_playbook(playbook, outcomes)

        # Assertions
        assert result.evolved_playbook == evolved_content
        assert result.outcomes_processed == 1
        assert len(result.operations_applied) == 1
        assert result.token_usage["total_tokens"] == 150
        mock_curator.curate.assert_called_once()

    def test_unsupported_api_provider(self, mock_settings):
        """Test error for unsupported API provider."""
        mock_settings.evolution_api_provider = "unsupported"
        service = EvolutionService(settings=mock_settings)

        with pytest.raises(ValueError, match="Unsupported API provider"):
            _ = service.api_client


class TestEvolutionServiceIntegration:
    """Integration tests for EvolutionService.

    These tests require ace_core to be accessible.
    """

    @pytest.fixture
    def sample_playbook(self):
        """Create a sample playbook for testing."""
        return """## STRATEGIES & INSIGHTS

## FORMULAS & CALCULATIONS

## CODE SNIPPETS & TEMPLATES

## COMMON MISTAKES TO AVOID

## PROBLEM-SOLVING HEURISTICS

## CONTEXT CLUES & INDICATORS

## OTHERS"""

    @pytest.mark.skip(reason="Requires ace_core path setup and real API key")
    def test_full_evolution_cycle(self, sample_playbook):
        """Test full evolution cycle with real ace_core agents.

        This test is skipped by default as it requires:
        1. ace_core to be in the Python path
        2. A real OpenAI API key
        """
        service = EvolutionService()
        outcomes = [
            OutcomeData(
                task_description="Analyze financial report",
                outcome_status="failure",
                notes="Could not identify key metrics",
            ),
            OutcomeData(
                task_description="Summarize earnings call",
                outcome_status="success",
            ),
        ]

        result = service.evolve_playbook(sample_playbook, outcomes)

        assert result.outcomes_processed == 2
        assert isinstance(result.evolved_playbook, str)
