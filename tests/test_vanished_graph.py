# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0067 — a graph that vanishes under an open cockpit ends the sitting with one
line, not a traceback.

Found when a git worktree was removed while a cockpit was open on its graph. The
idle reload asked for the graph again, nothing caught the refusal, and the
reviewer was shown a Python traceback. The reload also resolved the path afresh,
so a removed graph that sat inside another was replaced on screen by the
enclosing one.

These tests run the program on a scripted terminal, take the graph away behind
the open cockpit and let the interval pass.
"""
from __future__ import annotations

import shutil

import pytest

from conftest import _named_project
from throughline_ratify import cli, core, report, tui

IDLE = -1   # what getch returns when the interval passes with no key


class Terminal:
    """Enough of a curses window to run the key loops. A key may be a callable,
    run when the screen asks for it and then passed over, so the tree can change
    while the cockpit is up."""

    def __init__(self, keys):
        self.keys = list(keys)

    def getmaxyx(self):
        return 24, 120

    def getch(self):
        while callable(self.keys[0]):
            self.keys.pop(0)()
        return self.keys.pop(0)

    def addstr(self, *a):
        pass

    def erase(self):
        pass

    def keypad(self, on):
        pass

    def timeout(self, ms):
        pass

    def noutrefresh(self):
        pass


@pytest.fixture
def run(monkeypatch, capsys):
    """Run tl-ratify on a terminal that sends ``keys``. Returns the exit status,
    what reached standard error, and the graphs the cockpit showed."""
    shown = []

    class Cockpit(tui.App):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            # On an item that can be signed, so ``r`` takes a decision.
            self.sel = next((i for i, r in enumerate(self.rows) if r.ratifiable_now), 0)

        def draw(self):
            shown.append(self.session.project_name)

        def _confirm(self, question, detail=None):
            return True

    def _run(path, keys, *argv):
        terminal = Terminal(keys)
        monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True, raising=False)
        monkeypatch.setattr(tui, "App", Cockpit)
        monkeypatch.setattr(tui, "_init_colours", lambda: None)
        monkeypatch.setattr(tui, "_attr", lambda name, bold=False: 0)
        monkeypatch.setattr(tui, "_draw_opening", lambda scr, candidate: None)
        monkeypatch.setattr(tui.curses, "curs_set", lambda n: None)
        monkeypatch.setattr(tui.curses, "doupdate", lambda: None)
        monkeypatch.setattr(tui.curses, "wrapper", lambda fn, *a: fn(terminal, *a))
        rc = cli.main(["-C", str(path), "--by", "Ada Lovelace", *argv])
        return rc, capsys.readouterr().err, shown

    return _run


def _one_line(err: str) -> str:
    lines = [ln for ln in err.splitlines() if ln.strip()]
    assert len(lines) == 1, f"expected one line on standard error, got:\n{err}"
    return lines[0]


def test_a_graph_removed_under_an_idle_cockpit_ends_with_one_line(run, demo_project):
    rc, err, _ = run(demo_project, [lambda: shutil.rmtree(demo_project), IDLE])
    assert rc != 0
    assert _one_line(err) == f"tl-ratify: {demo_project}: the graph no longer exists"
    assert "Traceback" not in err


def test_decisions_already_taken_are_still_reported(run, demo_project, tmp_path):
    dest = tmp_path / "summary.txt"
    rc, err, _ = run(demo_project,
                     [ord("r"), lambda: shutil.rmtree(demo_project), IDLE],
                     "--summary", str(dest))
    assert rc != 0
    assert f"{demo_project}: the graph no longer exists" in err
    assert "Traceback" not in err
    text = dest.read_text(encoding="utf-8")
    assert "tl-ratify session summary" in text
    assert f"{report.TRAILER_TOKEN}: " in text


def test_a_graph_removed_from_inside_another_is_not_replaced_by_it(run, tmp_path):
    """The reload used to resolve the path afresh, which searches from the parent
    of a directory that has gone. The reviewer then saw the enclosing graph's
    worklist, a graph they never chose."""
    outer = _named_project(tmp_path / "outer", "Outer Graph")
    inner = _named_project(outer / "inner", "Inner Graph")
    rc, err, shown = run(inner, [lambda: shutil.rmtree(inner), IDLE, ord("q")])
    assert rc != 0
    assert _one_line(err) == f"tl-ratify: {inner}: the graph no longer exists"
    assert set(shown) == {"Inner Graph"}


def test_a_graph_broken_in_place_says_it_cannot_be_read_and_why(run, demo_project):
    config = demo_project / "throughline.toml"

    def _break():
        config.write_text("[project\n", encoding="utf-8")

    rc, err, _ = run(demo_project, [_break, IDLE])
    line = _one_line(err)
    assert rc != 0
    assert line.startswith(f"tl-ratify: {demo_project}: the graph can no longer be read: ")
    assert line.count(str(demo_project)) == 1, "the path is named once"
    assert "no longer exists" not in line
    assert "Traceback" not in err


def test_the_reload_before_a_write_ends_the_same_way(run, demo_project):
    """SR-0061 reloads before it writes, by the same path as the idle reload."""
    rc, err, _ = run(demo_project, [lambda: shutil.rmtree(demo_project), ord("r")])
    assert rc != 0
    assert _one_line(err) == f"tl-ratify: {demo_project}: the graph no longer exists"


def test_the_reload_key_ends_the_same_way(run, demo_project):
    rc, err, _ = run(demo_project, [lambda: shutil.rmtree(demo_project), ord("R")])
    assert rc != 0
    assert _one_line(err) == f"tl-ratify: {demo_project}: the graph no longer exists"


def test_a_graph_picked_from_the_list_ends_the_sitting_too(run, multi_project,
                                                           tmp_path):
    """The list is not shown again: whatever removes one graph usually removes
    its neighbours, and one behaviour is easier to rely on than two."""
    dest = tmp_path / "summary.txt"
    alpha = multi_project / "alpha"
    rc, err, shown = run(
        multi_project,
        [ord("\n"), ord("r"), lambda: shutil.rmtree(alpha), IDLE, ord("\n")],
        "--summary", str(dest))
    assert rc != 0
    assert f"tl-ratify: {alpha}: the graph no longer exists" in err
    assert "Traceback" not in err
    assert set(shown) == {"Alpha Graph"}
    assert f"{report.TRAILER_TOKEN}: " in dest.read_text(encoding="utf-8")


def test_a_reload_opens_the_root_it_was_opened_from(demo_project, monkeypatch):
    session = core.open_session(demo_project)
    monkeypatch.setattr(core, "resolve_root",
                        lambda path: pytest.fail("resolved the path afresh"))
    assert core.reopen(session).root == session.root


def test_a_graph_that_still_opens_is_reloaded_as_before(run, demo_project):
    item = next((demo_project / "requirements").glob("*.yml"))

    def _touch():
        item.write_text(item.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    rc, err, _ = run(demo_project, [_touch, IDLE, ord("q")])
    assert rc == 0 and err == ""
