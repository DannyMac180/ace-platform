from __future__ import annotations

import ast
import importlib
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "packages" / "ace-core"
PACKAGE_SRC = PACKAGE_ROOT / "src"
ACE_CORE_SRC = PACKAGE_SRC / "ace_core"


def test_ace_core_package_layout_exists() -> None:
    assert PACKAGE_ROOT.joinpath("pyproject.toml").exists()
    assert PACKAGE_ROOT.joinpath("README.md").exists()
    assert ACE_CORE_SRC.joinpath("__init__.py").exists()


def test_ace_core_package_has_no_ace_platform_imports() -> None:
    disallowed_imports: list[str] = []

    for path in ACE_CORE_SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("ace_platform"):
                        disallowed_imports.append(f"{path}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith("ace_platform"):
                    disallowed_imports.append(f"{path}: from {module} import ...")

    assert not disallowed_imports, "\n".join(disallowed_imports)


def test_ace_core_public_api_imports_from_package_src() -> None:
    sys.path.insert(0, str(PACKAGE_SRC))
    try:
        for name in list(sys.modules):
            if name == "ace_core" or name.startswith("ace_core."):
                sys.modules.pop(name)

        module = importlib.import_module("ace_core")

        assert Path(module.__file__).resolve().is_relative_to(ACE_CORE_SRC)
        assert module.ACE
        assert module.Generator
        assert module.Reflector
        assert module.Curator
        assert module.BulletpointAnalyzer
    finally:
        sys.path = [entry for entry in sys.path if entry != str(PACKAGE_SRC)]


def test_ace_core_builds_and_installs_independently(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(dist_dir)],
        cwd=PACKAGE_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    wheels = sorted(dist_dir.glob("ace_core-*.whl"))
    assert wheels, "expected an ace-core wheel to be built"

    install_dir = tmp_path / "install"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--target",
            str(install_dir),
            str(wheels[-1]),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    smoke_test = (
        "import sys; "
        f"sys.path.insert(0, {str(install_dir)!r}); "
        "import ace_core; "
        "from ace_core.ace import ACE; "
        "assert ace_core.ACE is ACE; "
        "assert ace_core.BulletpointAnalyzer is not None"
    )
    subprocess.run(
        [sys.executable, "-c", smoke_test],
        check=True,
        capture_output=True,
        text=True,
    )
