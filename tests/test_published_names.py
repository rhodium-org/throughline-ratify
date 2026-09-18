# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0057: the cockpit stands on what throughline publishes, and on nothing else.

Read from this package's own source, so a reach-in is caught in the change that
writes it rather than in an installation after an upgrade (UR-0016).
"""
from __future__ import annotations

import ast
from pathlib import Path

import throughline
import throughline_ratify

SRC = Path(throughline_ratify.__file__).parent


def _imports():
    for path in sorted(SRC.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0].startswith("throughline"):
                for alias in node.names:
                    yield path.name, node.module, alias.name
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0].startswith("throughline"):
                        yield path.name, alias.name, None


def test_every_throughline_import_is_a_published_name():
    published = set(throughline.__all__)
    for file, module, name in _imports():
        assert module == "throughline", f"{file} imports from inside the Tool: {module}"
        assert name is not None and not name.startswith("_"), f"{file}: {name}"
        assert name in published, f"{file} imports {name}, which throughline does not publish"


def test_nothing_is_imported_from_the_old_composing_package():
    for file, module, _ in _imports():
        assert not module.startswith("throughline_compose"), f"{file} still imports {module}"
