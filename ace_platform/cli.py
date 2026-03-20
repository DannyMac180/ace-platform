"""CLI for ACE project bootstrap and playbook portability."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib

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
MINIMUM_PYTHON = (3, 10)
SUPPORTED_MCP_TRANSPORTS = {"stdio", "http"}
INIT_NEXT_COMMANDS = ["ace doctor", "ace seed", "ace benchmark"]
IMPLEMENTED_COMMANDS = frozenset({"doctor", "export", "import", "init"})


@dataclass(frozen=True)
class InitLayout:
    project_name: str
    docs_dir: str
    examples_dir: str
    playbooks_dir: str
    readme_path: str
    git_enabled: bool


@dataclass(frozen=True)
class DoctorFinding:
    level: str
    title: str
    detail: str
    hint: str | None = None


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        return _run_init(args)
    if args.command == "doctor":
        return _run_doctor(args)
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

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Validate the local ACE environment and surface remediation hints.",
    )
    doctor_parser.add_argument(
        "--path",
        default=".",
        help="Project directory to inspect. Defaults to the current directory.",
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


def _run_doctor(args: argparse.Namespace) -> int:
    project_root = Path(args.path).expanduser().resolve()
    findings = _doctor_findings(project_root)

    failing = [finding for finding in findings if finding.level == "fail"]
    warnings = [finding for finding in findings if finding.level == "warn"]

    print(f"ACE doctor report for {project_root}")
    for finding in findings:
        print(_format_doctor_finding(finding))

    if failing:
        print(
            f"ACE doctor failed with {len(failing)} blocking issue(s) and {len(warnings)} warning(s).",
            file=sys.stderr,
        )
        return 1

    print(f"ACE doctor found no blocking issues and {len(warnings)} warning(s).")
    return 0


def _doctor_findings(project_root: Path) -> list[DoctorFinding]:
    findings = [_python_version_finding()]

    config_path = project_root / DEFAULT_CONFIG_FILENAME
    if not config_path.exists():
        findings.append(
            DoctorFinding(
                "fail",
                "Config file",
                f"{config_path} was not found.",
                f"Run `ace init --path {project_root}` to generate a starter config.",
            )
        )
        return findings

    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        findings.append(
            DoctorFinding(
                "fail",
                "Config file",
                f"{config_path.name} could not be parsed: {exc}.",
                "Fix the TOML syntax or regenerate the file with `ace init --force`.",
            )
        )
        return findings

    findings.extend(_validate_config(project_root, config_path, config))
    return findings


def _validate_config(
    project_root: Path,
    config_path: Path,
    config: object,
) -> list[DoctorFinding]:
    findings: list[DoctorFinding] = []
    if not isinstance(config, dict):
        return [
            DoctorFinding(
                "fail",
                "Config schema",
                f"{config_path.name} must decode to a top-level table.",
                "Regenerate the config with `ace init --force`.",
            )
        ]

    schema_version = config.get("schema_version")
    if schema_version == 1:
        findings.append(
            DoctorFinding(
                "ok",
                "Config schema",
                "schema_version = 1 is supported.",
            )
        )
    else:
        findings.append(
            DoctorFinding(
                "fail",
                "Config schema",
                f"schema_version must be 1, found {schema_version!r}.",
                "Regenerate the config with `ace init --force` or update the version number.",
            )
        )

    project = config.get("project")
    if not isinstance(project, dict):
        findings.append(
            DoctorFinding(
                "fail",
                "Project config",
                "The [project] table is missing or invalid.",
                "Ensure ace.toml contains the [project] settings written by `ace init`.",
            )
        )
        return findings

    project_root_value = project.get("root")
    if not isinstance(project_root_value, str) or not project_root_value.strip():
        findings.append(
            DoctorFinding(
                "fail",
                "Project root",
                "project.root must be a non-empty string.",
                'Set `root = "."` or another valid project path in [project].',
            )
        )
        resolved_project_root = project_root
    else:
        resolved_project_root = (project_root / project_root_value).resolve()
        if resolved_project_root.is_dir():
            findings.append(
                DoctorFinding(
                    "ok",
                    "Project root",
                    f"{resolved_project_root} exists.",
                )
            )
        else:
            findings.append(
                DoctorFinding(
                    "fail",
                    "Project root",
                    f"{resolved_project_root} does not exist.",
                    "Point project.root at a valid directory.",
                )
            )

    git_enabled = project.get("git_enabled")
    if git_enabled is True:
        if _command_available("git"):
            findings.append(
                DoctorFinding(
                    "ok",
                    "Git dependency",
                    "git is available for the configured project.",
                )
            )
        else:
            findings.append(
                DoctorFinding(
                    "fail",
                    "Git dependency",
                    "project.git_enabled is true but `git` is not available on PATH.",
                    "Install git or set `git_enabled = false` if this project does not use git.",
                )
            )
    elif git_enabled is False:
        findings.append(
            DoctorFinding(
                "ok",
                "Git dependency",
                "Git checks are disabled for this project.",
            )
        )
    else:
        findings.append(
            DoctorFinding(
                "fail",
                "Git dependency",
                f"project.git_enabled must be a boolean, found {git_enabled!r}.",
                "Set `git_enabled = true` or `git_enabled = false` in [project].",
            )
        )

    bootstrap = config.get("bootstrap")
    default_profile = None
    if not isinstance(bootstrap, dict):
        findings.append(
            DoctorFinding(
                "fail",
                "Bootstrap config",
                "The [bootstrap] table is missing or invalid.",
                "Ensure ace.toml contains the [bootstrap] settings written by `ace init`.",
            )
        )
    else:
        default_profile = bootstrap.get("default_profile")
        if default_profile in ("local", "hosted"):
            findings.append(
                DoctorFinding(
                    "ok",
                    "Default profile",
                    f"`{default_profile}` is supported.",
                )
            )
        else:
            findings.append(
                DoctorFinding(
                    "fail",
                    "Default profile",
                    f"default_profile must be `local` or `hosted`, found {default_profile!r}.",
                    "Update [bootstrap].default_profile to a supported value.",
                )
            )

    env_config = config.get("env")
    env_names = {
        "api_url_env": ACE_API_URL_ENV,
        "token_env": ACE_TOKEN_ENV,
        "api_key_env": ACE_API_KEY_ENV,
    }
    if isinstance(env_config, dict):
        for key, default_name in env_names.items():
            value = env_config.get(key)
            if isinstance(value, str) and value.strip():
                env_names[key] = value.strip()

    profiles = config.get("profiles")
    if not isinstance(profiles, dict):
        findings.append(
            DoctorFinding(
                "fail",
                "Profiles config",
                "The [profiles] table is missing or invalid.",
                "Ensure ace.toml contains at least [profiles.local] and [profiles.hosted].",
            )
        )
        return findings

    for profile_name in ("local", "hosted"):
        profile = profiles.get(profile_name)
        if not isinstance(profile, dict):
            findings.append(
                DoctorFinding(
                    "fail",
                    f"{profile_name} profile",
                    f"[profiles.{profile_name}] is missing or invalid.",
                    f"Regenerate ace.toml with `ace init --force` to restore [profiles.{profile_name}].",
                )
            )
            continue
        findings.extend(_validate_profile(profile_name, profile))

    if default_profile == "hosted" and not any(
        os.environ.get(env_names[name]) for name in ("token_env", "api_key_env")
    ):
        findings.append(
            DoctorFinding(
                "warn",
                "Hosted auth",
                "The hosted profile is the default but no hosted auth variable is set in this shell.",
                f"Export `{env_names['token_env']}` or `{env_names['api_key_env']}` before using hosted commands.",
            )
        )

    if (
        default_profile == "local"
        and not resolved_project_root.joinpath(".git").exists()
        and git_enabled
    ):
        findings.append(
            DoctorFinding(
                "warn",
                "Git workspace",
                f"{resolved_project_root} is not a git checkout even though git checks are enabled.",
                "Initialize git in the project root or set `git_enabled = false` if that is intentional.",
            )
        )

    return findings


def _validate_profile(profile_name: str, profile: dict[str, object]) -> list[DoctorFinding]:
    findings: list[DoctorFinding] = []

    api_url = profile.get("api_url")
    if isinstance(api_url, str) and _is_http_url(api_url):
        findings.append(
            DoctorFinding(
                "ok",
                f"{profile_name} API URL",
                f"{api_url} is a valid HTTP(S) URL.",
            )
        )
    else:
        findings.append(
            DoctorFinding(
                "fail",
                f"{profile_name} API URL",
                f"[profiles.{profile_name}].api_url must be a valid HTTP(S) URL, found {api_url!r}.",
                "Set api_url to an absolute http:// or https:// endpoint.",
            )
        )

    transport = profile.get("mcp_transport")
    if transport not in SUPPORTED_MCP_TRANSPORTS:
        findings.append(
            DoctorFinding(
                "fail",
                f"{profile_name} MCP transport",
                f"`{transport}` is not supported.",
                f"Use one of: {', '.join(sorted(SUPPORTED_MCP_TRANSPORTS))}.",
            )
        )
        return findings

    findings.append(
        DoctorFinding(
            "ok",
            f"{profile_name} MCP transport",
            f"`{transport}` is supported.",
        )
    )

    if transport == "stdio":
        mcp_command = profile.get("mcp_command")
        if not isinstance(mcp_command, str) or not mcp_command.strip():
            findings.append(
                DoctorFinding(
                    "fail",
                    f"{profile_name} MCP command",
                    f"[profiles.{profile_name}].mcp_command must be a non-empty string.",
                    "Set mcp_command to a command available on PATH, such as `python`.",
                )
            )
        elif _command_available(mcp_command):
            findings.append(
                DoctorFinding(
                    "ok",
                    f"{profile_name} MCP command",
                    f"`{mcp_command}` is available on PATH.",
                )
            )
        else:
            findings.append(
                DoctorFinding(
                    "fail",
                    f"{profile_name} MCP command",
                    f"`{mcp_command}` was not found on PATH.",
                    "Install the command or update mcp_command to a valid executable.",
                )
            )

        mcp_args = profile.get("mcp_args")
        if (
            isinstance(mcp_args, list)
            and mcp_args
            and all(isinstance(argument, str) and argument for argument in mcp_args)
        ):
            findings.append(
                DoctorFinding(
                    "ok",
                    f"{profile_name} MCP args",
                    f"{len(mcp_args)} stdio argument(s) configured.",
                )
            )
        else:
            findings.append(
                DoctorFinding(
                    "fail",
                    f"{profile_name} MCP args",
                    f"[profiles.{profile_name}].mcp_args must be a non-empty string list.",
                    "Set mcp_args to the command arguments required to launch the MCP server.",
                )
            )
    else:
        mcp_url = profile.get("mcp_url")
        if isinstance(mcp_url, str) and _is_http_url(mcp_url):
            findings.append(
                DoctorFinding(
                    "ok",
                    f"{profile_name} MCP URL",
                    f"{mcp_url} is a valid HTTP(S) URL.",
                )
            )
        else:
            findings.append(
                DoctorFinding(
                    "fail",
                    f"{profile_name} MCP URL",
                    f"[profiles.{profile_name}].mcp_url must be a valid HTTP(S) URL, found {mcp_url!r}.",
                    "Set mcp_url to the streamable HTTP or SSE endpoint for the hosted MCP server.",
                )
            )

    return findings


def _python_version_finding() -> DoctorFinding:
    if sys.version_info >= MINIMUM_PYTHON:
        return DoctorFinding(
            "ok",
            "Python runtime",
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} satisfies ACE's >=3.10 requirement.",
        )
    return DoctorFinding(
        "fail",
        "Python runtime",
        (
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} is not supported; "
            "ACE requires Python 3.10 or newer."
        ),
        "Install Python 3.10+ and recreate the virtual environment.",
    )


def _command_available(command: str) -> bool:
    if os.sep in command or (os.altsep and os.altsep in command):
        command_path = Path(command).expanduser()
        return command_path.is_file() and os.access(command_path, os.X_OK)
    return shutil.which(command) is not None


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _format_doctor_finding(finding: DoctorFinding) -> str:
    lines = [f"[{finding.level}] {finding.title}: {finding.detail}"]
    if finding.hint:
        lines.append(f"  hint: {finding.hint}")
    return "\n".join(lines)


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
