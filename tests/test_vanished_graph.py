# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0067, SR-0070, SR-0071 — what an open cockpit does when its graph goes.

A graph that is gone ends the sitting with one line, or returns the reviewer to
the list it was picked from (SR-0067). A reload never opens a different graph in
its place (SR-0070). A graph that is still there and cannot be read keeps the
cockpit up, writing nothing, until it can be read again (SR-0071).

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
        self.rows: dict[int, str] = {}
        self.lists: list[str] = []   # each painting of the list of graphs

    def getmaxyx(self):
        return 24, 120

    def getch(self):
        while callable(self.keys[0]):
            self.keys.pop(0)()
        return self.keys.pop(0)

    def addstr(self, y, x, text, attr=0):
        row = self.rows.get(y, "").ljust(x)
        self.rows[y] = (row[:x] + text + row[x + len(text):]).rstrip()

    def erase(self):
        self.rows.clear()

    def painted(self) -> str:
        return "\n".join(self.rows[y] for y in sorted(self.rows))

    def keypad(self, on):
        pass

    def timeout(self, ms):
        pass

    def noutrefresh(self):
        pass


@pytest.fixture
def run(monkeypatch, capsys):
    """Run tl-ratify on a terminal that sends ``keys``. Returns the exit status,
    what reached standard error, and what was shown: the graphs the cockpit drew,
    what it said at the foot of each drawing, and each painting of the list."""
    shown = Shown()

    class Cockpit(tui.App):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            # On an item that can be signed, so ``r`` takes a decision.
            self.sel = next((i for i, r in enumerate(self.rows) if r.ratifiable_now), 0)

        def draw(self):
            shown.append(self.session.project_name)
            shown.said.append(self.flash.text)

        def _confirm(self, question, detail=None):
            return True

    def _run(path, keys, *argv):
        terminal = Terminal(keys)
        doupdate = lambda: shown.lists.append(terminal.painted())  # noqa: E731
        monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True, raising=False)
        monkeypatch.setattr(tui, "App", Cockpit)
        monkeypatch.setattr(tui, "_init_colours", lambda: None)
        monkeypatch.setattr(tui, "_attr", lambda name, bold=False: 0)
        monkeypatch.setattr(tui, "_draw_opening", lambda scr, candidate: None)
        monkeypatch.setattr(tui.curses, "curs_set", lambda n: None)
        monkeypatch.setattr(tui.curses, "doupdate", doupdate)
        monkeypatch.setattr(tui.curses, "wrapper", lambda fn, *a: fn(terminal, *a))
        rc = cli.main(["-C", str(path), "--by", "Ada Lovelace", *argv])
        return rc, capsys.readouterr().err, shown

    return _run


class Shown(list):
    """The graphs the cockpit drew, in order, with what else was on screen."""

    def __init__(self):
        super().__init__()
        self.said: list[str] = []
        self.lists: list[str] = []


def _one_line(err: str) -> str:
    lines = [ln for ln in err.splitlines() if ln.strip()]
    assert len(lines) == 1, f"expected one line on standard error, got:\n{err}"
    return lines[0]


# --------------------------------------------------------------------------- #
# SR-0067 — a graph that is gone
# --------------------------------------------------------------------------- #

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


def test_a_key_that_writes_says_nothing_was_written(run, demo_project):
    """SR-0061 reloads before it writes. The reviewer pressed a key and the
    program left: the line says what became of the action as well."""
    rc, err, _ = run(demo_project, [lambda: shutil.rmtree(demo_project), ord("r")])
    assert rc != 0
    assert _one_line(err) == (
        f"tl-ratify: {demo_project}: the graph no longer exists; nothing was signed")


def test_the_reload_key_ends_the_same_way(run, demo_project):
    rc, err, _ = run(demo_project, [lambda: shutil.rmtree(demo_project), ord("R")])
    assert rc != 0
    assert _one_line(err) == f"tl-ratify: {demo_project}: the graph no longer exists"


def test_a_picked_graph_that_goes_returns_to_the_list_which_says_so(
        run, multi_project, tmp_path):
    """The reviewer came from the list and the other graphs are still theirs to
    open, so the sitting goes on."""
    dest = tmp_path / "summary.txt"
    alpha = multi_project / "alpha"
    rc, err, shown = run(
        multi_project,
        [ord("\n"), ord("r"), lambda: shutil.rmtree(alpha), IDLE,   # alpha goes
         ord("j"), ord("\n"), ord("q"), ord("q")],                   # on to beta
        "--summary", str(dest))
    assert rc == 0
    assert "no longer exists" not in err and "Traceback" not in err
    assert list(dict.fromkeys(shown)) == ["Alpha Graph", "Beta Graph"]
    back = next(p for p in shown.lists if "no longer exists" in p)
    assert "alpha: the graph no longer exists" in back
    assert "choose a project" in back
    assert f"{report.TRAILER_TOKEN}: " in dest.read_text(encoding="utf-8")


