# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0039: the decisions the cockpit offers are importable without a terminal.

The claim is not that `core` happens to avoid curses today — it is that a caller
with no terminal at all can build the worklist and take every decision. The
browser editor is such a caller: under Pyodide there is no curses module and no
process to fork, so an import added anywhere on this path does not degrade, it
fails to load.

Nothing in this repository would notice that. `tui` imports curses at module
level and every other test runs in a process where curses imports fine, so a
`from . import tui` added to `core` for one shared helper would pass the whole
suite and break the only consumer that cannot recover.

So the assertion is made where it can fail: in a child process where importing
curses raises, and where the audit hook turns any attempt to start a process
into an error rather than a silent success.
"""
from __future__ import annotations

import ast
import subprocess
import sys
import textwrap
from pathlib import Path

from throughline_ratify import core

# Run in the child, before anything of ours is imported.
#
# Blocking the import rather than deleting `sys.modules['curses']`: a module
# already imported by the parent would otherwise be found again, and the point
# is to reproduce an environment where it cannot be had at all.
PROBE = textwrap.dedent(
    """
    import sys

    class NoTerminal:
        def find_module(self, name, path=None):
            return self.find_spec(name, path)

        def find_spec(self, name, path=None, target=None):
            if name == "curses" or name.startswith("curses."):
                raise ImportError("no terminal in this process (SR-0039)")
            return None

    sys.modules.pop("curses", None)
    sys.meta_path.insert(0, NoTerminal())

    # Anything that starts a process is a failure, not a fallback. Shelling out
    # to git for the ratifier's name is the one this catches in practice.
    def no_processes(event, args):
        if event in {"subprocess.Popen", "os.system", "os.exec", "os.spawn", "os.posix_spawn"}:
            raise AssertionError(f"started a process: {event} (SR-0039)")

    sys.addaudithook(no_processes)

    try:
        import curses
    except ImportError:
        pass
    else:
        raise AssertionError("curses imported in a process that should not have it")

    from pathlib import Path
    from throughline_ratify import core

    assert "curses" not in sys.modules

    root = Path(sys.argv[1])
    session = core.open_session(root)

    # The worklist and its counts.
    rows = core.build_queue(session)
    assert rows, "no worklist"
    done, gradable = core.ratification_progress(session)
    assert gradable >= len(rows)

    # Each decision, on the item the fixture puts it in reach of. Taken rather
    # than merely resolved: an attribute lookup would pass against a module that
    # could not actually write.
    core.ratify_item(session, "FR-0001", by="A Person", by_id="email:a@example.com")

    # The walk for an item that overshot ratification, and the refusal cascade.
    assert core.reratify_item(session, "FR-0007", by="A Person") is not None
    before = core.preview_reject(session, "FR-0002")
    refused = core.reject_item(session, "FR-0002", reason="not as written")
    assert isinstance(before, list) and isinstance(refused, list)

    print("OK", len(rows), done, gradable)
    """
)


def test_core_is_usable_with_no_curses_and_no_subprocess(demo_project):
    proc = subprocess.run(
        [sys.executable, "-c", PROBE, str(demo_project)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert proc.stdout.startswith("OK "), proc.stdout


def test_the_full_screen_view_is_the_only_thing_that_needs_a_terminal():
    """`tui` is one caller of `core`, not where the decisions live.

    Stated as a test because the direction of the dependency is the whole of
    SR-0039: `tui` may import `core`, and `core` may never import `tui`. Read
    from the syntax tree rather than by searching the text, so the prose that
    explains the arrangement does not count as breaking it.
    """
    tree = ast.parse(Path(core.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.update(
                f"{node.module}.{a.name}" if node.module else a.name for a in node.names
            )
            if node.module:
                imported.add(node.module)

    forbidden = {n for n in imported if n == "curses" or n.split(".")[-1] == "tui"}
    assert not forbidden, f"the decision module imports {sorted(forbidden)} (SR-0039)"
