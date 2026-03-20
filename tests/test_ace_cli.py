from __future__ import annotations

import json

import httpx

import ace_platform.cli as ace_cli
from ace_core.portability import (
    PortablePlaybook,
    PortablePlaybookBundle,
    bundle_from_json,
    bundle_to_json,
)


class _StubClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = responses
        self.calls: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        self.calls.append({"method": method, "url": url, **kwargs})
        return self._responses.pop(0)


def test_export_command_writes_bundle(tmp_path, monkeypatch, capsys) -> None:
    bundle = PortablePlaybookBundle(
        playbooks=[PortablePlaybook(name="CLI Export", versions=[], traces=[])]
    )
    response = httpx.Response(
        200,
        text=bundle_to_json(bundle),
        request=httpx.Request("GET", "https://ace.example/playbooks/export"),
    )
    client = _StubClient([response])
    monkeypatch.setattr(ace_cli.httpx, "Client", lambda timeout=30.0: client)

    output_path = tmp_path / "bundle.json"
    exit_code = ace_cli.main(
        [
            "export",
            "--api-url",
            "https://ace.example",
            "--token",
            "test-token",
            "--output",
            str(output_path),
        ]
    )

    stdout = capsys.readouterr().out
    assert exit_code == 0
    assert "Exported 1 playbooks" in stdout
    assert (
        bundle_from_json(output_path.read_text(encoding="utf-8")).playbooks[0].name == "CLI Export"
    )
    assert client.calls[0]["url"] == "https://ace.example/playbooks/export"


def test_import_command_posts_bundle(monkeypatch, tmp_path, capsys) -> None:
    bundle = PortablePlaybookBundle(
        playbooks=[PortablePlaybook(name="CLI Import", versions=[], traces=[])]
    )
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(bundle_to_json(bundle), encoding="utf-8")

    response = httpx.Response(
        201,
        json={"imported_count": 1, "imported_playbooks": []},
        request=httpx.Request("POST", "https://ace.example/playbooks/import"),
    )
    client = _StubClient([response])
    monkeypatch.setattr(ace_cli.httpx, "Client", lambda timeout=30.0: client)

    exit_code = ace_cli.main(
        [
            "import",
            "--api-url",
            "https://ace.example",
            "--token",
            "test-token",
            "--input",
            str(bundle_path),
        ]
    )

    stdout = capsys.readouterr().out
    assert exit_code == 0
    assert "Imported 1 playbooks" in stdout
    assert client.calls[0]["url"] == "https://ace.example/playbooks/import"
    assert client.calls[0]["json"] == json.loads(bundle_to_json(bundle))


def test_init_command_writes_default_config(tmp_path, capsys) -> None:
    project_dir = tmp_path / "starter-project"
    project_dir.mkdir()
    (project_dir / "docs").mkdir()
    (project_dir / "playbooks").mkdir()
    (project_dir / "README.md").write_text("# Starter Project\n", encoding="utf-8")

    exit_code = ace_cli.main(["init", "--path", str(project_dir)])

    stdout = capsys.readouterr().out
    config_path = project_dir / "ace.toml"
    config_text = config_path.read_text(encoding="utf-8")

    assert exit_code == 0
    assert "Initialized ACE in" in stdout
    assert "- Default profile: local" in stdout
    assert config_path.exists()
    assert 'name = "starter-project"' in config_text
    assert 'docs_dir = "docs"' in config_text
    assert 'playbooks_dir = "playbooks"' in config_text
    assert 'readme_path = "README.md"' in config_text
    assert 'default_profile = "local"' in config_text
    assert 'api_url_env = "ACE_API_URL"' in config_text
    assert 'mcp_args = ["-m", "ace_platform.mcp.server", "stdio"]' in config_text
    assert 'mcp_url = "https://aceagent.io/mcp"' in config_text


