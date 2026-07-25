# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from throughline_ratify import cli


def test_list_prints_pending(demo_project, capsys):
    rc = cli.main(["-C", str(demo_project), "--list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Ratifier Fixture" in out
    assert "FR-0001" in out
    assert "FR-0005" not in out  # ratified, hidden by default
    assert "pending ratification" in out


def test_list_all_includes_ratified(demo_project, capsys):
    cli.main(["-C", str(demo_project), "--list", "--all"])
    out = capsys.readouterr().out
    assert "FR-0005" in out
    # under --all the count includes ratified items, so it is not "pending"
    assert "item(s) shown" in out
    assert "pending ratification" not in out


def test_list_shows_progress(demo_project, capsys):
    cli.main(["-C", str(demo_project), "--list"])
    out = capsys.readouterr().out
    assert "4/9 ratified" in out  # progress figure over the whole project


def test_list_sort_roots(demo_project, capsys):
    cli.main(["-C", str(demo_project), "--list", "--all", "--sort", "roots"])
    out = capsys.readouterr().out
    assert "sort: roots" in out
    assert out.index("INT-0001") < out.index("FR-0001")


def test_list_rejects_bad_sort(demo_project, capsys):
    # argparse choices reject an unknown sort with exit code 2
    import pytest
    with pytest.raises(SystemExit):
        cli.main(["-C", str(demo_project), "--list", "--sort", "sideways"])


def test_no_project_returns_error(tmp_path, capsys):
    rc = cli.main(["-C", str(tmp_path), "--list"])
    assert rc == 2
    assert "not inside a throughline project" in capsys.readouterr().err


def test_non_tty_without_list_is_error(demo_project, capsys):
    # under capsys stdout is not a tty, so the TUI must refuse and advise --list
    rc = cli.main(["-C", str(demo_project)])
    assert rc == 2
    assert "not a terminal" in capsys.readouterr().err
