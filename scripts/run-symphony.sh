#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv_symphony="$repo_root/venv/bin/symphony"
workflow_path="$repo_root/WORKFLOW.md"
port="${SYMPHONY_PORT:-4000}"
term_value="${TERM:-xterm-256color}"

if [[ ! -x "$venv_symphony" ]]; then
  echo "Missing Symphony launcher at $venv_symphony" >&2
  echo "Create the repo virtualenv and run setup first." >&2
  exit 1
fi

if [[ ! -f "$workflow_path" ]]; then
  echo "Missing workflow file at $workflow_path" >&2
  echo "Create it from the example template first:" >&2
  echo "  cp WORKFLOW.example.md WORKFLOW.md" >&2
  exit 1
fi

if [[ -z "${LINEAR_API_KEY:-}" ]]; then
  echo "LINEAR_API_KEY is not set in the current shell." >&2
  exit 1
fi

cd "$repo_root"
TERM="$term_value" exec "$venv_symphony" \
  --port "$port" \
  --i-understand-that-this-will-be-running-without-the-usual-guardrails \
  "$workflow_path"