def test_init_command_refuses_to_overwrite_existing_config(tmp_path, capsys) -> None:
    project_dir = tmp_path / "existing-project"
    project_dir.mkdir()
    config_path = project_dir / "ace.toml"
    config_path.write_text("existing = true\n", encoding="utf-8")

    exit_code = ace_cli.main(["init", "--path", str(project_dir)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "already exists" in captured.err
    assert config_path.read_text(encoding="utf-8") == "existing = true\n"


def test_init_command_force_overwrites_with_custom_settings(tmp_path, capsys) -> None:
    project_dir = tmp_path / "custom-project"
    project_dir.mkdir()
    (project_dir / "ace.toml").write_text("old = true\n", encoding="utf-8")

    exit_code = ace_cli.main(
        [
            "init",
            "--path",
            str(project_dir),
            "--project-name",
            "ACE Sandbox",
            "--default-profile",
            "hosted",
            "--api-url",
            "https://staging.example",
            "--local-api-url",
            "http://127.0.0.1:9000",
            "--docs-url",
            "https://docs.example",
            "--force",
        ]
    )

    stdout = capsys.readouterr().out
    config_text = (project_dir / "ace.toml").read_text(encoding="utf-8")

    assert exit_code == 0
    assert "- Default profile: hosted" in stdout
    assert 'name = "ACE Sandbox"' in config_text
    assert 'default_profile = "hosted"' in config_text
    assert 'docs_url = "https://docs.example"' in config_text
    assert 'api_url = "http://127.0.0.1:9000"' in config_text
    assert 'mcp_url = "https://staging.example/mcp"' in config_text


def test_benchmark_command_compares_baseline_and_ace_outputs(tmp_path, capsys) -> None:
    benchmark_path = tmp_path / "benchmark.json"
    benchmark_path.write_text(
        json.dumps(
            {
                "id": "starter-benchmark",
                "metric": "exact_match",
                "cases": [
                    {
                        "id": "case-1",
                        "prompt": "first prompt",
                        "expected_output": "alpha",
                        "baseline_output": "wrong",
                        "ace_output": "alpha",
                    },
                    {
                        "id": "case-2",
                        "prompt": "second prompt",
                        "expected_output": "beta",
                        "baseline_output": "beta",
                        "ace_output": "beta",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = ace_cli.main(["benchmark", "--input", str(benchmark_path)])

    stdout = capsys.readouterr().out
    assert exit_code == 0
    assert "Benchmark: starter-benchmark" in stdout
    assert "ACE-assisted" in stdout
    assert "- Net passed cases: +1" in stdout
    assert "- Head-to-head: 1 ACE wins, 0 baseline wins, 1 ties" in stdout
    assert "- Improved cases: case-1" in stdout


def test_benchmark_command_can_emit_json_summary(tmp_path, capsys) -> None:
    benchmark_path = tmp_path / "benchmark.json"
    benchmark_path.write_text(
        json.dumps(
            {
                "id": "json-benchmark",
                "metric": "contains",
                "cases": [
                    {
                        "id": "case-1",
                        "prompt": "unused",
                        "expected_output": "portable",
                        "baseline_output": "baseline miss",
                        "ace_output": "portable local runtime",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = ace_cli.main(["benchmark", "--input", str(benchmark_path), "--format", "json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["benchmark_id"] == "json-benchmark"
    assert payload["comparison"]["net_passed_delta"] == 1
    assert payload["comparison"]["ace_wins"] == 1
    assert payload["cases"][0]["outcome"] == "ace_win"


def test_benchmark_command_rejects_missing_case_fields(tmp_path, capsys) -> None:
    benchmark_path = tmp_path / "broken-benchmark.json"
    benchmark_path.write_text(
        json.dumps(
            {
                "id": "broken-benchmark",
                "metric": "exact_match",
                "cases": [
                    {
                        "id": "case-1",
                        "prompt": "missing ace output",
                        "expected_output": "value",
                        "baseline_output": "value",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = ace_cli.main(["benchmark", "--input", str(benchmark_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "field 'ace_output' must be a string" in captured.err


def test_benchmark_command_reports_missing_input_file(capsys) -> None:
    missing_path = "/tmp/ace-benchmark-does-not-exist.json"

    exit_code = ace_cli.main(["benchmark", "--input", missing_path])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "ACE benchmark failed:" in captured.err
    assert missing_path in captured.err
