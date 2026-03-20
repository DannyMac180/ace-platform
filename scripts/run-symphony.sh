#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv_symphony="$repo_root/venv/bin/symphony"
venv_python="$repo_root/venv/bin/python"
workflow_example_path="$repo_root/WORKFLOW.example.md"
workflow_local_path="$repo_root/WORKFLOW.local.md"
workflow_default_path="$repo_root/WORKFLOW.md"
workflow_rendered_path="$repo_root/.symphony-workflow.generated.md"
workflow_builder="$repo_root/scripts/build-symphony-workflow.py"
if [[ -f "$workflow_local_path" ]]; then
  workflow_override_path="$workflow_local_path"
else
  workflow_override_path="$workflow_default_path"
fi
port="${SYMPHONY_PORT:-4000}"
term_value="${TERM:-xterm-256color}"
linear_workspace_url_key="${SYMPHONY_LINEAR_WORKSPACE_URL_KEY:-danmac}"
linear_team_key="${SYMPHONY_LINEAR_TEAM_KEY:-DAN}"

if [[ ! -x "$venv_symphony" ]]; then
  echo "Missing Symphony launcher at $venv_symphony" >&2
  echo "Create the repo virtualenv and run setup first." >&2
  exit 1
fi

if [[ ! -x "$venv_python" ]]; then
  echo "Missing Python runtime at $venv_python" >&2
  echo "Create the repo virtualenv and run setup first." >&2
  exit 1
fi

if [[ ! -f "$workflow_example_path" ]]; then
  echo "Missing workflow example at $workflow_example_path" >&2
  exit 1
fi

if [[ ! -f "$workflow_override_path" ]]; then
  echo "Missing local workflow override at $workflow_override_path" >&2
  echo "Create it from the example template first:" >&2
  echo "  cp WORKFLOW.example.md WORKFLOW.local.md" >&2
  exit 1
fi

if [[ ! -f "$workflow_builder" ]]; then
  echo "Missing workflow builder at $workflow_builder" >&2
  exit 1
fi

if [[ -z "${LINEAR_API_KEY:-}" ]]; then
  echo "LINEAR_API_KEY is not set in the current shell." >&2
  exit 1
fi

"$venv_python" "$workflow_builder" \
  --base "$workflow_example_path" \
  --local "$workflow_override_path" \
  --output "$workflow_rendered_path"

"$venv_python" -m ace_platform.symphony.linear_guard \
  --workflow "$workflow_rendered_path" \
  --expected-workspace-url-key "$linear_workspace_url_key" \
  --expected-team-key "$linear_team_key"

cd "$repo_root"
export PATH="$repo_root/scripts:$PATH"
TERM="$term_value" exec "$venv_symphony" \
  --port "$port" \
  --i-understand-that-this-will-be-running-without-the-usual-guardrails \
  "$workflow_rendered_path"
