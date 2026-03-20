from __future__ import annotations

from pathlib import Path

from ace_platform.symphony.pr_media import (
    LinearIssue,
    UploadedArtifact,
    build_linear_comment_body,
    build_pr_comment_body,
    discover_artifact_files,
    infer_issue_identifier,
)


def test_infer_issue_identifier_prefers_explicit_or_path_signals(tmp_path: Path) -> None:
    issue_path = tmp_path / "DAN-35@abcdef"
    issue_path.mkdir()

    assert (
        infer_issue_identifier(
            explicit=None,
            manifest_issue=None,
            branch_name="danmacideas/dan-35-e4-t2-implement-usage-metering",
            cwd=issue_path,
        )
        == "DAN-35"
    )
    assert (
        infer_issue_identifier(
            explicit="lin-12",
            manifest_issue=None,
            branch_name="feature/no-ticket-here",
            cwd=tmp_path,
        )
        == "LIN-12"
    )


def test_discover_artifact_files_appends_manifest_last(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "screen.png").write_text("png", encoding="utf-8")
    (artifact_dir / "manifest.json").write_text("{}", encoding="utf-8")

    files = discover_artifact_files(artifact_dir)

    assert [path.name for path in files] == ["screen.png", "manifest.json"]


def test_build_comment_bodies_include_linear_links_and_assets() -> None:
    issue = LinearIssue(
        id="issue-id",
        identifier="DAN-35",
        title="Implement usage metering",
        url="https://linear.app/danmac/issue/DAN-35/e4-t2-implement-usage-metering",
    )
    uploads = [
        UploadedArtifact(
            file_path="/tmp/usage.png",
            file_name="usage.png",
            content_type="image/png",
            size_bytes=2048,
            asset_url="https://uploads.linear.app/example/usage.png",
            attachment_id="attachment-id",
        ),
        UploadedArtifact(
            file_path="/tmp/manifest.json",
            file_name="manifest.json",
            content_type="application/json",
            size_bytes=1024,
            asset_url="https://uploads.linear.app/example/manifest.json",
            attachment_id="attachment-id-2",
        ),
    ]

    linear_comment = build_linear_comment_body(issue, uploads, summary="Validated /usage locally.")
    pr_comment = build_pr_comment_body(
        issue,
        uploads,
        summary="Validated /usage locally.",
        linear_comment_url=f"{issue.url}#comment-comment-id",
    )

    assert "Runtime validation artifacts" in linear_comment
    assert "![usage.png]" in linear_comment
    assert "[DAN-35 artifacts]" in pr_comment
    assert "Linear asset URLs require Linear authentication" in pr_comment