def test_the_note_on_the_list_goes_at_the_next_key(run, multi_project):
    alpha = multi_project / "alpha"
    _, _, shown = run(multi_project,
                      [ord("\n"), lambda: shutil.rmtree(alpha), IDLE, ord("j"), ord("q")])
    assert "no longer exists" in shown.lists[-2]
    assert "no longer exists" not in shown.lists[-1]


def test_a_picked_graph_lost_at_a_write_says_nothing_was_written(run, multi_project):
    alpha = multi_project / "alpha"
    _, _, shown = run(multi_project,
                      [ord("\n"), lambda: shutil.rmtree(alpha), ord("r"), ord("q")])
    assert any("alpha: the graph no longer exists; nothing was signed" in p
               for p in shown.lists)


# --------------------------------------------------------------------------- #
# SR-0071 — a graph that cannot be read keeps the cockpit up
# --------------------------------------------------------------------------- #

@pytest.fixture
def breakable(demo_project):
    """Break the graph's configuration in place, and mend it."""
    config = demo_project / "throughline.toml"
    good = config.read_text(encoding="utf-8")
    return (lambda: config.write_text("[project\n", encoding="utf-8"),
            lambda: config.write_text(good, encoding="utf-8"))


def _signed(root) -> int:
    return core.ratification_progress(core.open_root(root))[0]


def test_a_graph_broken_in_place_keeps_the_cockpit_up_and_says_why(
        run, demo_project, breakable):
    break_, mend = breakable
    rc, err, shown = run(demo_project, [break_, IDLE, mend, ord("q")])
    assert rc == 0 and err == ""
    said = next(t for t in shown.said if "cannot be read" in t)
    assert "nothing can be written until it can" in said
    assert "Expected" in said, "the reason is given"
    assert str(demo_project) not in said, "the cockpit already names the graph"


def test_nothing_is_written_while_the_graph_cannot_be_read(run, demo_project,
                                                           breakable):
    break_, mend = breakable
    before = _signed(demo_project)
    rc, _, shown = run(demo_project, [break_, IDLE, ord("r"), mend, ord("q")])
    assert rc == 0
    assert _signed(demo_project) == before
    assert any(t.startswith("the graph cannot be read, so nothing was signed: ")
               for t in shown.said)


def test_a_key_that_writes_is_refused_without_waiting_for_the_interval(
        run, demo_project, breakable):
    break_, mend = breakable
    before = _signed(demo_project)
    run(demo_project, [break_, ord("r"), mend, ord("q")])
    assert _signed(demo_project) == before


def test_it_tries_again_at_each_interval(run, demo_project, breakable, monkeypatch):
    break_, mend = breakable
    tries = []
    opening = core.open_root

    def _open(root):
        tries.append(root)
        return opening(root)

    def _count_from_here():
        break_()
        monkeypatch.setattr(core, "open_root", _open)

    run(demo_project, [_count_from_here, IDLE, IDLE, IDLE, mend, ord("q")])
    assert len(tries) == 3


def test_a_mended_graph_is_reloaded_and_can_be_signed_again(run, demo_project,
                                                            breakable):
    break_, mend = breakable
    before = _signed(demo_project)
    rc, _, shown = run(demo_project,
                       [break_, IDLE, mend, IDLE, ord("r"), ord("q")])
    assert rc == 0
    assert "the graph changed on disk and has been reloaded" in shown.said
    assert _signed(demo_project) == before + 1


def test_a_broken_item_file_is_unreadable_too_not_gone(run, demo_project):
    item = next((demo_project / "requirements").glob("*.yml"))
    good = item.read_text(encoding="utf-8")
    rc, err, shown = run(demo_project, [
        lambda: item.write_text("uid: [unclosed\n", encoding="utf-8"), IDLE,
        lambda: item.write_text(good, encoding="utf-8"), ord("q")])
    assert rc == 0 and err == ""
    assert any("cannot be read" in t for t in shown.said)


def test_a_graph_broken_and_then_removed_ends_the_sitting(run, demo_project,
                                                          breakable):
    break_, _ = breakable
    rc, err, _ = run(demo_project,
                     [break_, IDLE, lambda: shutil.rmtree(demo_project), IDLE])
    assert rc != 0
    assert _one_line(err) == f"tl-ratify: {demo_project}: the graph no longer exists"


# --------------------------------------------------------------------------- #
# SR-0070 — a reload opens the root the graph was opened from
# --------------------------------------------------------------------------- #

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
