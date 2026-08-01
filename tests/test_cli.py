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
    assert "4/11 ratified" in out  # progress figure over the whole project


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


def test_a_malformed_by_id_is_refused_before_the_view_opens(demo_project, capsys,
                                                            monkeypatch):
    """SR-0028: the identity a sitting signs under is settled before the full-screen
    view opens. A refusal must therefore reach the terminal, where it can be read
    and acted on, rather than arriving inside a curses window.
    """
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    opened = []
    monkeypatch.setattr("throughline_ratify.tui.run",
                        lambda *a, **k: opened.append(True))

    rc = cli.main(["-C", str(demo_project), "--by", "Ada", "--by-id", "ada@x.com"])
    assert rc == 2
    assert "tl-ratify:" in capsys.readouterr().err
    assert not opened, "the cockpit never opened"


def test_a_well_formed_by_id_reaches_the_sitting(demo_project, monkeypatch):
    """It is carried to the view, not decided there — and it is carried in its own
    right, never folded into the name."""
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    seen = {}
    monkeypatch.setattr("throughline_ratify.tui.run",
                        lambda session, ratifier, log=None, ratifier_id=None:
                            seen.update(by=ratifier, by_id=ratifier_id))

    rc = cli.main(["-C", str(demo_project), "--by", "Ada Lovelace",
                   "--by-id", "github:ada"])
    assert rc == 0
    assert seen == {"by": "Ada Lovelace", "by_id": "github:ada"}


def test_no_by_id_stays_none_all_the_way_through(demo_project, monkeypatch):
    """Never invented, derived or defaulted — an absent identifier stays absent."""
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    seen = {}
    monkeypatch.setattr("throughline_ratify.tui.run",
                        lambda session, ratifier, log=None, ratifier_id=None:
                            seen.update(by_id=ratifier_id))
    cli.main(["-C", str(demo_project), "--by", "Ada Lovelace"])
    assert seen == {"by_id": None}


def test_list_marks_a_stale_item_as_stale_not_as_ratify_ready(demo_project, capsys):
    """A stale row is ratifiable, so the readiness mark alone would hide the one thing
    that distinguishes it — a signature already given, over wording since changed
    (SR-0030). It also has to be in the default listing, not just under --all."""
    cli.main(["-C", str(demo_project), "--list"])
    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if "FR-0010" in ln)
    assert "stale" in line
    assert "ratify-ready" not in line
