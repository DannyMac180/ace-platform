from __future__ import annotations

import json
import textwrap

import httpx
import pytest

import ace_platform.cli as ace_cli
from ace_core.portability import (
    PortablePlaybook,
    PortablePlaybookBundle,
    bundle_from_json,
    bundle_to_json,
)


@pytest.fixture(autouse=True)
def disable_cli_analytics(monkeypatch) -> None:
    monkeypatch.setattr(ace_cli, "_emit_cli_analytics_event", lambda *_args, **_kwargs: None)


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


def test_init_command_emits_product_analytics(tmp_path, monkeypatch) -> None:
    project_dir = tmp_path / "telemetry-project"
    project_dir.mkdir()
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        ace_cli,
        "_emit_cli_analytics_event",
        lambda event_type, **kwargs: calls.append({"event_type": event_type, **kwargs}),
    )

    exit_code = ace_cli.main(["init", "--path", str(project_dir), "--default-profile", "hosted"])

    assert exit_code == 0
    assert calls == [
        {
            "event_type": "cli_init_completed",
            "project_root": project_dir.resolve(),
            "event_data": {
                "project_name": "telemetry-project",
                "default_profile": "hosted",
                "git_enabled": False,
                "agent_mode": False,
                "output_mode": "text",
            },
        }
    ]


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


def test_benchmark_command_emits_product_analytics_when_config_present(
    tmp_path,
    monkeypatch,
) -> None:
    project_dir = tmp_path / "benchmark-project"
    project_dir.mkdir()
    benchmark_dir = project_dir / "benchmarks"
    benchmark_dir.mkdir()
    benchmark_path = benchmark_dir / "suite.json"
    benchmark_path.write_text(
        json.dumps(
            {
                "id": "telemetry-benchmark",
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
    (project_dir / "ace.toml").write_text(
        textwrap.dedent(
            """
            [profiles.hosted]
            api_url = "https://ace.example"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        ace_cli,
        "_emit_cli_analytics_event",
        lambda event_type, **kwargs: calls.append({"event_type": event_type, **kwargs}),
    )

    exit_code = ace_cli.main(["benchmark", "--input", str(benchmark_path), "--format", "json"])

    assert exit_code == 0
    assert calls[0]["event_type"] == "cli_benchmark_completed"
    assert calls[0]["project_root"] == benchmark_path.resolve()
    assert calls[0]["event_data"]["benchmark_id"] == "telemetry-benchmark"
    assert calls[0]["event_data"]["ace_wins"] == 1


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


def test_doctor_command_reports_missing_config(tmp_path, capsys) -> None:
    exit_code = ace_cli.main(["doctor", "--path", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "ACE doctor report" in captured.out
    assert "[fail] Config file" in captured.out
    assert "ace init --path" in captured.out
    assert "ACE doctor failed" in captured.err


def test_doctor_command_accepts_generated_config(tmp_path, monkeypatch, capsys) -> None:
    project_dir = tmp_path / "starter-project"
    project_dir.mkdir()
    (project_dir / ".git").mkdir()
    ace_cli.main(["init", "--path", str(project_dir)])

    monkeypatch.setattr(ace_cli, "_command_available", lambda command: True)

    exit_code = ace_cli.main(["doctor", "--path", str(project_dir)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[ok] Python runtime" in captured.out
    assert "[ok] Config schema" in captured.out
    assert "[ok] local MCP command" in captured.out
    assert "ACE doctor found no blocking issues" in captured.out


def test_doctor_command_flags_unsupported_transport(tmp_path, capsys) -> None:
    project_dir = tmp_path / "unsupported-project"
    project_dir.mkdir()
    (project_dir / "ace.toml").write_text(
        textwrap.dedent(
            """
            schema_version = 1

            [project]
            root = "."
            git_enabled = false

            [bootstrap]
            default_profile = "local"

            [profiles.local]
            api_url = "http://localhost:8000"
            mcp_transport = "websocket"

            [profiles.hosted]
            api_url = "https://aceagent.io"
            mcp_transport = "http"
            mcp_url = "https://aceagent.io/mcp"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    exit_code = ace_cli.main(["doctor", "--path", str(project_dir)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "[fail] local MCP transport: `websocket` is not supported." in captured.out
    assert "Use one of: http, stdio." in captured.out


def test_doctor_command_flags_missing_local_command(tmp_path, monkeypatch, capsys) -> None:
    project_dir = tmp_path / "missing-command-project"
    project_dir.mkdir()
    (project_dir / "ace.toml").write_text(
        textwrap.dedent(
            """
            schema_version = 1

            [project]
            root = "."
            git_enabled = false

            [bootstrap]
            default_profile = "local"

            [profiles.local]
            api_url = "http://localhost:8000"
            mcp_transport = "stdio"
            mcp_command = "missing-python"
            mcp_args = ["-m", "ace_platform.mcp.server", "stdio"]

            [profiles.hosted]
            api_url = "https://aceagent.io"
            mcp_transport = "http"
            mcp_url = "https://aceagent.io/mcp"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ace_cli, "_command_available", lambda command: command != "missing-python")

    exit_code = ace_cli.main(["doctor", "--path", str(project_dir)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "[fail] local MCP command: `missing-python` was not found on PATH." in captured.out


def test_command_available_requires_executable_file_for_path(tmp_path) -> None:
    command_dir = tmp_path / "bin"
    command_dir.mkdir()
    assert ace_cli._command_available(str(command_dir)) is False

    command_file = tmp_path / "ace-mcp"
    command_file.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    assert ace_cli._command_available(str(command_file)) is False

    command_file.chmod(0o755)
    assert ace_cli._command_available(str(command_file)) is True


def test_init_command_agent_mode_emits_deterministic_json(tmp_path, capsys) -> None:
    project_dir = tmp_path / "agent-project"
    project_dir.mkdir()
    (project_dir / "docs").mkdir()

    exit_code = ace_cli.main(["init", "--path", str(project_dir), "--agent"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    config_text = (project_dir / "ace.toml").read_text(encoding="utf-8")

    assert exit_code == 0
    assert captured.err == ""
    assert payload["status"] == "ok"
    assert payload["mode"] == "agent"
    assert payload["deterministic"] is True
    assert payload["project_root"] == str(project_dir.resolve())
    assert payload["config_path"] == str((project_dir / "ace.toml").resolve())
    assert payload["recommended_next_commands"] == ["ace doctor", "ace seed", "ace benchmark"]
    assert payload["follow_up_commands"] == [
        {
            "available": True,
            "command": "ace doctor",
            "reason": None,
        },
        {
            "available": True,
            "command": "ace seed",
            "reason": None,
        },
        {
            "available": True,
            "command": "ace benchmark",
            "reason": None,
        },
    ]
    assert "generated_at" not in payload["config"]
    assert "generated_at" not in config_text
    assert payload["config"] == config_text


def test_init_command_json_error_is_machine_readable(tmp_path, capsys) -> None:
    project_dir = tmp_path / "existing-agent-project"
    project_dir.mkdir()
    config_path = project_dir / "ace.toml"
    config_path.write_text("existing = true\n", encoding="utf-8")

    exit_code = ace_cli.main(["init", "--path", str(project_dir), "--output", "json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 1
    assert captured.err == ""
    assert payload["status"] == "error"
    assert payload["mode"] == "standard"
    assert payload["deterministic"] is False
    assert payload["project_root"] == str(project_dir.resolve())
    assert payload["config_path"] == str(config_path.resolve())
    assert payload["error"]["code"] == "config_exists"
    assert "already exists" in payload["error"]["message"]
