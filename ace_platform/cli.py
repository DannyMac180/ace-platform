"""CLI for ACE project bootstrap and playbook portability."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ace_core.portability import bundle_from_json, bundle_to_json

ACE_API_URL_ENV = "ACE_API_URL"
ACE_TOKEN_ENV = "ACE_TOKEN"
ACE_API_KEY_ENV = "ACE_API_KEY"
DEFAULT_CONFIG_FILENAME = "ace.toml"
DEFAULT_HOSTED_API_URL = "https://aceagent.io"
DEFAULT_HOSTED_MCP_URL = f"{DEFAULT_HOSTED_API_URL}/mcp"
DEFAULT_LOCAL_API_URL = "http://localhost:8000"
DEFAULT_DOCS_URL = "https://docs.aceagent.io"
INIT_NEXT_COMMANDS = ["ace doctor", "ace seed", "ace benchmark"]
IMPLEMENTED_COMMANDS = frozenset({"export", "import", "init"})


@dataclass(frozen=True)
class InitLayout:
    project_name: str
    docs_dir: str
    examples_dir: str
    playbooks_dir: str
    readme_path: str
    git_enabled: bool


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        return _run_init(args)
    if args.command == "export":
        return _run_export(args, parser)
    if args.command == "import":
        return _run_import(args, parser)

    parser.print_help()
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ace",
        description="Bootstrap ACE projects and move playbooks between hosted and local contexts.",
    )
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser(
        "init",
        help="Generate a default ACE project config for local and hosted workflows.",
    )
    init_parser.add_argument(
        "--path",
        default=".",
        help="Project directory to initialize. Defaults to the current directory.",
    )
    init_parser.add_argument(
        "--project-name",
        default=None,
        help="Project name to write into the generated config. Defaults to the directory name.",
    )
    init_parser.add_argument(
        "--default-profile",
        choices=("local", "hosted"),
        default="local",
        help="Default profile to use after bootstrap. Defaults to local.",
    )
    init_parser.add_argument(
        "--api-url",
        default=os.environ.get(ACE_API_URL_ENV, DEFAULT_HOSTED_API_URL),
        help=(
            "Hosted ACE API base URL. Defaults to $ACE_API_URL when set, "
            f"otherwise {DEFAULT_HOSTED_API_URL}."
        ),
    )
    init_parser.add_argument(
        "--local-api-url",
        default=DEFAULT_LOCAL_API_URL,
        help=f"Local ACE API base URL. Defaults to {DEFAULT_LOCAL_API_URL}.",
    )
    init_parser.add_argument(
        "--docs-url",
        default=DEFAULT_DOCS_URL,
        help=f"ACE documentation URL. Defaults to {DEFAULT_DOCS_URL}.",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing ace.toml file in the target directory.",
    )
    init_parser.add_argument(
        "--output",
        choices=("text", "json"),
        default="text",
        help="Output mode for init results. Defaults to text.",
    )
    init_parser.add_argument(
        "--deterministic",
        action="store_true",
        help="Omit time-based metadata from generated config output.",
    )
    init_parser.add_argument(
        "--agent",
        action="store_true",
        help="Enable deterministic, machine-readable init output for coding agents.",
    )

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--api-url",
        default=os.environ.get(ACE_API_URL_ENV),
        help=f"ACE API base URL. Defaults to ${ACE_API_URL_ENV}.",
    )
    common.add_argument(
        "--token",
        default=os.environ.get(ACE_TOKEN_ENV),
        help=f"Bearer token for ACE API auth. Defaults to ${ACE_TOKEN_ENV}.",
    )

    export_parser = subparsers.add_parser(
        "export",
        parents=[common],
        help="Export hosted playbooks and traces to a local bundle file.",
    )
    export_parser.add_argument(
        "--output",
        required=True,
        help="Destination path for the exported bundle, or '-' for stdout.",
    )

    import_parser = subparsers.add_parser(
        "import",
        parents=[common],
        help="Import a local bundle file into the hosted ACE API.",
    )
    import_parser.add_argument(
        "--input",
        required=True,
        help="Source bundle path to import, or '-' for stdin.",
    )

    return parser


def _run_export(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    api_url = _required_value(args.api_url, "api-url", parser)
    token = _required_value(args.token, "token", parser)
    response = _request(
        "GET",
        f"{api_url.rstrip('/')}/playbooks/export",
        token=token,
    )
    if response is None:
        return 1

    bundle = bundle_from_json(response.text)
    _write_text(args.output, bundle_to_json(bundle))
    destination = "stdout" if args.output == "-" else args.output
    stream = sys.stderr if args.output == "-" else sys.stdout
    print(f"Exported {len(bundle.playbooks)} playbooks to {destination}", file=stream)
    return 0


def _run_import(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    api_url = _required_value(args.api_url, "api-url", parser)
    token = _required_value(args.token, "token", parser)
    bundle = bundle_from_json(_read_text(args.input))
    response = _request(
        "POST",
        f"{api_url.rstrip('/')}/playbooks/import",
        token=token,
        json=bundle.model_dump(mode="json", exclude_none=True),
    )
    if response is None:
        return 1

    payload = response.json()
    print(f"Imported {payload['imported_count']} playbooks")
    return 0


def _run_init(args: argparse.Namespace) -> int:
    project_root = Path(args.path).expanduser().resolve()
    project_root.mkdir(parents=True, exist_ok=True)
    output_mode = _init_output_mode(args)
    deterministic = args.deterministic or args.agent

    config_path = project_root / DEFAULT_CONFIG_FILENAME
    if config_path.exists() and not args.force:
        message = (
            f"ACE init aborted: {config_path} already exists. Re-run with --force to overwrite it."
        )
        if output_mode == "json":
            _emit_json(
                _build_init_error_payload(
                    code="config_exists",
                    message=message,
                    project_root=project_root,
                    config_path=config_path,
                    args=args,
                    deterministic=deterministic,
                )
            )
        else:
            print(message, file=sys.stderr)
        return 1

    layout = _detect_layout(project_root, explicit_project_name=args.project_name)
    config_payload = _render_init_config(
        layout=layout,
        default_profile=args.default_profile,
        hosted_api_url=args.api_url,
        local_api_url=args.local_api_url,
        docs_url=args.docs_url,
        deterministic=deterministic,
    )
    config_path.write_text(config_payload, encoding="utf-8")
    if output_mode == "json":
        _emit_json(
            _build_init_success_payload(
                project_root=project_root,
                config_path=config_path,
                layout=layout,
                default_profile=args.default_profile,
                config_payload=config_payload,
                args=args,
                deterministic=deterministic,
            )
        )
    else:
        print(
            _format_init_summary(
                project_root=project_root,
                config_path=config_path,
                layout=layout,
                default_profile=args.default_profile,
            )
        )
    return 0


def _request(
    method: str,
    url: str,
    *,
    token: str,
    json: dict | None = None,
) -> httpx.Response | None:
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.request(
                method,
                url,
                headers={"Authorization": f"Bearer {token}"},
                json=json,
            )
    except httpx.HTTPError as exc:
        print(f"ACE CLI request failed: {exc}", file=sys.stderr)
        return None

    if response.is_error:
        message = response.text.strip() or f"HTTP {response.status_code}"
        print(f"ACE CLI request failed: {message}", file=sys.stderr)
        return None

    return response


def _required_value(
    value: str | None,
    flag_name: str,
    parser: argparse.ArgumentParser,
) -> str:
    if value:
        return value
    parser.error(f"--{flag_name} is required")
    raise AssertionError("argparse should have exited")


def _read_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def _write_text(path: str, payload: str) -> None:
    if path == "-":
        sys.stdout.write(payload)
        if not payload.endswith("\n"):
            sys.stdout.write("\n")
        return

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(payload, encoding="utf-8")


def _detect_layout(project_root: Path, *, explicit_project_name: str | None) -> InitLayout:
    project_name = explicit_project_name or project_root.name or "ace-project"
    docs_dir = _first_existing_name(project_root, "docs", "doc") or "docs"
    examples_dir = _first_existing_name(project_root, "examples", "example") or "examples"
    playbooks_dir = _first_existing_name(project_root, "playbooks") or "playbooks"
    readme_path = (
        _first_existing_name(project_root, "README.md", "README.rst", "README.txt") or "README.md"
    )
    return InitLayout(
        project_name=project_name,
        docs_dir=docs_dir,
        examples_dir=examples_dir,
        playbooks_dir=playbooks_dir,
        readme_path=readme_path,
        git_enabled=(project_root / ".git").exists(),
    )


def _first_existing_name(project_root: Path, *candidates: str) -> str | None:
    for candidate in candidates:
        if (project_root / candidate).exists():
            return candidate
    return None


def _render_init_config(
    *,
    layout: InitLayout,
    default_profile: str,
    hosted_api_url: str,
    local_api_url: str,
    docs_url: str,
    deterministic: bool,
) -> str:
    lines = [
        "# Generated by `ace init`.",
        "# Review the defaults, then run `ace doctor`, `ace seed`, and `ace benchmark`.",
        "schema_version = 1",
        "",
        "[project]",
        f'name = "{layout.project_name}"',
        'root = "."',
        f'docs_dir = "{layout.docs_dir}"',
        f'examples_dir = "{layout.examples_dir}"',
        f'playbooks_dir = "{layout.playbooks_dir}"',
        f'readme_path = "{layout.readme_path}"',
        f"git_enabled = {_format_toml_bool(layout.git_enabled)}",
    ]
    if not deterministic:
        generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        lines.append(f'generated_at = "{generated_at}"')

    lines.extend(
        [
            "",
            "[bootstrap]",
            f'default_profile = "{default_profile}"',
            f'docs_url = "{docs_url}"',
            f"recommended_next_commands = {_format_toml_string_list(INIT_NEXT_COMMANDS)}",
            "",
            "[env]",
            f'api_url_env = "{ACE_API_URL_ENV}"',
            f'token_env = "{ACE_TOKEN_ENV}"',
            f'api_key_env = "{ACE_API_KEY_ENV}"',
            "",
            "[profiles.local]",
            f'api_url = "{local_api_url}"',
            'mcp_transport = "stdio"',
            'mcp_command = "python"',
            'mcp_args = ["-m", "ace_platform.mcp.server", "stdio"]',
            "",
            "[profiles.hosted]",
            f'api_url = "{hosted_api_url}"',
            'mcp_transport = "http"',
            f'mcp_url = "{hosted_api_url.rstrip("/")}/mcp"',
            "",
        ]
    )
    return "\n".join(lines)


def _format_init_summary(
    *,
    project_root: Path,
    config_path: Path,
    layout: InitLayout,
    default_profile: str,
) -> str:
    return "\n".join(
        [
            f"Initialized ACE in {project_root}",
            f"- Wrote {config_path.name}",
            f"- Project name: {layout.project_name}",
            f"- Default profile: {default_profile}",
            f"- Playbooks directory: {layout.playbooks_dir}",
            f"- Docs directory: {layout.docs_dir}",
            f"- README path: {layout.readme_path}",
            "- Next commands: ace doctor, ace seed, ace benchmark",
        ]
    )


def _format_toml_bool(value: bool) -> str:
    return "true" if value else "false"


def _format_toml_string_list(values: list[str]) -> str:
    return "[" + ", ".join(f'"{value}"' for value in values) + "]"


def _init_output_mode(args: argparse.Namespace) -> str:
    if args.agent:
        return "json"
    return args.output


def _build_init_success_payload(
    *,
    project_root: Path,
    config_path: Path,
    layout: InitLayout,
    default_profile: str,
    config_payload: str,
    args: argparse.Namespace,
    deterministic: bool,
) -> dict[str, object]:
    return {
        "status": "ok",
        "mode": "agent" if args.agent else "standard",
        "deterministic": deterministic,
        "project_root": str(project_root),
        "config_path": str(config_path),
        "default_profile": default_profile,
        "force": args.force,
        "layout": asdict(layout),
        "recommended_next_commands": INIT_NEXT_COMMANDS,
        "follow_up_commands": _build_follow_up_commands(INIT_NEXT_COMMANDS),
        "config": config_payload,
    }


def _build_init_error_payload(
    *,
    code: str,
    message: str,
    project_root: Path,
    config_path: Path,
    args: argparse.Namespace,
    deterministic: bool,
) -> dict[str, object]:
    return {
        "status": "error",
        "mode": "agent" if args.agent else "standard",
        "deterministic": deterministic,
        "project_root": str(project_root),
        "config_path": str(config_path),
        "error": {
            "code": code,
            "message": message,
        },
    }


def _build_follow_up_commands(commands: list[str]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for command in commands:
        command_name = command.split(maxsplit=1)[1]
        available = command_name in IMPLEMENTED_COMMANDS
        items.append(
            {
                "command": command,
                "available": available,
                "reason": None if available else "command not implemented yet",
            }
        )
    return items


def _emit_json(payload: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
    sys.stdout.write("\n")


__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
