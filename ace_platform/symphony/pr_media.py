"""Upload runtime artifacts to Linear and link them from a GitHub PR comment."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_LINEAR_ENDPOINT = "https://api.linear.app/graphql"
DEFAULT_REPO = "DannyMac180/ace-platform"
DEFAULT_ARTIFACT_DIR = ".artifacts/launch-app"
ISSUE_IDENTIFIER_PATTERN = re.compile(r"\b([A-Z]{2,10}-\d+)\b")
LEADING_IDENTIFIER_PATTERN = re.compile(r"(?i)(?:^|[/_])([a-z]{2,10}-\d+)(?:[@/_-]|$)")
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

ISSUE_QUERY = """
query RuntimeMediaIssue($id: String!) {
  issue(id: $id) {
    id
    identifier
    title
    url
  }
}
"""

FILE_UPLOAD_MUTATION = """
mutation RuntimeMediaUpload($contentType: String!, $filename: String!, $size: Int!) {
  fileUpload(contentType: $contentType, filename: $filename, size: $size) {
    success
    uploadFile {
      uploadUrl
      assetUrl
      headers {
        key
        value
      }
    }
  }
}
"""

ATTACHMENT_CREATE_MUTATION = """
mutation RuntimeMediaAttachment(
  $issueId: String!,
  $title: String!,
  $subtitle: String,
  $url: String!,
  $metadata: JSONObject
) {
  attachmentCreate(
    input: {
      issueId: $issueId,
      title: $title,
      subtitle: $subtitle,
      url: $url,
      metadata: $metadata
    }
  ) {
    success
    attachment {
      id
      title
      url
    }
  }
}
"""

COMMENT_CREATE_MUTATION = """
mutation RuntimeMediaComment($issueId: String!, $body: String!) {
  commentCreate(input: { issueId: $issueId, body: $body }) {
    success
    comment {
      id
    }
  }
}
"""


class PRMediaError(RuntimeError):
    """Raised when PR media publishing fails."""


@dataclass(frozen=True)
class LinearIssue:
    id: str
    identifier: str
    title: str
    url: str


@dataclass(frozen=True)
class UploadedArtifact:
    file_path: str
    file_name: str
    content_type: str
    size_bytes: int
    asset_url: str
    attachment_id: str | None


def linear_graphql_request(
    token: str,
    query: str,
    *,
    variables: dict[str, Any] | None = None,
    endpoint: str = DEFAULT_LINEAR_ENDPOINT,
) -> dict[str, Any]:
    payload = {
        "query": query,
        "variables": variables or {},
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": token,
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30.0) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise PRMediaError(
            f"Linear GraphQL request failed with HTTP {exc.code}: {detail or 'no response body'}"
        ) from exc
    except urllib.error.URLError as exc:
        raise PRMediaError(f"Linear GraphQL request failed: {exc.reason}") from exc

    errors = body.get("errors")
    if isinstance(errors, list) and errors:
        messages = [
            error.get("message", "unknown GraphQL error")
            for error in errors
            if isinstance(error, dict)
        ]
        raise PRMediaError("; ".join(messages or ["Linear GraphQL request failed"]))

    data = body.get("data")
    if not isinstance(data, dict):
        raise PRMediaError("Linear GraphQL request returned an unexpected payload.")
    return data


def infer_issue_identifier(
    *,
    explicit: str | None = None,
    manifest_issue: str | None = None,
    branch_name: str | None = None,
    cwd: Path | None = None,
) -> str | None:
    for candidate in [explicit, manifest_issue]:
        if candidate:
            match = ISSUE_IDENTIFIER_PATTERN.search(candidate.upper())
            if match:
                return match.group(1).upper()

    if cwd:
        for part in reversed(cwd.parts):
            match = ISSUE_IDENTIFIER_PATTERN.search(part.upper())
            if match:
                return match.group(1).upper()

    if branch_name:
        match = LEADING_IDENTIFIER_PATTERN.search(branch_name)
        if match:
            return match.group(1).upper()

    return None


def guess_content_type(path: Path) -> str:
    content_type, _ = mimetypes.guess_type(path.name)
    return content_type or "application/octet-stream"


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise PRMediaError(f"Manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def discover_artifact_files(artifact_dir: Path) -> list[Path]:
    manifest_path = artifact_dir / "manifest.json"
    candidates = [
        path
        for path in sorted(artifact_dir.rglob("*"))
        if path.is_file() and path.name != manifest_path.name
    ]
    if manifest_path.exists():
        candidates.append(manifest_path)
    return candidates


def lookup_linear_issue(identifier: str, *, token: str, endpoint: str) -> LinearIssue:
    data = linear_graphql_request(
        token,
        ISSUE_QUERY,
        variables={"id": identifier},
        endpoint=endpoint,
    )
    issue = data.get("issue")
    if not isinstance(issue, dict):
        raise PRMediaError(f"Linear issue {identifier} was not found.")
    return LinearIssue(
        id=str(issue["id"]),
        identifier=str(issue["identifier"]),
        title=str(issue["title"]),
        url=str(issue["url"]),
    )


def request_upload_url(
    *,
    token: str,
    filename: str,
    content_type: str,
    size_bytes: int,
    endpoint: str,
) -> tuple[str, str, list[dict[str, str]]]:
    data = linear_graphql_request(
        token,
        FILE_UPLOAD_MUTATION,
        variables={
            "contentType": content_type,
            "filename": filename,
            "size": size_bytes,
        },
        endpoint=endpoint,
    )
    payload = data.get("fileUpload")
    if not isinstance(payload, dict) or not payload.get("success"):
        raise PRMediaError(f"Linear did not accept file upload request for {filename}.")
    upload_file = payload.get("uploadFile")
    if not isinstance(upload_file, dict):
        raise PRMediaError(f"Linear did not return upload metadata for {filename}.")
    headers = upload_file.get("headers")
    if not isinstance(headers, list):
        headers = []
    return str(upload_file["uploadUrl"]), str(upload_file["assetUrl"]), headers


def upload_file_bytes(
    path: Path,
    *,
    upload_url: str,
    content_type: str,
    header_items: list[dict[str, str]],
) -> None:
    data = path.read_bytes()
    headers = {
        "Content-Type": content_type,
        "Cache-Control": "public, max-age=31536000",
    }
    for item in header_items:
        key = item.get("key")
        value = item.get("value")
        if isinstance(key, str) and isinstance(value, str):
            headers[key] = value

    request = urllib.request.Request(
        upload_url,
        data=data,
        method="PUT",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=60.0):
            return
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise PRMediaError(
            f"Linear asset upload failed for {path.name} with HTTP {exc.code}: {detail or 'no response body'}"
        ) from exc
    except urllib.error.URLError as exc:
        raise PRMediaError(f"Linear asset upload failed for {path.name}: {exc.reason}") from exc


def create_attachment(
    *,
    token: str,
    issue_id: str,
    title: str,
    subtitle: str,
    asset_url: str,
    metadata: dict[str, Any],
    endpoint: str,
) -> str | None:
    data = linear_graphql_request(
        token,
        ATTACHMENT_CREATE_MUTATION,
        variables={
            "issueId": issue_id,
            "title": title,
            "subtitle": subtitle,
            "url": asset_url,
            "metadata": metadata,
        },
        endpoint=endpoint,
    )
    payload = data.get("attachmentCreate")
    if not isinstance(payload, dict) or not payload.get("success"):
        return None
    attachment = payload.get("attachment")
    if not isinstance(attachment, dict):
        return None
    return str(attachment.get("id")) if attachment.get("id") else None


def create_linear_comment(
    *,
    token: str,
    issue_id: str,
    body: str,
    endpoint: str,
) -> str | None:
    data = linear_graphql_request(
        token,
        COMMENT_CREATE_MUTATION,
        variables={"issueId": issue_id, "body": body},
        endpoint=endpoint,
    )
    payload = data.get("commentCreate")
    if not isinstance(payload, dict) or not payload.get("success"):
        return None
    comment = payload.get("comment")
    if not isinstance(comment, dict):
        return None
    comment_id = comment.get("id")
    return str(comment_id) if comment_id else None


def human_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def build_linear_comment_body(
    issue: LinearIssue,
    uploads: list[UploadedArtifact],
    *,
    summary: str | None,
) -> str:
    lines = [
        "## Runtime validation artifacts",
        "",
    ]
    if summary:
        lines.extend([summary, ""])
    lines.extend(
        [
            f"Uploaded by `github-pr-media` for `{issue.identifier}`.",
            "",
            "### Files",
        ]
    )
    for upload in uploads:
        lines.append(
            f"- [{upload.file_name}]({upload.asset_url}) ({upload.content_type}, {human_size(upload.size_bytes)})"
        )

    previews = [upload for upload in uploads if upload.content_type.startswith("image/")][:3]
    if previews:
        lines.extend(["", "### Previews"])
        for preview in previews:
            lines.append(f"![{preview.file_name}]({preview.asset_url})")

    return "\n".join(lines)


def build_pr_comment_body(
    issue: LinearIssue,
    uploads: list[UploadedArtifact],
    *,
    summary: str | None,
    linear_comment_url: str | None,
) -> str:
    lines = [
        "## Runtime Validation Artifacts",
        "",
    ]
    if summary:
        lines.extend([summary, ""])
    lines.extend(
        [
            f"- Linear issue: [{issue.identifier}]({issue.url})",
            f"- Linear media comment: [{issue.identifier} artifacts]({linear_comment_url or issue.url})",
            "- Note: Linear asset URLs require Linear authentication outside the app.",
            "",
            "### Uploaded files",
        ]
    )
    for upload in uploads:
        lines.append(
            f"- [{upload.file_name}]({upload.asset_url}) ({upload.content_type}, {human_size(upload.size_bytes)})"
        )
    return "\n".join(lines)


def post_pr_comment(*, repo: str, pr_number: str, body: str) -> None:
    command = [
        "gh",
        "api",
        f"repos/{repo}/issues/{pr_number}/comments",
        "-f",
        f"body={body}",
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise PRMediaError(detail or "Failed to post GitHub PR comment.") from exc


def infer_pr_number(*, explicit: str | None, repo: str) -> str:
    if explicit:
        return explicit
    command = ["gh", "pr", "view", "--repo", repo, "--json", "number", "-q", ".number"]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise PRMediaError(detail or "Unable to infer PR number with gh.") from exc
    value = completed.stdout.strip()
    if not value:
        raise PRMediaError("Unable to infer PR number from current branch.")
    return value


def current_branch() -> str | None:
    completed = subprocess.run(
        ["git", "branch", "--show-current"],
        check=False,
        capture_output=True,
        text=True,
    )
    branch = completed.stdout.strip()
    return branch or None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload runtime artifacts to the associated Linear issue and link them from a PR comment.",
    )
    parser.add_argument("--artifact-dir", default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--issue", default=None)
    parser.add_argument("--pr", default=None)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--summary", default=None)
    parser.add_argument("--linear-endpoint", default=DEFAULT_LINEAR_ENDPOINT)
    parser.add_argument("--max-upload-bytes", type=int, default=MAX_UPLOAD_BYTES)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    token = os.environ.get("LINEAR_API_KEY")
    if not token:
        print("LINEAR_API_KEY is not set in the current shell.", file=sys.stderr)
        return 1

    repo_root = Path(__file__).resolve().parents[2]
    artifact_dir = (repo_root / args.artifact_dir).resolve()
    manifest_path = (
        (repo_root / args.manifest).resolve() if args.manifest else artifact_dir / "manifest.json"
    )
    manifest = load_manifest(manifest_path)

    issue_identifier = infer_issue_identifier(
        explicit=args.issue,
        manifest_issue=manifest.get("issue_identifier") if isinstance(manifest, dict) else None,
        branch_name=current_branch(),
        cwd=Path.cwd(),
    )
    if not issue_identifier:
        print(
            "Could not infer a Linear issue identifier. Pass --issue DAN-35 explicitly.",
            file=sys.stderr,
        )
        return 1

    issue = lookup_linear_issue(issue_identifier, token=token, endpoint=args.linear_endpoint)
    files = discover_artifact_files(artifact_dir)
    uploads: list[UploadedArtifact] = []
    skipped: list[str] = []

    for file_path in files:
        size_bytes = file_path.stat().st_size
        if size_bytes > args.max_upload_bytes:
            skipped.append(f"{file_path.name} ({human_size(size_bytes)} exceeds upload cap)")
            continue
        content_type = guess_content_type(file_path)
        upload_url, asset_url, header_items = request_upload_url(
            token=token,
            filename=file_path.name,
            content_type=content_type,
            size_bytes=size_bytes,
            endpoint=args.linear_endpoint,
        )
        upload_file_bytes(
            file_path,
            upload_url=upload_url,
            content_type=content_type,
            header_items=header_items,
        )
        attachment_id = create_attachment(
            token=token,
            issue_id=issue.id,
            title=file_path.name,
            subtitle=f"Runtime validation artifact • {content_type} • {human_size(size_bytes)}",
            asset_url=asset_url,
            metadata={
                "title": "Runtime validation artifact",
                "attributes": [
                    {"name": "Content-Type", "value": content_type},
                    {"name": "Size", "value": human_size(size_bytes)},
                    {"name": "Path", "value": str(file_path.relative_to(repo_root))},
                ],
            },
            endpoint=args.linear_endpoint,
        )
        uploads.append(
            UploadedArtifact(
                file_path=str(file_path),
                file_name=file_path.name,
                content_type=content_type,
                size_bytes=size_bytes,
                asset_url=asset_url,
                attachment_id=attachment_id,
            )
        )

    if not uploads:
        print("No artifacts were uploaded to Linear.", file=sys.stderr)
        return 1

    summary = args.summary
    if skipped:
        skipped_note = "Skipped: " + ", ".join(skipped)
        summary = f"{summary}\n\n{skipped_note}" if summary else skipped_note

    linear_body = build_linear_comment_body(issue, uploads, summary=summary)
    linear_comment_id = create_linear_comment(
        token=token,
        issue_id=issue.id,
        body=linear_body,
        endpoint=args.linear_endpoint,
    )
    linear_comment_url = (
        f"{issue.url}#comment-{linear_comment_id}" if linear_comment_id else issue.url
    )

    pr_number = infer_pr_number(explicit=args.pr, repo=args.repo)
    pr_body = build_pr_comment_body(
        issue,
        uploads,
        summary=summary,
        linear_comment_url=linear_comment_url,
    )
    post_pr_comment(repo=args.repo, pr_number=pr_number, body=pr_body)

    print(
        json.dumps(
            {
                "issue": {
                    "identifier": issue.identifier,
                    "url": issue.url,
                },
                "linear_comment_url": linear_comment_url,
                "pr_number": pr_number,
                "uploaded_files": [upload.file_name for upload in uploads],
                "skipped_files": skipped,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
