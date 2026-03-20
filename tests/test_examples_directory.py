from __future__ import annotations

import shutil
from pathlib import Path

import ace_platform.cli as ace_cli

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PROJECT = REPO_ROOT / "examples" / "repo-maintainer-starter"
PLAYBOOK_PACK = REPO_ROOT / "examples" / "playbook-packs" / "repo-maintainer"


def test_examples_readme_documents_local_oss_demo_flow() -> None:
    readme = (REPO_ROOT / "examples" / "README.md").read_text(encoding="utf-8")

    assert "python -m ace_platform.cli seed --path examples/repo-maintainer-starter" in readme
    assert "python -m ace_platform.cli benchmark" in readme
    assert "playbook-packs/repo-maintainer/" in readme


def test_repo_maintainer_sample_project_can_seed_and_benchmark(tmp_path, capsys) -> None:
    project_dir = tmp_path / "repo-maintainer-starter"
    shutil.copytree(SAMPLE_PROJECT, project_dir)

    seed_exit = ace_cli.main(["seed", "--path", str(project_dir)])
    seed_stdout = capsys.readouterr().out

    assert seed_exit == 0
    assert (
        "Created: ace_project_context.md, ace_workflow_starter.md, ace_example_patterns.md"
        in seed_stdout
    )

    generated_dir = project_dir / ".ace" / "playbooks"
    context_playbook = (generated_dir / "ace_project_context.md").read_text(encoding="utf-8")
    workflow_playbook = (generated_dir / "ace_workflow_starter.md").read_text(encoding="utf-8")
    examples_playbook = (generated_dir / "ace_example_patterns.md").read_text(encoding="utf-8")

    assert "Start with `README.md`" in context_playbook
    assert "Use `docs/maintainer_workflow.md` and the rest of `docs/`" in context_playbook
    assert "Review `examples/cli_extension.md`" in examples_playbook
    assert (
        "Run pytest before proposing a release or merging a behavior change." in workflow_playbook
    )

    benchmark_exit = ace_cli.main(
        ["benchmark", "--input", str(project_dir / "benchmark" / "repo-maintainer-benchmark.json")]
    )
    benchmark_stdout = capsys.readouterr().out

    assert benchmark_exit == 0
    assert "Benchmark: repo-maintainer-starter" in benchmark_stdout
    assert "- Net passed cases: +2" in benchmark_stdout
    assert "- Head-to-head: 2 ACE wins, 0 baseline wins, 1 ties" in benchmark_stdout


def test_repo_maintainer_playbook_pack_contains_multiple_files() -> None:
    pack_files = sorted(path.name for path in PLAYBOOK_PACK.glob("*.md"))

    assert pack_files == ["release_handoff.md", "repo_maintainer_context.md"]
    for path in PLAYBOOK_PACK.glob("*.md"):
        assert path.read_text(encoding="utf-8").startswith("# ")
