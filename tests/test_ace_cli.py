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
