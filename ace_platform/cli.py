"""CLI for ACE project bootstrap, benchmarking, and playbook portability."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ace_core import EvalCase, EvalResult, EvalSpec, LocalEvalRunner
from ace_core.portability import bundle_from_json, bundle_to_json

ACE_API_URL_ENV = "ACE_API_URL"
ACE_TOKEN_ENV = "ACE_TOKEN"
ACE_API_KEY_ENV = "ACE_API_KEY"
DEFAULT_CONFIG_FILENAME = "ace.toml"
DEFAULT_HOSTED_API_URL = "https://aceagent.io"
DEFAULT_HOSTED_MCP_URL = f"{DEFAULT_HOSTED_API_URL}/mcp"
DEFAULT_LOCAL_API_URL = "http://localhost:8000"
DEFAULT_DOCS_URL = "https://docs.aceagent.io"


@dataclass(frozen=True)
class InitLayout:
    project_name: str
    docs_dir: str
    examples_dir: str
    playbooks_dir: str
    readme_path: str
    git_enabled: bool


@dataclass(frozen=True)
class BenchmarkCase:
    id: str
    prompt: str
    expected_output: str
    baseline_output: str
    ace_output: str
    metadata: dict[str, object]


@dataclass(frozen=True)
class BenchmarkSuite:
    id: str
    metric: str
    cases: list[BenchmarkCase]
    metadata: dict[str, object]


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        return _run_init(args)
    if args.command == "benchmark":
        return _run_benchmark(args)
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

    benchmark_parser = subparsers.add_parser(
        "benchmark",
        help="Compare baseline and ACE-assisted outputs against a local benchmark file.",
    )
    benchmark_parser.add_argument(
        "--input",
        required=True,
        help="Source benchmark JSON path, or '-' for stdin.",
    )
    benchmark_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format for the benchmark summary. Defaults to text.",
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

    config_path = project_root / DEFAULT_CONFIG_FILENAME
    if config_path.exists() and not args.force:
        print(
            f"ACE init aborted: {config_path} already exists. Re-run with --force to overwrite it.",
            file=sys.stderr,
        )
        return 1

    layout = _detect_layout(project_root, explicit_project_name=args.project_name)
    config_payload = _render_init_config(
        layout=layout,
        default_profile=args.default_profile,
        hosted_api_url=args.api_url,
        local_api_url=args.local_api_url,
        docs_url=args.docs_url,
    )
    config_path.write_text(config_payload, encoding="utf-8")
    print(
        _format_init_summary(
            project_root=project_root,
            config_path=config_path,
            layout=layout,
            default_profile=args.default_profile,
        )
    )
    return 0


def _run_benchmark(args: argparse.Namespace) -> int:
    try:
        suite = _load_benchmark_suite(args.input)
        baseline_result, ace_result = asyncio.run(_evaluate_benchmark_suite(suite))
        payload = _build_benchmark_summary(
            suite=suite,
            baseline_result=baseline_result,
            ace_result=ace_result,
        )
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"ACE benchmark failed: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_format_benchmark_summary(payload))
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
) -> str:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return "\n".join(
        [
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
            f'generated_at = "{generated_at}"',
            "",
            "[bootstrap]",
            f'default_profile = "{default_profile}"',
            f'docs_url = "{docs_url}"',
            'recommended_next_commands = ["ace doctor", "ace seed", "ace benchmark"]',
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


def _load_benchmark_suite(path: str) -> BenchmarkSuite:
    payload = json.loads(_read_text(path))
    if not isinstance(payload, dict):
        raise ValueError("benchmark input must be a JSON object.")

    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("benchmark input must include a non-empty 'cases' list.")

    raw_metadata = payload.get("metadata")
    if raw_metadata is not None and not isinstance(raw_metadata, dict):
        raise ValueError("benchmark 'metadata' must be an object when provided.")

    suite_id = payload.get("id") or payload.get("name") or "ace-benchmark"
    metric = _benchmark_required_string(payload, "metric", "benchmark input")
    cases = [
        _parse_benchmark_case(raw_case, index=index)
        for index, raw_case in enumerate(raw_cases, start=1)
    ]
    return BenchmarkSuite(
        id=str(suite_id),
        metric=metric,
        cases=cases,
        metadata=dict(raw_metadata or {}),
    )


def _parse_benchmark_case(raw_case: object, *, index: int) -> BenchmarkCase:
    if not isinstance(raw_case, dict):
        raise ValueError(f"benchmark case {index} must be an object.")

    raw_metadata = raw_case.get("metadata")
    if raw_metadata is not None and not isinstance(raw_metadata, dict):
        raise ValueError(f"benchmark case {index} metadata must be an object when provided.")

    case_id = raw_case.get("id") or f"case-{index}"
    return BenchmarkCase(
        id=str(case_id),
        prompt=_benchmark_required_string(raw_case, "prompt", f"benchmark case {index}"),
        expected_output=_benchmark_required_string(
            raw_case,
            "expected_output",
            f"benchmark case {index}",
        ),
        baseline_output=_benchmark_required_string(
            raw_case,
            "baseline_output",
            f"benchmark case {index}",
        ),
        ace_output=_benchmark_required_string(raw_case, "ace_output", f"benchmark case {index}"),
        metadata=dict(raw_metadata or {}),
    )


def _benchmark_required_string(
    payload: dict[str, object],
    field_name: str,
    context: str,
) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str):
        raise ValueError(f"{context} field '{field_name}' must be a string.")
    return value


async def _evaluate_benchmark_suite(suite: BenchmarkSuite) -> tuple[EvalResult, EvalResult]:
    runner = LocalEvalRunner()
    baseline_result = await runner.run(_build_eval_spec(suite, variant="baseline"))
    ace_result = await runner.run(_build_eval_spec(suite, variant="ace"))
    return baseline_result, ace_result


def _build_eval_spec(suite: BenchmarkSuite, *, variant: str) -> EvalSpec:
    output_field = "baseline_output" if variant == "baseline" else "ace_output"
    return EvalSpec(
        id=f"{suite.id}:{variant}",
        metric=suite.metric,
        metadata=dict(suite.metadata),
        cases=[
            EvalCase(
                id=case.id,
                prompt=case.prompt,
                expected_output=case.expected_output,
                metadata={
                    **case.metadata,
                    "actual_output": getattr(case, output_field),
                },
            )
            for case in suite.cases
        ],
    )


def _build_benchmark_summary(
    *,
    suite: BenchmarkSuite,
    baseline_result: EvalResult,
    ace_result: EvalResult,
) -> dict[str, object]:
    case_rows: list[dict[str, object]] = []
    ace_wins = 0
    baseline_wins = 0
    ties = 0
    improved_case_ids: list[str] = []
    regressed_case_ids: list[str] = []

    for baseline_case, ace_case in zip(
        baseline_result.case_results,
        ace_result.case_results,
        strict=True,
    ):
        if ace_case.passed and not baseline_case.passed:
            outcome = "ace_win"
            ace_wins += 1
            improved_case_ids.append(ace_case.case_id)
        elif baseline_case.passed and not ace_case.passed:
            outcome = "baseline_win"
            baseline_wins += 1
            regressed_case_ids.append(ace_case.case_id)
        else:
            outcome = "tie"
            ties += 1

        case_rows.append(
            {
                "id": ace_case.case_id,
                "baseline_passed": baseline_case.passed,
                "ace_passed": ace_case.passed,
                "baseline_score": baseline_case.score,
                "ace_score": ace_case.score,
                "outcome": outcome,
            }
        )

    baseline_summary = _summarize_eval_result(baseline_result)
    ace_summary = _summarize_eval_result(ace_result)
    return {
        "benchmark_id": suite.id,
        "metric": suite.metric,
        "case_count": len(case_rows),
        "baseline": baseline_summary,
        "ace": ace_summary,
        "comparison": {
            "net_passed_delta": ace_summary["passed_cases"] - baseline_summary["passed_cases"],
            "pass_rate_delta": ace_summary["pass_rate"] - baseline_summary["pass_rate"],
            "score_delta": (ace_summary["score"] or 0.0) - (baseline_summary["score"] or 0.0),
            "ace_wins": ace_wins,
            "baseline_wins": baseline_wins,
            "ties": ties,
            "improved_case_ids": improved_case_ids,
            "regressed_case_ids": regressed_case_ids,
        },
        "cases": case_rows,
    }


def _summarize_eval_result(result: EvalResult) -> dict[str, float | int | None]:
    total_cases = len(result.case_results)
    passed_cases = sum(1 for case_result in result.case_results if case_result.passed)
    return {
        "passed_cases": passed_cases,
        "case_count": total_cases,
        "pass_rate": (passed_cases / total_cases) if total_cases else 0.0,
        "score": result.score,
    }


def _format_benchmark_summary(payload: dict[str, object]) -> str:
    baseline = payload["baseline"]
    ace = payload["ace"]
    comparison = payload["comparison"]
    improved_cases = comparison["improved_case_ids"]
    regressed_cases = comparison["regressed_case_ids"]
    lines = [
        f"Benchmark: {payload['benchmark_id']}",
        f"Metric: {payload['metric']}",
        f"Cases: {payload['case_count']}",
        "",
        "Baseline",
        (
            f"- Passed: {baseline['passed_cases']}/{baseline['case_count']} "
            f"({_format_ratio(float(baseline['pass_rate']))})"
        ),
        f"- Average score: {_format_score(baseline['score'])}",
        "",
        "ACE-assisted",
        f"- Passed: {ace['passed_cases']}/{ace['case_count']} ({_format_ratio(float(ace['pass_rate']))})",
        f"- Average score: {_format_score(ace['score'])}",
        "",
        "Comparison",
        f"- Net passed cases: {_format_signed_int(int(comparison['net_passed_delta']))}",
        f"- Pass rate delta: {_format_signed_ratio(float(comparison['pass_rate_delta']))}",
        f"- Average score delta: {_format_signed_score(float(comparison['score_delta']))}",
        (
            f"- Head-to-head: {comparison['ace_wins']} ACE wins, "
            f"{comparison['baseline_wins']} baseline wins, {comparison['ties']} ties"
        ),
    ]
    if improved_cases:
        lines.append(f"- Improved cases: {', '.join(improved_cases)}")
    if regressed_cases:
        lines.append(f"- Regressed cases: {', '.join(regressed_cases)}")
    return "\n".join(lines)


def _format_ratio(value: float) -> str:
    return f"{value * 100:.1f}%"


def _format_score(value: object) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.3f}"


def _format_signed_ratio(value: float) -> str:
    return f"{value * 100:+.1f} pts"


def _format_signed_score(value: float) -> str:
    return f"{value:+.3f}"


def _format_signed_int(value: int) -> str:
    return f"{value:+d}"


__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
