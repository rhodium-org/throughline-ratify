# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0074 — started in a directory that no longer exists, tl-ratify says so in one
line.

Found when a git worktree was removed under a shell that was sitting inside it.
The next ``tl-ratify -C .`` there ended in a traceback from the standard library,
which says nothing about what to do.
"""
from __future__ import annotations

import os

import pytest

from throughline_ratify import cli, core


@pytest.fixture
def nowhere(tmp_path, monkeypatch):
    """Run with the working directory removed from under the process."""
    gone = tmp_path / "gone"
    gone.mkdir()
    monkeypatch.chdir(gone)
    gone.rmdir()
    with pytest.raises(OSError):
        os.getcwd()          # the premise: there is no directory to resolve against
    return gone


@pytest.mark.parametrize("argv", [[], ["-C", "."], ["-C", "idd"], ["--list"],
                                  ["-C", ".", "--list"]])
def test_a_relative_path_fails_with_one_line_and_no_traceback(nowhere, capsys, argv):
    assert cli.main([*argv, "--by", "Ada Lovelace"]) == 2
    out, err = capsys.readouterr()
    lines = [ln for ln in err.splitlines() if ln.strip()]
    assert out == "" and len(lines) == 1
    assert lines[0].startswith("tl-ratify: cannot resolve the path ")
    assert "no longer exists" in lines[0]
    assert "Traceback" not in err


def test_the_line_names_the_path_given_and_says_what_to_do(nowhere, capsys):
    cli.main(["-C", "idd", "--list"])
    err = capsys.readouterr().err
    assert "'idd'" in err
    assert "Change to a directory that exists" in err
    assert "absolute path with -C" in err


def test_an_absolute_path_still_opens_from_there(nowhere, demo_project, capsys):
    """Nothing about the graph is wrong, so a path that does not depend on the
    missing directory is opened as usual."""
    assert cli.main(["-C", str(demo_project), "--list"]) == 0
    assert "FR-0001" in capsys.readouterr().out


def test_the_refusal_is_raised_where_the_path_is_resolved(nowhere):
    with pytest.raises(core.RatifierError, match="no longer exists"):
        core.resolve_root(".")
