#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import re
import sys
from pathlib import Path

import yaml

WORKFLOW_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def parse_workflow(path: Path) -> tuple[dict, str]:
    text = path.read_text()
    match = WORKFLOW_RE.match(text)
    if not match:
        raise ValueError(f"{path} is missing YAML frontmatter")
    frontmatter_text, body = match.groups()
    data = yaml.safe_load(frontmatter_text) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} frontmatter must be a mapping")
    return data, body


def deep_merge(base: dict, override: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def build_workflow(base_path: Path, local_path: Path, output_path: Path) -> None:
    base_frontmatter, base_body = parse_workflow(base_path)
    local_frontmatter, local_body = parse_workflow(local_path)
    merged_frontmatter = deep_merge(base_frontmatter, local_frontmatter)

    if local_body.strip() and local_body != base_body:
        print(
            (
                f"Warning: {local_path.name} contains workflow body content that "
                "differs from the tracked example. Using the tracked example body "
                "so shared workflow logic stays current."
            ),
            file=sys.stderr,
        )

    rendered_frontmatter = yaml.safe_dump(
        merged_frontmatter,
        sort_keys=False,
        default_flow_style=False,
    ).strip()
    output_path.write_text(f"---\n{rendered_frontmatter}\n---\n{base_body}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a Symphony workflow from the tracked example plus local overrides.",
    )
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--local", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    build_workflow(args.base, args.local, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
