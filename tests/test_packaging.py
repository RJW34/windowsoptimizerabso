"""Packaging correctness (gate G1, defects PKG-003 and PKG-004).

The baseline declared a package literally named ``src``, an entry point pointing at ``src.main``,
placeholder author/URL metadata, and a ``requirements.txt`` that disagreed with
``pyproject.toml`` -- listing a GUI toolkit, ``pywin32``, ``wmi`` and the test tools as runtime
requirements, none of which the code imported.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

# ``tomllib`` is stdlib from 3.11, but the package supports 3.10 (requires-python and the CI
# matrix both say so). Importing it unconditionally made this module fail to collect on 3.10,
# which aborts the whole run rather than failing one test.
if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - only the oldest supported interpreter takes this branch
    import tomli as tomllib

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def pyproject() -> dict:
    return tomllib.loads((REPO / "pyproject.toml").read_text())


def _requirement_names(text: str) -> set[str]:
    names = set()
    for raw in text.splitlines():
        line = raw.split("#")[0].strip()
        if not line or line.startswith("-"):
            continue
        names.add(re.split(r"[<>=!~\[]", line)[0].strip().lower())
    return names


def test_package_is_not_named_src(pyproject):
    """PKG-004: `src` is a directory convention, not a distributable package name."""
    find = pyproject["tool"]["setuptools"]["packages"]["find"]
    assert find["where"] == ["src"]
    assert find["include"] == ["windowsoptimizerabso*"]
    assert (REPO / "src" / "windowsoptimizerabso" / "__init__.py").exists()
    assert not (REPO / "src" / "__init__.py").exists()


def test_entry_point_resolves_to_a_real_callable(pyproject):
    target = pyproject["project"]["scripts"]["winopt"]
    module_path, _, attribute = target.partition(":")
    module = __import__(module_path, fromlist=[attribute])
    assert callable(getattr(module, attribute))


def test_metadata_has_no_placeholders(pyproject):
    """PKG-004: the baseline shipped "Your Name", "your@email.com" and "yourusername"."""
    blob = str(pyproject["project"]).lower()
    for placeholder in ["your name", "your@email.com", "yourusername", "example.com"]:
        assert placeholder not in blob, f"placeholder metadata: {placeholder}"


def test_version_matches_the_package(pyproject):
    from windowsoptimizerabso import __version__

    assert pyproject["project"]["version"] == __version__


def test_development_status_is_honest(pyproject):
    """PKG-005: "4 - Beta" for a tree that could not roll back a single change."""
    statuses = [c for c in pyproject["project"]["classifiers"] if c.startswith("Development Status")]
    assert statuses == ["Development Status :: 2 - Pre-Alpha"], statuses


def test_requirements_and_pyproject_agree(pyproject):
    """PKG-003: the two dependency lists disagreed in the baseline."""
    declared = {re.split(r"[<>=!~\[]", d)[0].strip().lower() for d in pyproject["project"]["dependencies"]}
    pinned = _requirement_names((REPO / "requirements.txt").read_text())
    assert declared == pinned, f"pyproject={sorted(declared)} requirements.txt={sorted(pinned)}"


def test_dev_requirements_and_pyproject_agree(pyproject):
    declared = {
        re.split(r"[<>=!~\[]", d)[0].strip().lower()
        for d in pyproject["project"]["optional-dependencies"]["dev"]
    }
    pinned = _requirement_names((REPO / "requirements-dev.txt").read_text())
    runtime = _requirement_names((REPO / "requirements.txt").read_text())
    assert declared == pinned - runtime, f"pyproject={sorted(declared)} requirements-dev={sorted(pinned)}"


def test_every_runtime_dependency_is_actually_imported(pyproject):
    """A dependency nobody imports is either dead weight or a missing import."""
    import ast

    package = REPO / "src" / "windowsoptimizerabso"
    imported: set[str] = set()
    for source_file in package.rglob("*.py"):
        if "legacy" in source_file.relative_to(package).parts:
            continue
        for node in ast.walk(ast.parse(source_file.read_text())):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.add(node.module.split(".")[0])

    declared = {re.split(r"[<>=!~\[]", d)[0].strip().lower() for d in pyproject["project"]["dependencies"]}
    unused = declared - {name.lower() for name in imported}
    assert unused == set(), f"declared but never imported: {sorted(unused)}"


def test_no_gui_dependencies_are_declared(pyproject):
    """PRD-005/PKG-006: the baseline shipped customtkinter, Pillow and ttkthemes for no GUI."""
    blob = " ".join(pyproject["project"]["dependencies"]).lower()
    for gui in ["customtkinter", "pillow", "ttkthemes", "tkinter"]:
        assert gui not in blob


def test_all_source_compiles():
    """Gate G1, and the regression test for the parse failure BASE-001 claimed."""
    import compileall

    assert compileall.compile_dir(str(REPO / "src"), quiet=2, force=True), "source failed to compile"


def test_governance_files_exist():
    """PKG-007: MIT was declared with no LICENSE, and CONTRIBUTING.md was referenced but absent."""
    for name in ["LICENSE", "SECURITY.md", "CONTRIBUTING.md", "CHANGELOG.md"]:
        assert (REPO / name).exists(), f"{name} is missing"
    assert "MIT" in (REPO / "LICENSE").read_text()


def test_readme_documents_only_commands_that_exist():
    """PKG-006: every command example in the baseline README was fabricated."""
    import re

    from typer.main import get_command

    from windowsoptimizerabso.cli.app import app

    implemented = set(get_command(app).commands)  # type: ignore[attr-defined]

    # Lines that explicitly document a command as absent are the point, not a violation.
    lines = [
        line
        for line in (REPO / "README.md").read_text().splitlines()
        if "Not implemented" not in line
    ]
    referenced = set(re.findall(r"`winopt ([a-z-]+)", "\n".join(lines)))
    missing = referenced - implemented
    assert missing == set(), f"README references commands that do not exist: {sorted(missing)}"


def test_changelog_names_the_current_version():
    assert "0.0.1a1" in (REPO / "CHANGELOG.md").read_text()
