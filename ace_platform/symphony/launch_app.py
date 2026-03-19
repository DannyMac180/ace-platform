"""Repo-owned runtime validation wrapper for Symphony app-touching tasks."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_FRONTEND_URL = "http://127.0.0.1:3000"
DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"
DEFAULT_FRONTEND_PORT = 3000
DEFAULT_BACKEND_PORT = 8000
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_SCREENSHOT_SIZE = "1440,1200"
DEFAULT_ARTIFACT_DIR = ".artifacts/launch-app"
DEFAULT_ROUTES = ["/"]


class LaunchAppError(RuntimeError):
    """Raised when runtime validation cannot complete."""


@dataclass(frozen=True)
class ServiceResult:
    name: str
    url: str
    started: bool
    ready: bool
    log_path: str | None
    pid: int | None


@dataclass(frozen=True)
class RouteArtifact:
    label: str
    url: str
    http_status: int | None
    content_type: str | None
    body_path: str | None
    screenshot_path: str | None
    screenshot_backend: str | None
    screenshot_error: str | None


def _iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def sanitize_label(value: str) -> str:
    label = value.strip().strip("/")
    if not label:
        return "root"
    pieces: list[str] = []
    for char in label:
        if char.isalnum():
            pieces.append(char.lower())
        else:
            pieces.append("-")
    compact = "".join(pieces).strip("-")
    while "--" in compact:
        compact = compact.replace("--", "-")
    return compact or "route"


def infer_extension(content_type: str | None) -> str:
    if not content_type:
        return ".txt"
    mime = content_type.split(";", 1)[0].strip().lower()
    if mime == "application/json":
        return ".json"
    if mime in {"text/html", "application/xhtml+xml"}:
        return ".html"
    guessed = mimetypes.guess_extension(mime)
    return guessed or ".txt"


def _urlopen(
    url: str, *, timeout: float, headers: dict[str, str] | None = None
) -> urllib.response.addinfourl:
    request = urllib.request.Request(url, headers=headers or {})
    return urllib.request.urlopen(request, timeout=timeout)


def wait_for_url(
    url: str,
    *,
    timeout_seconds: float,
    acceptable_statuses: set[int] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[bool, int | None]:
    deadline = time.monotonic() + timeout_seconds
    accepted = acceptable_statuses or {200}

    while time.monotonic() < deadline:
        try:
            with _urlopen(url, timeout=5.0, headers=headers) as response:
                if response.status in accepted:
                    return True, response.status
        except urllib.error.HTTPError as exc:
            if exc.code in accepted:
                return True, exc.code
        except urllib.error.URLError:
            pass
        time.sleep(1.0)

    return False, None


def _browser_candidates() -> list[str]:
    candidates = [
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "chrome",
        "msedge",
    ]
    found = [path for name in candidates if (path := shutil.which(name))]
    mac_paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    for path in mac_paths:
        if Path(path).exists():
            found.append(path)
    return found


def find_browser_executable() -> str | None:
    candidates = _browser_candidates()
    return candidates[0] if candidates else None


def capture_screenshot(
    url: str, destination: Path, *, window_size: str
) -> tuple[str | None, str | None]:
    browser = find_browser_executable()
    if browser is None:
        return None, "No headless Chrome/Chromium executable found on PATH."

    command = [
        browser,
        "--headless",
        "--disable-gpu",
        "--hide-scrollbars",
        f"--window-size={window_size}",
        f"--screenshot={destination}",
        "--virtual-time-budget=5000",
        url,
    ]

    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or exc.stdout or "").strip()
        return Path(
            browser
        ).name, stderr or f"Screenshot command failed with exit code {exc.returncode}."

    if destination.exists():
        return Path(browser).name, None
    stderr = (completed.stderr or completed.stdout or "").strip()
    return Path(browser).name, stderr or "Screenshot command succeeded but no file was written."


def kill_processes_on_port(port: int) -> None:
    try:
        completed = subprocess.run(
            ["/bin/bash", "-lc", f"lsof -ti :{port} | xargs kill -9 2>/dev/null || true"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return
    if completed.returncode not in {0, 123}:
        return


def launch_background_process(
    command: list[str], *, cwd: Path, log_path: Path
) -> subprocess.Popen[str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("w", encoding="utf-8")
    return subprocess.Popen(
        command,
        cwd=cwd,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
        env=os.environ.copy(),
    )


def default_backend_command() -> list[str]:
    return [
        sys.executable,
        "-m",
        "uvicorn",
        "ace_platform.api.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(DEFAULT_BACKEND_PORT),
    ]


def default_frontend_command() -> list[str]:
    return [
        "npm",
        "run",
        "dev",
        "--",
        "--host",
        "127.0.0.1",
        "--port",
        str(DEFAULT_FRONTEND_PORT),
    ]


def fetch_route_artifact(
    route: str,
    *,
    base_url: str,
    artifact_dir: Path,
    timeout_seconds: float,
    window_size: str,
    headers: dict[str, str] | None,
) -> RouteArtifact:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", route.lstrip("/"))
    label = sanitize_label(route)
    body_path: str | None = None
    screenshot_path: str | None = None
    screenshot_backend: str | None = None
    screenshot_error: str | None = None
    http_status: int | None = None
    content_type: str | None = None

    try:
        with _urlopen(url, timeout=timeout_seconds, headers=headers) as response:
            payload = response.read()
            http_status = response.status
            content_type = response.headers.get("Content-Type")
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        http_status = exc.code
        content_type = exc.headers.get("Content-Type")
    except urllib.error.URLError as exc:
        raise LaunchAppError(f"Failed to fetch {url}: {exc.reason}") from exc

    extension = infer_extension(content_type)
    body_file = artifact_dir / f"{label}{extension}"
    body_file.write_bytes(payload)
    body_path = str(body_file)

    screenshot_file = artifact_dir / f"{label}.png"
    screenshot_backend, screenshot_error = capture_screenshot(
        url,
        screenshot_file,
        window_size=window_size,
    )
    if screenshot_file.exists():
        screenshot_path = str(screenshot_file)

    return RouteArtifact(
        label=label,
        url=url,
        http_status=http_status,
        content_type=content_type,
        body_path=body_path,
        screenshot_path=screenshot_path,
        screenshot_backend=screenshot_backend,
        screenshot_error=screenshot_error,
    )


def parse_header_arguments(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        name, separator, rest = value.partition(":")
        if not separator:
            raise LaunchAppError(f"Header must use 'Name: value' format, got {value!r}.")
        parsed[name.strip()] = rest.strip()
    return parsed


def build_manifest(
    *,
    repo_root: Path,
    artifact_dir: Path,
    issue_identifier: str | None,
    frontend: ServiceResult | None,
    backend: ServiceResult | None,
    routes: list[RouteArtifact],
) -> dict[str, Any]:
    manifest = {
        "generated_at": _iso_now(),
        "repo_root": str(repo_root),
        "cwd": str(Path.cwd()),
        "artifact_dir": str(artifact_dir),
        "issue_identifier": issue_identifier,
        "git_branch": subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=False,
            cwd=repo_root,
        ).stdout.strip()
        or None,
        "frontend": asdict(frontend) if frontend else None,
        "backend": asdict(backend) if backend else None,
        "routes": [asdict(route) for route in routes],
    }
    return manifest


def _socket_is_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch the ACE app stack, capture runtime artifacts, and write a manifest.",
    )
    parser.add_argument("--artifact-dir", default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--issue", default=None, help="Optional Linear issue identifier.")
    parser.add_argument("--frontend-url", default=DEFAULT_FRONTEND_URL)
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--route", action="append", dest="routes", default=[])
    parser.add_argument("--header", action="append", default=[])
    parser.add_argument("--start-frontend", action="store_true")
    parser.add_argument("--start-backend", action="store_true")
    parser.add_argument("--frontend-cmd", default=None)
    parser.add_argument("--backend-cmd", default=None)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--window-size", default=DEFAULT_SCREENSHOT_SIZE)
    parser.add_argument("--keep-running", action="store_true")
    parser.add_argument("--replace-frontend", action="store_true")
    parser.add_argument("--replace-backend", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = _repo_root()
    artifact_dir = (repo_root / args.artifact_dir).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    headers = parse_header_arguments(args.header)

    frontend_process: subprocess.Popen[str] | None = None
    backend_process: subprocess.Popen[str] | None = None
    frontend_result: ServiceResult | None = None
    backend_result: ServiceResult | None = None

    try:
        if args.start_backend:
            if args.replace_backend:
                kill_processes_on_port(DEFAULT_BACKEND_PORT)
            backend_log = artifact_dir / "backend.log"
            backend_command = (
                ["/bin/bash", "-lc", args.backend_cmd]
                if args.backend_cmd
                else default_backend_command()
            )
            backend_cwd = repo_root if not args.backend_cmd else repo_root
            backend_process = launch_background_process(
                backend_command, cwd=backend_cwd, log_path=backend_log
            )

        backend_ready, _ = wait_for_url(
            urllib.parse.urljoin(args.backend_url.rstrip("/") + "/", "health"),
            timeout_seconds=args.timeout_seconds,
            acceptable_statuses={200},
            headers=headers,
        )
        backend_result = ServiceResult(
            name="backend",
            url=args.backend_url,
            started=backend_process is not None,
            ready=backend_ready,
            log_path=str(artifact_dir / "backend.log") if backend_process else None,
            pid=backend_process.pid if backend_process else None,
        )

        if args.start_frontend:
            if args.replace_frontend:
                kill_processes_on_port(DEFAULT_FRONTEND_PORT)
            frontend_log = artifact_dir / "frontend.log"
            frontend_command = (
                ["/bin/bash", "-lc", args.frontend_cmd]
                if args.frontend_cmd
                else default_frontend_command()
            )
            frontend_cwd = repo_root / "web" if not args.frontend_cmd else repo_root
            frontend_process = launch_background_process(
                frontend_command,
                cwd=frontend_cwd,
                log_path=frontend_log,
            )

        routes = args.routes or DEFAULT_ROUTES
        frontend_ready, _ = wait_for_url(
            args.frontend_url,
            timeout_seconds=args.timeout_seconds,
            acceptable_statuses={200, 301, 302, 401, 403},
            headers=headers,
        )
        frontend_result = ServiceResult(
            name="frontend",
            url=args.frontend_url,
            started=frontend_process is not None,
            ready=frontend_ready,
            log_path=str(artifact_dir / "frontend.log") if frontend_process else None,
            pid=frontend_process.pid if frontend_process else None,
        )

        if not frontend_ready:
            raise LaunchAppError(f"Frontend did not become reachable at {args.frontend_url}.")
        if args.start_backend and not backend_ready:
            raise LaunchAppError(f"Backend did not become reachable at {args.backend_url}/health.")

        route_artifacts = [
            fetch_route_artifact(
                route,
                base_url=args.frontend_url,
                artifact_dir=artifact_dir,
                timeout_seconds=min(args.timeout_seconds, 30.0),
                window_size=args.window_size,
                headers=headers,
            )
            for route in routes
        ]

        manifest = build_manifest(
            repo_root=repo_root,
            artifact_dir=artifact_dir,
            issue_identifier=args.issue,
            frontend=frontend_result,
            backend=backend_result,
            routes=route_artifacts,
        )
        manifest_path = artifact_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(json.dumps(manifest, indent=2))
        return 0
    except LaunchAppError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        if not args.keep_running:
            for process in (frontend_process, backend_process):
                if process is None:
                    continue
                process.terminate()
                try:
                    process.wait(timeout=10.0)
                except subprocess.TimeoutExpired:
                    process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
