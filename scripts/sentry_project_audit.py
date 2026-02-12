#!/usr/bin/env python3
"""Authenticated Sentry project audit helper for observability controls.

This script checks core project settings required by the Sentry observability audit:
- project metadata resolvable by API
- DSN keys present
- alert rules existence
- inbound filter settings
- ownership rules presence
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

SENTRY_API_BASE_DEFAULT = "https://sentry.io"


@dataclass
class AuditCheck:
    """Single check for project telemetry posture."""

    name: str
    status: str
    details: str


def _build_request(url: str, token: str) -> urllib.request.Request:
    request = urllib.request.Request(url)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Content-Type", "application/json")
    return request


def _get_json(url: str, token: str) -> Any:
    request = _build_request(url, token)
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload


def _render_checks(checks: list[AuditCheck]) -> dict[str, Any]:
    return {
        "status": "fail" if any(check.status == "fail" for check in checks) else "ok",
        "checks": [check.__dict__ for check in checks],
    }


def run_audit(
    *,
    token: str,
    org: str,
    project: str,
    base_url: str,
    require_alert_rules: bool = False,
    strict: bool = False,
) -> int:
    checks: list[AuditCheck] = []

    try:
        project_info = _get_json(
            f"{base_url}/api/0/projects/{org}/{project}/",
            token,
        )
        checks.append(
            AuditCheck(
                "project_lookup",
                "pass",
                f"Project '{project_info.get('slug', project)}' resolved",
            )
        )
    except urllib.error.HTTPError as exc:
        return _render_fail(
            checks,
            f"project_lookup failed: {exc.code} {exc.reason}",
        )
    except urllib.error.URLError as exc:
        return _render_fail(
            checks,
            f"project_lookup failed: network error {exc.reason}",
        )
    except (ValueError, json.JSONDecodeError) as exc:
        return _render_fail(
            checks,
            f"project_lookup failed: invalid json response ({exc})",
        )

    checkers = [
        (
            "sentry_keys",
            lambda: len(_get_json(f"{base_url}/api/0/projects/{org}/{project}/keys/", token)) > 0,
            "DSN keys configured",
        ),
        (
            "inbound_filters",
            lambda: bool(
                _get_json(
                    f"{base_url}/api/0/projects/{org}/{project}/filters/",
                    token,
                ).get("sensitive_fields")
            ),
            "Inbound filters endpoint returned sensitive field settings",
        ),
        (
            "alert_rules",
            lambda: len(
                _get_json(
                    f"{base_url}/api/0/projects/{org}/{project}/rules/",
                    token,
                )
            )
            > 0,
            "At least one alert rule is configured",
        ),
        (
            "ownership_rules",
            lambda: len(
                _get_json(
                    f"{base_url}/api/0/projects/{org}/{project}/ownership/",
                    token,
                )
            )
            > 0,
            "Ownership mapping exists",
        ),
    ]

    alert_rules_configured = False

    for name, checker, details in checkers:
        try:
            passed = checker()
            if name == "alert_rules":
                alert_rules_configured = bool(passed)
            checks.append(
                AuditCheck(
                    name,
                    "pass"
                    if passed
                    else "warn"
                    if name in {"alert_rules", "ownership_rules"}
                    else "fail",
                    details if passed else f"{details} (missing)",
                )
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            checks.append(
                AuditCheck(
                    name,
                    "fail",
                    f"{name} lookup failed: {exc}",
                )
            )

    if require_alert_rules and not alert_rules_configured:
        checks.append(
            AuditCheck(
                "alert_rule_requirement",
                "fail",
                "No alert rules were configured and --require-alert-rules is set.",
            )
        )

    summary = _render_checks(checks)
    print(json.dumps(summary, indent=2, sort_keys=True))

    had_fail = any(check.status == "fail" for check in checks)
    had_warn = any(check.status == "warn" for check in checks)
    if strict and (had_fail or had_warn):
        return 2
    if had_fail:
        return 1
    if had_warn and require_alert_rules:
        return 3
    return 0


def _render_fail(checks: list[AuditCheck], message: str) -> int:
    checks.append(AuditCheck("project_lookup", "fail", message))
    print(json.dumps(_render_checks(checks), indent=2, sort_keys=True))
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Sentry project controls for audit workflows."
    )
    parser.add_argument("--org", default=None, help="Sentry organization slug")
    parser.add_argument("--project", default=None, help="Sentry project slug")
    parser.add_argument(
        "--base-url",
        default=SENTRY_API_BASE_DEFAULT,
        help="Sentry base URL",
    )
    parser.add_argument(
        "--require-alert-rules",
        action="store_true",
        help="Fail if no alert rules are configured.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as failures.",
    )

    parser.add_argument(
        "--token",
        default=None,
        help="Sentry auth token (or SENTRY_AUTH_TOKEN env var).",
    )

    args = parser.parse_args()

    token = args.token or os.getenv("SENTRY_AUTH_TOKEN")
    org = args.org or os.getenv("SENTRY_ORG")
    project = args.project or os.getenv("SENTRY_PROJECT")

    if not token or not org or not project:
        parser.error("SENTRY_AUTH_TOKEN, SENTRY_ORG, and SENTRY_PROJECT are required.")

    return run_audit(
        token=token,
        org=org,
        project=project,
        base_url=args.base_url.rstrip("/"),
        require_alert_rules=args.require_alert_rules,
        strict=args.strict,
    )


if __name__ == "__main__":
    sys.exit(main())
