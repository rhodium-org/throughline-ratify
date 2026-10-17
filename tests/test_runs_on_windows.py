# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0076 — on Windows the package brings the curses it draws with.

CPython on Windows ships no ``curses`` module, so a cockpit that only lists
``throughline`` as a dependency installs cleanly there and then dies at the
first keypress. The distribution must declare ``windows-curses`` for that
platform and that platform only, say so where an installer reads, and keep the
no-terminal path free of curses so ``--list`` never needed it anywhere.
"""
from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PYPROJECT = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
DEPENDENCIES = PYPROJECT["project"]["dependencies"]


def _requirement(name: str) -> tuple[str, str]:
    """The dependency line for ``name`` as (specifier, marker); fails if absent."""
    for line in DEPENDENCIES:
        spec, _, marker = (part.strip() for part in line.partition(";"))
        if re.match(r"[A-Za-z0-9_.-]+", spec).group(0).lower() == name:
            return spec, marker
    raise AssertionError(f"{name} is not a declared dependency: {DEPENDENCIES}")


def test_the_distribution_brings_curses_on_windows():
    spec, marker = _requirement("windows-curses")
    assert "sys_platform" in marker and "win32" in marker, marker


def test_the_marker_leaves_every_other_platform_alone():
    _, marker = _requirement("windows-curses")
    # One condition, on the platform alone: a marker that also tests a Python
    # version or an implementation would leave some Windows installs without it.
    assert marker.replace('"', "'") == "sys_platform == 'win32'", marker


def test_the_tool_itself_carries_no_platform_marker():
    _, marker = _requirement("throughline")
    assert marker == "", marker


def test_windows_is_a_declared_operating_system():
    classifiers = PYPROJECT["project"]["classifiers"]
    assert "Operating System :: Microsoft :: Windows" in classifiers
    # The two that were already there stay: adding a platform is not a swap.
    assert "Operating System :: POSIX" in classifiers
    assert "Operating System :: MacOS" in classifiers


def test_the_readme_tells_a_windows_installer_nothing_extra_is_needed():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    install = readme[readme.index("## Install"):readme.index("## Use")]
    assert "Windows" in install and "windows-curses" in install


def test_the_curses_import_waits_for_the_cockpit():
    """``--list`` and ``--version`` must work where curses is absent, so the
    command module imports the screen only inside the function that opens it."""
    tree = ast.parse((REPO / "src/throughline_ratify/cli.py").read_text(encoding="utf-8"))
    at_module_level = {
        alias.name
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "curses" not in at_module_level
    assert "tui" not in at_module_level
