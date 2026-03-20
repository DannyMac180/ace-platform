"""Local project scanning and starter playbook generation for `ace seed`."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ace_platform.core.content_converter import IMPERATIVE_VERBS, extract_candidates

CONFIG_FILENAME = "ace.toml"
TEXT_FILE_SUFFIXES = {".md", ".rst", ".txt", ".adoc"}
LOCKFILE_TO_MANAGER = {
    "package-lock.json": "npm",
    "pnpm-lock.yaml": "pnpm",
    "yarn.lock": "yarn",
    "bun.lockb": "bun",
}
COMMON_SCRIPT_NAMES = ("test", "lint", "format", "build", "dev", "start", "check")
COMMON_MAKE_TARGETS = ("test", "lint", "format", "build", "dev", "run", "check")
MAX_DOC_FILES = 4
MAX_EXAMPLE_DOCS = 4
MAX_EXAMPLE_REFS = 4
MAX_ACTIONABLE_BULLETS = 6
MAX_TOP_LEVEL_DIRS = 8
MAX_SOURCE_DIRS = 4
MAX_CONTEXT_DIRS = 3
MAX_FILE_CHARS = 12_000


@dataclass(frozen=True)
class SeedLayout:
    project_name: str
    docs_dir: str
    examples_dir: str
    playbooks_dir: str
    readme_path: str
    git_enabled: bool


@dataclass(frozen=True)
class ScannedFile:
    relative_path: str
    source_kind: str
    content: str


@dataclass(frozen=True)
class GeneratedPlaybook:
    filename: str
    content: str


@dataclass(frozen=True)
class ProjectScan:
    layout: SeedLayout
    scanned_files: tuple[ScannedFile, ...]
    source_dirs: tuple[str, ...]
    test_dirs: tuple[str, ...]
    top_level_dirs: tuple[str, ...]
    languages: tuple[str, ...]
    package_manager: str | None
    package_scripts: tuple[str, ...]
    make_targets: tuple[str, ...]
    example_refs: tuple[str, ...]
    has_ci_workflows: bool
    actionable_instructions: tuple[str, ...]


@dataclass(frozen=True)
class SeedResult:
    playbooks_dir: Path
    scanned_inputs: tuple[str, ...]
    created: tuple[str, ...]
    overwritten: tuple[str, ...]
    skipped: tuple[str, ...]


def seed_project_playbooks(project_root: Path, *, force: bool = False) -> SeedResult:
    """Generate starter playbooks for a local project."""
    project_root = project_root.expanduser().resolve()
    project_root.mkdir(parents=True, exist_ok=True)

    layout = load_seed_layout(project_root)
    scan = scan_project(project_root, layout)
    generated_playbooks = build_seed_playbooks(scan)

    playbooks_dir = project_root / layout.playbooks_dir
    playbooks_dir.mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    overwritten: list[str] = []
    skipped: list[str] = []

    for playbook in generated_playbooks:
        destination = playbooks_dir / playbook.filename
        existed = destination.exists()
        if existed and not force:
            skipped.append(playbook.filename)
            continue

        destination.write_text(playbook.content, encoding="utf-8")
        if existed:
            overwritten.append(playbook.filename)
        else:
            created.append(playbook.filename)

    return SeedResult(
        playbooks_dir=playbooks_dir,
        scanned_inputs=tuple(item.relative_path for item in scan.scanned_files),
        created=tuple(created),
        overwritten=tuple(overwritten),
        skipped=tuple(skipped),
    )


def load_seed_layout(project_root: Path) -> SeedLayout:
    """Load project layout for seeding from `ace.toml` when present."""
    config_values = _parse_project_config(project_root / CONFIG_FILENAME)

    project_name = config_values.get("name") or project_root.name or "ace-project"
    docs_dir = (
        config_values.get("docs_dir") or _first_existing_name(project_root, "docs", "doc") or "docs"
    )
    examples_dir = (
        config_values.get("examples_dir")
        or _first_existing_name(project_root, "examples", "example")
        or "examples"
    )
    playbooks_dir = (
        config_values.get("playbooks_dir")
        or _first_existing_name(project_root, "playbooks")
        or "playbooks"
    )
    readme_path = (
        config_values.get("readme_path")
        or _first_existing_name(project_root, "README.md", "README.rst", "README.txt")
        or "README.md"
    )

    return SeedLayout(
        project_name=project_name,
        docs_dir=docs_dir,
        examples_dir=examples_dir,
        playbooks_dir=playbooks_dir,
        readme_path=readme_path,
        git_enabled=(project_root / ".git").exists(),
    )


def scan_project(project_root: Path, layout: SeedLayout) -> ProjectScan:
    """Collect repo/docs/examples signals that inform starter playbooks."""
    scanned_files: list[ScannedFile] = []

    readme_file = _read_text_file(project_root, layout.readme_path, "readme")
    if readme_file:
        scanned_files.append(readme_file)

    docs_dir = project_root / layout.docs_dir
    scanned_files.extend(
        _collect_text_files(
            project_root,
            docs_dir,
            source_kind="docs",
            max_files=MAX_DOC_FILES,
            exclude_paths={layout.readme_path},
        )
    )

    examples_dir = project_root / layout.examples_dir
    scanned_files.extend(
        _collect_text_files(
            project_root,
            examples_dir,
            source_kind="examples",
            max_files=MAX_EXAMPLE_DOCS,
        )
    )

    top_level_dirs = tuple(_list_top_level_dirs(project_root))
    source_dirs = tuple(_detect_source_dirs(project_root, top_level_dirs))
    test_dirs = tuple(name for name in top_level_dirs if name in {"tests", "test", "spec"})
    package_manager = _detect_package_manager(project_root)
    package_scripts = tuple(_load_package_scripts(project_root))
    make_targets = tuple(_load_make_targets(project_root))
    example_refs = tuple(_collect_example_refs(project_root, examples_dir))
    languages = tuple(_detect_languages(project_root, top_level_dirs))
    actionable_instructions = tuple(_collect_actionable_instructions(scanned_files))

    return ProjectScan(
        layout=layout,
        scanned_files=tuple(scanned_files),
        source_dirs=source_dirs,
        test_dirs=test_dirs,
        top_level_dirs=top_level_dirs,
        languages=languages,
        package_manager=package_manager,
        package_scripts=package_scripts,
        make_targets=make_targets,
        example_refs=example_refs,
        has_ci_workflows=(project_root / ".github" / "workflows").exists(),
        actionable_instructions=actionable_instructions,
    )


def build_seed_playbooks(scan: ProjectScan) -> tuple[GeneratedPlaybook, ...]:
    """Build the deterministic starter playbook set for a project."""
    playbooks = [
        _build_project_context_playbook(scan),
        _build_workflow_playbook(scan),
    ]

    examples_playbook = _build_examples_playbook(scan)
    if examples_playbook is not None:
        playbooks.append(examples_playbook)

    return tuple(playbooks)


def format_seed_summary(result: SeedResult) -> str:
    """Render a user-facing summary for CLI output."""
    lines = [f"Seeded ACE starter playbooks in {result.playbooks_dir}"]
    if result.scanned_inputs:
        lines.append(f"- Scanned inputs: {', '.join(result.scanned_inputs)}")
    else:
        lines.append("- Scanned inputs: repository structure only (no README/docs/examples found)")
    if result.created:
        lines.append(f"- Created: {', '.join(result.created)}")
    if result.overwritten:
        lines.append(f"- Overwrote: {', '.join(result.overwritten)}")
    if result.skipped:
        lines.append(f"- Skipped existing: {', '.join(result.skipped)}")
    return "\n".join(lines)


def _build_project_context_playbook(scan: ProjectScan) -> GeneratedPlaybook:
    strategies: list[str] = []
    context: list[str] = []
    mistakes: list[str] = []

    if any(item.relative_path == scan.layout.readme_path for item in scan.scanned_files):
        strategies.append(
            f"Start with `{scan.layout.readme_path}` to understand "
            f"`{scan.layout.project_name}` goals, setup, and terminology before making changes."
        )

    docs_paths = [item.relative_path for item in scan.scanned_files if item.source_kind == "docs"]
    if docs_paths:
        strategies.append(
            f"Use `{docs_paths[0]}` and the rest of `{scan.layout.docs_dir}/` as the deeper "
            "reference set when the README is not enough."
        )

    if scan.example_refs:
        strategies.append(
            f"Check `{scan.example_refs[0]}` and other files under `{scan.layout.examples_dir}/` "
            "before creating a new workflow or integration pattern."
        )

    if scan.source_dirs and scan.test_dirs:
        strategies.append(
            f"Keep `{', '.join(scan.source_dirs[:2])}` and `{scan.test_dirs[0]}` aligned when "
            "behavior changes so implementation and validation move together."
        )

    if scan.languages:
        context.append(
            f"Primary stack detected: {', '.join(scan.languages)}. Treat those runtimes and "
            "toolchains as the default implementation surfaces for this repo."
        )

    focus_dirs = list(scan.source_dirs[:MAX_CONTEXT_DIRS])
    if scan.test_dirs:
        focus_dirs.extend(scan.test_dirs[:1])
    if docs_paths:
        focus_dirs.append(scan.layout.docs_dir)
    focus_dirs = _dedupe_preserve(focus_dirs)[:MAX_CONTEXT_DIRS]
    if focus_dirs:
        quoted = ", ".join(f"`{directory}/`" for directory in focus_dirs)
        context.append(
            f"Inspect {quoted} together when a task crosses implementation, validation, "
            "or documentation boundaries."
        )

    if scan.layout.git_enabled:
        mistakes.append(
            "Don't finalize changes without reviewing the tracked diff in the current git "
            "worktree, especially after generating or editing playbooks."
        )

    mistakes.append(
        "Don't rely on these starter playbooks alone when the repository changes materially; "
        "re-run `ace seed` or update the playbooks after large docs or workflow shifts."
    )

    content = _render_playbook(
        title=f"{scan.layout.project_name} Project Context",
        description=(
            "Generated by `ace seed` from repository structure, docs, and examples. "
            "Use this playbook as the first-pass map for how to navigate the project."
        ),
        sections=[
            ("STRATEGIES & INSIGHTS", strategies),
            ("CONTEXT CLUES & INDICATORS", context),
            ("COMMON MISTAKES TO AVOID", mistakes),
        ],
    )
    return GeneratedPlaybook(filename="ace_project_context.md", content=content)


def _build_workflow_playbook(scan: ProjectScan) -> GeneratedPlaybook:
    strategies: list[str] = []
    mistakes: list[str] = []

    for script_name in scan.package_scripts:
        manager = scan.package_manager or "npm"
        if script_name == "test":
            strategies.append(
                f"Use `{manager} run test` as the package-managed validation path when "
                "JavaScript or TypeScript surfaces change."
            )
        elif script_name == "lint":
            strategies.append(
                f"Run `{manager} run lint` before handoff when package-managed code or UI files change."
            )
        elif script_name == "format":
            strategies.append(
                f"Use `{manager} run format` to apply the repo's package-managed formatting rules."
            )
        elif script_name == "build":
            strategies.append(
                f"Run `{manager} run build` when changes affect bundled or shipped package-managed assets."
            )
        elif script_name in {"dev", "start"}:
            strategies.append(
                f"Use `{manager} run {script_name}` for local runtime verification when you need the project running."
            )
        else:
            strategies.append(
                f"Use `{manager} run {script_name}` when you need the repo-defined `{script_name}` workflow."
            )

    for target in scan.make_targets:
        if target == "test":
            strategies.append(
                "Use `make test` when the repository exposes a canonical test target."
            )
        elif target == "lint":
            strategies.append("Run `make lint` when you need the repo's top-level lint workflow.")
        elif target == "format":
            strategies.append(
                "Use `make format` when the Makefile owns formatting or code generation steps."
            )
        elif target == "build":
            strategies.append("Run `make build` before packaging or release-oriented validation.")
        elif target in {"dev", "run"}:
            strategies.append(
                f"Use `make {target}` for the top-level local runtime flow when available."
            )
        else:
            strategies.append(
                f"Use `make {target}` when you need the repo-defined `{target}` workflow."
            )

    if scan.test_dirs:
        strategies.append(
            f"Run the closest automated checks under `{scan.test_dirs[0]}/` before broader validation or handoff."
        )

    if scan.has_ci_workflows:
        strategies.append(
            "Mirror the validation expectations in `.github/workflows/` before finishing work so local "
            "proof stays close to CI behavior."
        )

    strategies.extend(scan.actionable_instructions)
    strategies = _dedupe_preserve(strategies)

    mistakes.append(
        "Don't bypass the closest local validation path for the files you changed before finalizing the playbook or code changes."
    )
    if scan.example_refs or any(item.source_kind == "docs" for item in scan.scanned_files):
        mistakes.append(
            "Don't ignore repository docs or examples when they define a workflow that overlaps the change you are making."
        )

    content = _render_playbook(
        title=f"{scan.layout.project_name} Workflow Starter",
        description=(
            "Generated by `ace seed` from repo commands and documented guidance. "
            "Use this playbook for repeatable local execution and validation habits."
        ),
        sections=[
            ("STRATEGIES & INSIGHTS", strategies),
            ("COMMON MISTAKES TO AVOID", mistakes),
        ],
    )
    return GeneratedPlaybook(filename="ace_workflow_starter.md", content=content)


def _build_examples_playbook(scan: ProjectScan) -> GeneratedPlaybook | None:
    if not scan.example_refs:
        return None

    strategies: list[str] = [
        f"Review `{path}` before implementing a similar flow so new work matches the repository's reference patterns."
        for path in scan.example_refs
    ]
    if scan.layout.examples_dir:
        strategies.append(
            f"Treat `{scan.layout.examples_dir}/` as the first place to look for usage patterns, wiring examples, or expected file layout."
        )

    content = _render_playbook(
        title=f"{scan.layout.project_name} Example Patterns",
        description=(
            "Generated by `ace seed` from example files discovered in the repository. "
            "Use it to shortcut pattern-matching before adding new implementations."
        ),
        sections=[("STRATEGIES & INSIGHTS", _dedupe_preserve(strategies))],
    )
    return GeneratedPlaybook(filename="ace_example_patterns.md", content=content)


def _render_playbook(
    *,
    title: str,
    description: str,
    sections: list[tuple[str, list[str]]],
) -> str:
    slug_state: set[str] = set()
    lines = [f"# {title}", "", description, ""]

    for heading, bullets in sections:
        filtered = _dedupe_preserve([bullet for bullet in bullets if bullet])
        if not filtered:
            continue
        lines.append(f"## {heading}")
        lines.append("")
        for bullet in filtered:
            slug = _slugify_unique(bullet, slug_state)
            lines.append(f"[{slug}] helpful=0 harmful=0 :: {bullet}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _parse_project_config(config_path: Path) -> dict[str, str]:
    if not config_path.exists():
        return {}

    values: dict[str, str] = {}
    current_section: str | None = None
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current_section = line.strip("[]")
            continue
        if current_section != "project":
            continue

        match = re.match(r'([A-Za-z0-9_]+)\s*=\s*"(.*)"$', line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def _read_text_file(project_root: Path, relative_path: str, source_kind: str) -> ScannedFile | None:
    path = project_root / relative_path
    if not path.exists() or not path.is_file():
        return None

    return ScannedFile(
        relative_path=relative_path,
        source_kind=source_kind,
        content=path.read_text(encoding="utf-8", errors="ignore")[:MAX_FILE_CHARS],
    )


def _collect_text_files(
    project_root: Path,
    base_dir: Path,
    *,
    source_kind: str,
    max_files: int,
    exclude_paths: set[str] | None = None,
) -> list[ScannedFile]:
    if not base_dir.exists() or not base_dir.is_dir():
        return []

    exclude_paths = exclude_paths or set()
    scanned_files: list[ScannedFile] = []
    for path in sorted(base_dir.rglob("*")):
        if len(scanned_files) >= max_files:
            break
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() not in TEXT_FILE_SUFFIXES and not path.name.lower().startswith(
            "readme."
        ):
            continue

        relative_path = path.relative_to(project_root).as_posix()
        if relative_path in exclude_paths:
            continue
        scanned_files.append(
            ScannedFile(
                relative_path=relative_path,
                source_kind=source_kind,
                content=path.read_text(encoding="utf-8", errors="ignore")[:MAX_FILE_CHARS],
            )
        )
    return scanned_files


def _collect_example_refs(project_root: Path, examples_dir: Path) -> list[str]:
    if not examples_dir.exists() or not examples_dir.is_dir():
        return []

    refs: list[str] = []
    for path in sorted(examples_dir.rglob("*")):
        if len(refs) >= MAX_EXAMPLE_REFS:
            break
        if not path.is_file() or path.name.startswith("."):
            continue
        refs.append(path.relative_to(project_root).as_posix())
    return refs


def _detect_package_manager(project_root: Path) -> str | None:
    for filename, manager in LOCKFILE_TO_MANAGER.items():
        if (project_root / filename).exists():
            return manager

    if (project_root / "package.json").exists():
        return "npm"
    return None


def _load_package_scripts(project_root: Path) -> list[str]:
    package_json = project_root / "package.json"
    if not package_json.exists():
        return []

    try:
        payload = json.loads(package_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    scripts = payload.get("scripts")
    if not isinstance(scripts, dict):
        return []

    ordered = [name for name in COMMON_SCRIPT_NAMES if name in scripts]
    extras = sorted(name for name in scripts if name not in ordered)[:2]
    return ordered + extras


def _load_make_targets(project_root: Path) -> list[str]:
    makefile = project_root / "Makefile"
    if not makefile.exists():
        return []

    targets: list[str] = []
    pattern = re.compile(r"^([A-Za-z0-9_.-]+):(?:\s|$)")
    for raw_line in makefile.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = pattern.match(raw_line)
        if not match:
            continue
        target = match.group(1)
        if target.startswith("."):
            continue
        targets.append(target)

    ordered = [name for name in COMMON_MAKE_TARGETS if name in targets]
    extras = sorted(name for name in targets if name not in ordered)[:2]
    return ordered + extras


def _list_top_level_dirs(project_root: Path) -> list[str]:
    top_level_dirs: list[str] = []
    for path in sorted(project_root.iterdir()):
        if len(top_level_dirs) >= MAX_TOP_LEVEL_DIRS:
            break
        if path.is_dir() and not path.name.startswith("."):
            top_level_dirs.append(path.name)
    return top_level_dirs


def _detect_source_dirs(project_root: Path, top_level_dirs: tuple[str, ...]) -> list[str]:
    source_dirs: list[str] = []
    for directory in top_level_dirs:
        path = project_root / directory
        if directory in {
            "docs",
            "doc",
            "examples",
            "example",
            "tests",
            "test",
            "playbooks",
            "venv",
        }:
            continue
        if (path / "__init__.py").exists():
            source_dirs.append(directory)
            continue
        if (
            any(path.glob("*.py"))
            or any(path.glob("*.ts"))
            or any(path.glob("*.tsx"))
            or any(path.glob("*.js"))
        ):
            source_dirs.append(directory)
    return source_dirs[:MAX_SOURCE_DIRS]


def _detect_languages(project_root: Path, top_level_dirs: tuple[str, ...]) -> list[str]:
    languages: list[str] = []
    if (project_root / "pyproject.toml").exists() or any(
        name.startswith("requirements") for name in _list_root_files(project_root)
    ):
        languages.append("Python")
    if (project_root / "tsconfig.json").exists() or any(
        name in {"tsconfig.app.json", "tsconfig.base.json"}
        for name in _list_root_files(project_root)
    ):
        languages.append("TypeScript")
    if (project_root / "package.json").exists() and "TypeScript" not in languages:
        languages.append("JavaScript")
    if (project_root / "go.mod").exists():
        languages.append("Go")
    if (project_root / "Cargo.toml").exists():
        languages.append("Rust")
    if (project_root / "pom.xml").exists() or (project_root / "build.gradle").exists():
        languages.append("Java")

    if not languages:
        for directory in top_level_dirs:
            path = project_root / directory
            if any(path.glob("*.py")):
                languages.append("Python")
            if any(path.glob("*.ts")) or any(path.glob("*.tsx")):
                languages.append("TypeScript")
            if any(path.glob("*.js")) or any(path.glob("*.jsx")):
                languages.append("JavaScript")
        languages = _dedupe_preserve(languages)
    return languages


def _list_root_files(project_root: Path) -> list[str]:
    return [path.name for path in project_root.iterdir() if path.is_file()]


def _collect_actionable_instructions(
    scanned_files: tuple[ScannedFile, ...] | list[ScannedFile],
) -> list[str]:
    instructions: list[str] = []
    seen: set[str] = set()

    for scanned_file in scanned_files:
        for candidate in extract_candidates(scanned_file.content):
            normalized = _normalize_instruction(candidate.content)
            if not _is_actionable_instruction(normalized):
                continue
            key = re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()
            if key in seen:
                continue
            seen.add(key)
            instructions.append(normalized)
            if len(instructions) >= MAX_ACTIONABLE_BULLETS:
                return instructions
    return instructions


def _normalize_instruction(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized.endswith((".", "!", "?")):
        normalized += "."
    return normalized


def _is_actionable_instruction(text: str) -> bool:
    lowered = text.lower().strip()
    if not lowered:
        return False

    actionable_prefixes = (
        "always ",
        "never ",
        "avoid ",
        "check ",
        "configure ",
        "ensure ",
        "follow ",
        "install ",
        "keep ",
        "look ",
        "prefer ",
        "read ",
        "review ",
        "run ",
        "set ",
        "start ",
        "stop ",
        "treat ",
        "update ",
        "use ",
        "verify ",
        "do not ",
        "don't ",
    )
    if lowered.startswith(actionable_prefixes):
        return True

    first_word = re.findall(r"[a-z0-9]+", lowered[:40])
    if first_word and first_word[0] in IMPERATIVE_VERBS:
        return True

    return " should " in lowered or " must " in lowered or lowered.startswith("if ")


def _slugify_unique(text: str, existing: set[str]) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    filtered = [
        word for word in words if word not in {"the", "a", "an", "and", "or", "to", "for", "of"}
    ]
    base = "-".join(filtered[:4]) or "instruction"
    candidate = base
    suffix = 2
    while candidate in existing:
        candidate = f"{base}-{suffix}"
        suffix += 1
    existing.add(candidate)
    return candidate


def _dedupe_preserve(items: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _first_existing_name(project_root: Path, *candidates: str) -> str | None:
    for candidate in candidates:
        if (project_root / candidate).exists():
            return candidate
    return None


__all__ = [
    "SeedResult",
    "build_seed_playbooks",
    "format_seed_summary",
    "load_seed_layout",
    "scan_project",
    "seed_project_playbooks",
]
