"""CLI for portable playbook import/export."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

from ace_core.portability import bundle_from_json, bundle_to_json

ACE_API_URL_ENV = "ACE_API_URL"
ACE_TOKEN_ENV = "ACE_TOKEN"


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "export":
        return _run_export(args, parser)
    if args.command == "import":
        return _run_import(args, parser)

    parser.print_help()
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ace",
        description="Move ACE playbooks and traces between hosted and local contexts.",
    )
    subparsers = parser.add_subparsers(dest="command")

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


__all__ = ["main"]
