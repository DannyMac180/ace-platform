from __future__ import annotations

import ace_platform.cli as ace_cli


def test_seed_command_creates_project_playbooks_from_repo_signals(tmp_path, capsys) -> None:
    project_dir = tmp_path / "seeded-project"
    project_dir.mkdir()
    (project_dir / ".git").mkdir()
    (project_dir / "tests").mkdir()
    (project_dir / "src").mkdir()
    (project_dir / "docs").mkdir()
    (project_dir / "examples").mkdir()
    (project_dir / "pyproject.toml").write_text(
        "[project]\nname = 'seeded-project'\n", encoding="utf-8"
    )
    (project_dir / "package.json").write_text(
        '{"scripts":{"test":"vitest","lint":"eslint .","build":"vite build"}}',
        encoding="utf-8",
    )
    (project_dir / "Makefile").write_text("lint:\n\t@echo lint\n", encoding="utf-8")
    (project_dir / "README.md").write_text(
        "# Seeded Project\n\nA demo repo.\n\n- Always run pytest before merging changes\n",
        encoding="utf-8",
    )
    (project_dir / "docs" / "workflow.md").write_text(
        "# Workflow\n\nUse service-layer modules for business logic.\n",
        encoding="utf-8",
    )
    (project_dir / "examples" / "README.md").write_text(
        "# Examples\n\nCheck this example before adding a new integration.\n",
        encoding="utf-8",
    )

    exit_code = ace_cli.main(["seed", "--path", str(project_dir)])

    stdout = capsys.readouterr().out
    playbooks_dir = project_dir / "playbooks"
    context_playbook = (playbooks_dir / "ace_project_context.md").read_text(encoding="utf-8")
    workflow_playbook = (playbooks_dir / "ace_workflow_starter.md").read_text(encoding="utf-8")
    examples_playbook = (playbooks_dir / "ace_example_patterns.md").read_text(encoding="utf-8")

    assert exit_code == 0
    assert "Seeded ACE starter playbooks in" in stdout
    assert (
        "Created: ace_project_context.md, ace_workflow_starter.md, ace_example_patterns.md"
        in stdout
    )
    assert "Start with `README.md`" in context_playbook
    assert "Use `docs/workflow.md` and the rest of `docs/`" in context_playbook
    assert "Primary stack detected: Python, JavaScript." in context_playbook
    assert "Use `npm run test`" in workflow_playbook
    assert "Run `make lint`" in workflow_playbook
    assert "Always run pytest before merging changes." in workflow_playbook
    assert "Use service-layer modules for business logic." in workflow_playbook
    assert "Review `examples/README.md`" in examples_playbook


def test_seed_command_respects_project_paths_from_ace_toml(tmp_path) -> None:
    project_dir = tmp_path / "custom-layout"
    project_dir.mkdir()
    (project_dir / "knowledge").mkdir()
    (project_dir / "samples").mkdir()
    (project_dir / "guides").mkdir()
    (project_dir / "guides" / "README-custom.md").write_text("# Custom\n", encoding="utf-8")
    (project_dir / "knowledge" / "guide.md").write_text(
        "# Guide\n\nAlways check the knowledge folder first.\n",
        encoding="utf-8",
    )
    (project_dir / "samples" / "README.md").write_text("# Samples\n", encoding="utf-8")
    (project_dir / "ace.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "Custom Layout"',
                'docs_dir = "knowledge"',
                'examples_dir = "samples"',
                'playbooks_dir = "guides"',
                'readme_path = "guides/README-custom.md"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = ace_cli.main(["seed", "--path", str(project_dir)])

    assert exit_code == 0
    generated = (project_dir / "guides" / "ace_project_context.md").read_text(encoding="utf-8")
    assert "# Custom Layout Project Context" in generated
    assert "Start with `guides/README-custom.md`" in generated
    assert "Use `knowledge/guide.md` and the rest of `knowledge/`" in generated
    assert "Check `samples/README.md` and other files under `samples/`" in generated


def test_seed_command_is_idempotent_without_force(tmp_path, capsys) -> None:
    project_dir = tmp_path / "idempotent-project"
    project_dir.mkdir()
    (project_dir / "README.md").write_text("# Idempotent\n", encoding="utf-8")

    first_exit = ace_cli.main(["seed", "--path", str(project_dir)])
    first_output = capsys.readouterr().out
    second_exit = ace_cli.main(["seed", "--path", str(project_dir)])
    second_output = capsys.readouterr().out

    assert first_exit == 0
    assert "Created: ace_project_context.md, ace_workflow_starter.md" in first_output
    assert second_exit == 0
    assert "Skipped existing: ace_project_context.md, ace_workflow_starter.md" in second_output


def test_seed_command_force_overwrites_existing_generated_playbooks(tmp_path) -> None:
    project_dir = tmp_path / "force-project"
    project_dir.mkdir()
    readme_path = project_dir / "README.md"
    readme_path.write_text("# Force Project\n", encoding="utf-8")

    first_exit = ace_cli.main(["seed", "--path", str(project_dir)])
    original = (project_dir / "playbooks" / "ace_workflow_starter.md").read_text(encoding="utf-8")

    readme_path.write_text(
        "# Force Project\n\nAlways validate release notes before shipping.\n",
        encoding="utf-8",
    )
    second_exit = ace_cli.main(["seed", "--path", str(project_dir), "--force"])
    updated = (project_dir / "playbooks" / "ace_workflow_starter.md").read_text(encoding="utf-8")

    assert first_exit == 0
    assert second_exit == 0
    assert "Always validate release notes before shipping." not in original
    assert "Always validate release notes before shipping." in updated
