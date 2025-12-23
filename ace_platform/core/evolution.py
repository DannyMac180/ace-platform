"""Evolution service that wraps ace_core for playbook evolution.

This service provides a platform-level interface to the ACE three-agent
architecture (Generator, Reflector, Curator) for evolving playbooks
based on outcome feedback.
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import openai

from ace_platform.config import Settings, get_settings

# Add ace_core to path for imports (must be done after local imports, before ace_core imports)
ACE_CORE_PATH = Path(__file__).parent.parent.parent / "ace_core"
if str(ACE_CORE_PATH) not in sys.path:
    sys.path.insert(0, str(ACE_CORE_PATH))


@dataclass
class OutcomeData:
    """Data structure for outcome feedback used in evolution."""

    task_description: str
    outcome_status: str  # "success", "failure", "partial"
    reasoning_trace: str | None = None
    notes: str | None = None

    @property
    def is_successful(self) -> bool:
        """Check if outcome was successful."""
        return self.outcome_status == "success"

    @property
    def environment_feedback(self) -> str:
        """Generate environment feedback string for reflector."""
        if self.outcome_status == "success":
            return "Task completed successfully"
        elif self.outcome_status == "partial":
            return "Task partially completed with some issues"
        else:
            return "Task failed to complete successfully"


@dataclass
class EvolutionResult:
    """Result from playbook evolution."""

    original_playbook: str
    evolved_playbook: str
    outcomes_processed: int
    operations_applied: list[dict[str, Any]]
    token_usage: dict[str, int]

    @property
    def has_changes(self) -> bool:
        """Check if evolution made any changes."""
        return self.original_playbook != self.evolved_playbook


class EvolutionService:
    """Service for evolving playbooks using the ACE three-agent architecture.

    This service wraps the ace_core Reflector and Curator agents to process
    outcome feedback and evolve playbooks accordingly.
    """

    def __init__(self, settings: Settings | None = None):
        """Initialize the evolution service.

        Args:
            settings: Platform settings. If None, loads from environment.
        """
        self.settings = settings or get_settings()
        self._api_client: openai.OpenAI | None = None
        self._reflector = None
        self._curator = None

    @property
    def api_client(self) -> openai.OpenAI:
        """Lazily initialize the OpenAI client."""
        if self._api_client is None:
            if self.settings.evolution_api_provider == "openai":
                self._api_client = openai.OpenAI(
                    api_key=self.settings.openai_api_key,
                )
            else:
                raise ValueError(
                    f"Unsupported API provider: {self.settings.evolution_api_provider}"
                )
        return self._api_client

    def _get_reflector(self):
        """Lazily initialize the Reflector agent."""
        if self._reflector is None:
            from ace.core.reflector import Reflector

            self._reflector = Reflector(
                api_client=self.api_client,
                api_provider=self.settings.evolution_api_provider,
                model=self.settings.evolution_reflector_model,
                max_tokens=self.settings.evolution_max_tokens,
            )
        return self._reflector

    def _get_curator(self):
        """Lazily initialize the Curator agent."""
        if self._curator is None:
            from ace.core.curator import Curator

            self._curator = Curator(
                api_client=self.api_client,
                api_provider=self.settings.evolution_api_provider,
                model=self.settings.evolution_curator_model,
                max_tokens=self.settings.evolution_max_tokens,
            )
        return self._curator

    def _get_playbook_stats(self, playbook_content: str) -> dict[str, Any]:
        """Get statistics about the playbook.

        Args:
            playbook_content: The playbook content to analyze.

        Returns:
            Dictionary with playbook statistics.
        """
        from playbook_utils import get_playbook_stats

        return get_playbook_stats(playbook_content)

    def _get_next_global_id(self, playbook_content: str) -> int:
        """Get the next available global ID for bullets.

        Args:
            playbook_content: The playbook content to analyze.

        Returns:
            Next available global ID.
        """
        from playbook_utils import get_next_global_id

        return get_next_global_id(playbook_content)

    def _format_outcomes_for_reflection(self, outcomes: list[OutcomeData]) -> str:
        """Format outcomes into a reflection context string.

        Args:
            outcomes: List of outcomes to format.

        Returns:
            Formatted string for reflection input.
        """
        lines = []
        for i, outcome in enumerate(outcomes, 1):
            lines.append(f"--- Outcome {i} ---")
            lines.append(f"Task: {outcome.task_description}")
            lines.append(f"Result: {outcome.outcome_status}")
            if outcome.reasoning_trace:
                lines.append(f"Reasoning: {outcome.reasoning_trace}")
            if outcome.notes:
                lines.append(f"Notes: {outcome.notes}")
            lines.append("")

        return "\n".join(lines)

    def _create_aggregated_reflection(
        self,
        outcomes: list[OutcomeData],
    ) -> str:
        """Create an aggregated reflection from multiple outcomes.

        This synthesizes feedback from multiple outcomes into a single
        reflection that can guide the Curator.

        Args:
            outcomes: List of outcomes to reflect on.

        Returns:
            Aggregated reflection string.
        """
        successful = [o for o in outcomes if o.is_successful]
        failed = [o for o in outcomes if o.outcome_status == "failure"]
        partial = [o for o in outcomes if o.outcome_status == "partial"]

        lines = [
            "## Aggregated Reflection from Recent Outcomes",
            "",
            f"Total outcomes analyzed: {len(outcomes)}",
            f"- Successful: {len(successful)}",
            f"- Failed: {len(failed)}",
            f"- Partial: {len(partial)}",
            "",
        ]

        if failed:
            lines.append("### Failed Tasks (need improvement)")
            for outcome in failed:
                lines.append(f"- Task: {outcome.task_description}")
                if outcome.notes:
                    lines.append(f"  Notes: {outcome.notes}")
            lines.append("")

        if partial:
            lines.append("### Partial Successes (could be improved)")
            for outcome in partial:
                lines.append(f"- Task: {outcome.task_description}")
                if outcome.notes:
                    lines.append(f"  Notes: {outcome.notes}")
            lines.append("")

        if successful:
            lines.append("### Successful Tasks (patterns to reinforce)")
            for outcome in successful[:5]:  # Limit to top 5
                lines.append(f"- Task: {outcome.task_description}")
            if len(successful) > 5:
                lines.append(f"  ... and {len(successful) - 5} more successful tasks")
            lines.append("")

        return "\n".join(lines)

    def evolve_playbook(
        self,
        playbook_content: str,
        outcomes: list[OutcomeData],
    ) -> EvolutionResult:
        """Evolve a playbook based on outcome feedback.

        This is the main entry point for playbook evolution. It:
        1. Creates an aggregated reflection from outcomes
        2. Runs the Curator to propose and apply playbook updates
        3. Returns the evolved playbook

        Args:
            playbook_content: Current playbook content (markdown format).
            outcomes: List of outcome data from task executions.

        Returns:
            EvolutionResult with the evolved playbook and metadata.
        """
        if not outcomes:
            return EvolutionResult(
                original_playbook=playbook_content,
                evolved_playbook=playbook_content,
                outcomes_processed=0,
                operations_applied=[],
                token_usage={},
            )

        # Get playbook stats and next ID
        stats = self._get_playbook_stats(playbook_content)
        next_global_id = self._get_next_global_id(playbook_content)

        # Create aggregated reflection from outcomes
        reflection = self._create_aggregated_reflection(outcomes)

        # Format outcomes as question context
        question_context = self._format_outcomes_for_reflection(outcomes)

        # Run the Curator to evolve the playbook
        curator = self._get_curator()

        evolved_playbook, new_next_id, operations, call_info = curator.curate(
            current_playbook=playbook_content,
            recent_reflection=reflection,
            question_context=question_context,
            current_step=len(outcomes),
            total_samples=len(outcomes),
            token_budget=self.settings.evolution_playbook_token_budget,
            playbook_stats=stats,
            use_ground_truth=False,  # We don't have ground truth in platform context
            use_json_mode=True,
            call_id="platform_evolution",
            log_dir=None,
            next_global_id=next_global_id,
        )

        # Extract token usage from call_info
        token_usage = {}
        if call_info:
            token_usage = {
                "prompt_tokens": call_info.get("prompt_num_tokens", 0),
                "completion_tokens": call_info.get("response_num_tokens", 0),
                "total_tokens": (
                    call_info.get("prompt_num_tokens", 0) + call_info.get("response_num_tokens", 0)
                ),
            }

        return EvolutionResult(
            original_playbook=playbook_content,
            evolved_playbook=evolved_playbook,
            outcomes_processed=len(outcomes),
            operations_applied=operations,
            token_usage=token_usage,
        )

    async def evolve_playbook_async(
        self,
        playbook_content: str,
        outcomes: list[OutcomeData],
    ) -> EvolutionResult:
        """Async version of evolve_playbook.

        Currently wraps the sync version since ace_core is sync.
        Future versions may use native async LLM calls.

        Args:
            playbook_content: Current playbook content.
            outcomes: List of outcome data.

        Returns:
            EvolutionResult with the evolved playbook.
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.evolve_playbook,
            playbook_content,
            outcomes,
        )
