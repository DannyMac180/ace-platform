"""Workflow file loading and strict prompt rendering."""

from __future__ import annotations

from pathlib import Path

import yaml
from jinja2 import Environment, StrictUndefined, TemplateError, TemplateSyntaxError

from ace_platform.symphony.errors import WorkflowError
from ace_platform.symphony.models import Issue, WorkflowDefinition

DEFAULT_PROMPT = "You are working on an issue from Linear."
CONTINUATION_GUIDANCE = (
    "Continue working on this issue using the existing thread context. "
    "Avoid repeating completed work. If you have reached a natural handoff or the "
    "ticket is no longer active, stop cleanly."
)


def load_workflow_definition(path: Path) -> WorkflowDefinition:
    """Load a workflow file with optional YAML front matter."""

    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise WorkflowError("missing_workflow_file", f"Workflow file not found: {path}") from exc
    except OSError as exc:
        raise WorkflowError(
            "missing_workflow_file", f"Unable to read workflow file: {path}"
        ) from exc

    config: dict[str, object] = {}
    body = raw
    if raw.startswith("---"):
        lines = raw.splitlines(keepends=True)
        if not lines or lines[0].strip() != "---":
            raise WorkflowError("workflow_parse_error", "Invalid workflow front matter")

        closing_index = None
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                closing_index = index
                break
        if closing_index is None:
            raise WorkflowError("workflow_parse_error", "Unterminated workflow front matter")

        front_matter = "".join(lines[1:closing_index])
        body = "".join(lines[closing_index + 1 :])
        try:
            loaded = yaml.safe_load(front_matter) or {}
        except yaml.YAMLError as exc:
            raise WorkflowError(
                "workflow_parse_error", "Invalid YAML in workflow front matter"
            ) from exc

        if not isinstance(loaded, dict):
            raise WorkflowError(
                "workflow_front_matter_not_a_map",
                "Workflow front matter must decode to an object",
            )
        config = loaded

    return WorkflowDefinition(config=config, prompt_template=body.strip())


def _template_environment() -> Environment:
    return Environment(undefined=StrictUndefined, autoescape=False)


def render_issue_prompt(
    workflow: WorkflowDefinition,
    issue: Issue,
    attempt: int | None,
) -> str:
    """Render the first-turn prompt for an issue."""

    template_source = workflow.prompt_template or DEFAULT_PROMPT
    try:
        template = _template_environment().from_string(template_source)
    except TemplateSyntaxError as exc:
        raise WorkflowError("template_parse_error", str(exc)) from exc

    try:
        return template.render(issue=issue.to_template_context(), attempt=attempt).strip()
    except TemplateError as exc:
        raise WorkflowError("template_render_error", str(exc)) from exc


def build_turn_prompt(
    workflow: WorkflowDefinition,
    issue: Issue,
    attempt: int | None,
    turn_number: int,
    max_turns: int,
) -> str:
    """Build the first-turn prompt or continuation guidance."""

    if turn_number <= 1:
        return render_issue_prompt(workflow, issue, attempt)

    return (
        f"{CONTINUATION_GUIDANCE}\n\n"
        f"Continuation turn {turn_number} of {max_turns} for {issue.identifier}."
    )
