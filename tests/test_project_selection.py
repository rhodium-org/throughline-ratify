# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""UR-0013 — choosing which graph to open when the given path holds more than one.

Resolution used to answer only "which project am I inside", by walking upward.
These tests hold it to the whole of SR-0045..SR-0048: what the downward search
finds, what it refuses to offer, what happens when nobody can be asked, and the
screen that asks.
"""
from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from throughline_ratify import cli, core, tui


# --------------------------------------------------------------------------- #
# SR-0045 — the order resolution asks its questions in
# --------------------------------------------------------------------------- #

def test_a_path_holding_two_graphs_is_the_reviewers_to_settle(multi_project):
    with pytest.raises(core.AmbiguousProjectError) as exc:
        core.resolve_root(multi_project)
    names = [c.name for c in exc.value.candidates]
    assert names == ["Alpha Graph", "Beta Graph"]
    assert [c.rel for c in exc.value.candidates] == ["alpha", "beta"]


def test_one_graph_beneath_the_path_is_opened_without_asking(multi_project):
    """The single-graph case is the one every present invocation is in, and it must
    stay a direct open rather than becoming a question."""
    shutil.rmtree(multi_project / "beta")
    assert core.resolve_root(multi_project) == multi_project / "alpha"


def test_pointing_at_a_graph_settles_it(multi_project):
    """A path that is itself a graph is the answer, not one candidate among those
    beneath it — otherwise a chosen candidate would be asked about again, and
    opening a project that happens to enclose another would become a question."""
    nested = multi_project / "alpha" / "vendored"
    nested.mkdir()
    (nested / "throughline.toml").write_text(
        (multi_project / "alpha" / "throughline.toml").read_text(), encoding="utf-8")
    assert core.resolve_root(multi_project / "alpha") == multi_project / "alpha"


def test_nothing_beneath_still_walks_upward(demo_project):
    """`tl-ratify` run from inside a project keeps working like git."""
    inside = demo_project / "requirements"
    assert core.resolve_root(inside) == demo_project


def test_no_graph_anywhere_names_all_three_directions(tmp_path):
    with pytest.raises(core.RatifierError) as exc:
        core.resolve_root(tmp_path)
    assert "at, beneath or above" in str(exc.value)


def test_a_path_naming_a_file_is_read_as_the_directory_holding_it(multi_project):
    """`-C` completed to `throughline.toml` itself is what a shell hands you when
    you tab through to the config; it names the same graph the directory does."""
    config = multi_project / "alpha" / "throughline.toml"
    assert core.resolve_root(config) == multi_project / "alpha"
    assert [c.rel for c in core.discover_projects(config)] == ["."]


def test_a_graph_named_directly_is_its_own_candidate(multi_project):
    """The path given is labelled `.` rather than by name, because the command that
    would re-open it is the one the reviewer just ran."""
    found = core.discover_projects(multi_project / "alpha")
    assert [(c.name, c.rel) for c in found] == [("Alpha Graph", ".")]


# --------------------------------------------------------------------------- #
# SR-0046 — what may appear in the choice
# --------------------------------------------------------------------------- #

def test_a_dot_directory_is_never_offered(multi_project):
    hidden = multi_project / ".cache" / "graph"
    hidden.mkdir(parents=True)
    (hidden / "throughline.toml").write_text("[project]\nname = 'Hidden'\n", encoding="utf-8")
    assert "Hidden" not in [c.name for c in core.discover_projects(multi_project)]


def test_a_virtualenv_is_never_offered(multi_project):
    venv = multi_project / "env"
    (venv / "lib").mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
    (venv / "lib" / "throughline.toml").write_text(
        "[project]\nname = 'Vendored'\n", encoding="utf-8")
    assert "Vendored" not in [c.name for c in core.discover_projects(multi_project)]


def test_a_git_ignored_graph_is_never_offered(multi_project):
    """Asked of git rather than answered from a list of directory names, so a
    project's own idea of what is not its source is the one that counts."""
    subprocess.run(["git", "init", "-q"], cwd=multi_project, check=True)
    (multi_project / ".gitignore").write_text("scratch/\n", encoding="utf-8")
    scratch = multi_project / "scratch"
    scratch.mkdir()
    (scratch / "throughline.toml").write_text(
        "[project]\nname = 'Scratch'\n", encoding="utf-8")
    names = [c.name for c in core.discover_projects(multi_project)]
    assert "Scratch" not in names
    assert "Alpha Graph" in names


def test_a_graph_declared_as_a_source_is_not_offered_as_a_peer(multi_project):
    """Composition gives a wider view, never a wider authority — a source offered
    beside its consumer is a graph on which every decision would then be refused."""
    borrowed = multi_project / "alpha" / "base"
    borrowed.mkdir()
    (borrowed / "throughline.toml").write_text(
        "[project]\nname = 'Borrowed'\n", encoding="utf-8")
    cfg = multi_project / "alpha" / "throughline.toml"
    cfg.write_text(
        cfg.read_text() + '\n[[sources]]\nnamespace = "base"\npath = "base"\n',
        encoding="utf-8")
    assert "Borrowed" not in [c.name for c in core.discover_projects(multi_project)]


def test_a_symlinked_directory_is_never_followed(multi_project):
    """A tree that links to itself, or to a graph already offered by its real path,
    would otherwise offer the same project twice or search forever."""
    (multi_project / "link").symlink_to(multi_project / "alpha", target_is_directory=True)
    assert [c.rel for c in core.discover_projects(multi_project)] == ["alpha", "beta"]


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0,
                    reason="root reads every directory, so there is nothing to step over")
def test_an_unreadable_directory_is_stepped_over(multi_project):
    """One directory the reviewer cannot read must not cost them the choice between
    the graphs they can."""
    walled = multi_project / "walled"
    walled.mkdir()
    walled.chmod(0o000)
    try:
        names = [c.name for c in core.discover_projects(multi_project)]
    finally:
        walled.chmod(0o755)
    assert names == ["Alpha Graph", "Beta Graph"]


def test_a_graph_whose_config_cannot_be_read_is_still_offered(multi_project):
    """Named by its directory, and with no sources believed of it. Discovery decides
    what to offer, not whether a graph is sound — refusing to list a broken one
    would hide the very project the reviewer opened the tool to go and fix."""
    broken = multi_project / "gamma"
    broken.mkdir()
    (broken / "throughline.toml").write_text("[project\nname = ", encoding="utf-8")
    assert [c.name for c in core.discover_projects(multi_project)] == [
        "Alpha Graph", "Beta Graph", "gamma"]


def test_discovery_survives_having_no_git(multi_project, monkeypatch):
    """The ignore question is asked of git as a courtesy; a tree that is not a
    repository, or a machine without git, still gets its choice."""
    def _no_git(*args, **kwargs):
        raise OSError("git: not found")

    monkeypatch.setattr(core.subprocess, "run", _no_git)
    assert [c.name for c in core.discover_projects(multi_project)] == [
        "Alpha Graph", "Beta Graph"]


def test_nothing_to_ask_about_starts_no_process(monkeypatch):
    """SR-0039: the search starts a process only where there is a question for it."""
    monkeypatch.setattr(
        core.subprocess, "run",
        lambda *a, **k: pytest.fail("ran git with nothing to ask about"))
    assert core._vcs_ignored(core.Path("."), []) == set()


def test_the_search_depth_is_a_constant_not_a_setting(multi_project):
    """SR-0026: a behaviour the assistant needs is written in its code, never
    added as a knob for the project to set."""
    deep = multi_project.joinpath(*[f"d{i}" for i in range(core._MAX_SEARCH_DEPTH + 1)])
    deep.mkdir(parents=True)
    (deep / "throughline.toml").write_text("[project]\nname = 'TooDeep'\n", encoding="utf-8")
    assert "TooDeep" not in [c.name for c in core.discover_projects(multi_project)]


# --------------------------------------------------------------------------- #
# SR-0047 — nobody to ask
# --------------------------------------------------------------------------- #

def test_list_over_an_ambiguous_path_refuses_and_says_how(multi_project, capsys):
    rc = cli.main(["-C", str(multi_project), "--list"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "Alpha Graph" in err and "Beta Graph" in err
    # the remedy is printed, not described
    assert "tl-ratify -C alpha" in err and "tl-ratify -C beta" in err


def test_an_ambiguous_path_off_a_terminal_refuses(multi_project, capsys):
    """No --list either — stdout simply is not a terminal, as in a pipeline."""
    rc = cli.main(["-C", str(multi_project)])
    assert rc == 2
    assert "tl-ratify -C alpha" in capsys.readouterr().err


def test_refusing_opens_no_graph(multi_project, monkeypatch):
    opened = []
    monkeypatch.setattr(core, "open_root", lambda root: opened.append(root))
    assert cli.main(["-C", str(multi_project), "--list"]) == 2
    assert opened == []


# --------------------------------------------------------------------------- #
# SR-0048 — the screen that asks
# --------------------------------------------------------------------------- #

@pytest.fixture
def terminal(monkeypatch):
    """A CLI run that believes it has a terminal, with the cockpit stubbed out so
    only the route through the picker is under test."""
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True, raising=False)
    opened = {}
    monkeypatch.setattr(tui, "run", lambda session, *a, **k: opened.update(root=session.root))
    return opened


def test_the_picked_graph_is_the_one_opened(multi_project, terminal, monkeypatch):
    monkeypatch.setattr(tui, "choose_project", lambda candidates: candidates[1])
    assert cli.main(["-C", str(multi_project)]) == 0
    assert terminal["root"] == multi_project / "beta"


def test_leaving_without_choosing_opens_nothing(multi_project, terminal, monkeypatch):
    monkeypatch.setattr(tui, "choose_project", lambda candidates: None)
    assert cli.main(["-C", str(multi_project)]) == 0
    assert terminal == {}


def test_a_chosen_graph_that_will_not_open_says_so(multi_project, capfd, terminal,
                                                   monkeypatch):
    """The other half of the price SR-0048 pays for listing without composing: a
    graph whose sources cannot be resolved looks sound until it is chosen, so the
    failure has to arrive legibly at that moment rather than as a traceback."""
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(tui, "choose_project", lambda candidates: candidates[0])
    monkeypatch.setattr(core, "open_root", lambda root: (_ for _ in ()).throw(
        core.RatifierError("source 'base' could not be resolved")))
    rc = cli.main(["-C", str(multi_project)])
    assert rc == 2
    assert "source 'base' could not be resolved" in capfd.readouterr().err
    assert terminal == {}


def test_the_picker_never_composes_a_graph_it_was_not_given(multi_project, monkeypatch):
    """The load-bearing half of SR-0048. Decorating the list with each candidate's
    pending count would resolve every candidate's sources — over the network for a
    remote one — on behalf of projects the reviewer never asked for."""
    monkeypatch.setattr(
        core, "_compose_if_declared",
        lambda *a, **k: pytest.fail("composed a graph before one was chosen"))
    core.discover_projects(multi_project)


# --------------------------------------------------------------------------- #
# The picker loop, driven against a fake screen
# --------------------------------------------------------------------------- #

class FakeScreen:
    def __init__(self, height, width, keys):
        self.h, self.w = height, width
        self.keys = list(keys)
        self.rows: dict[int, str] = {}

    def getmaxyx(self):
        return self.h, self.w

    def addstr(self, y, x, text, attr=0):
        row = self.rows.get(y, "").ljust(x)
        self.rows[y] = (row[:x] + text + row[x + len(text):]).rstrip()

    def erase(self):
        self.rows.clear()

    def getch(self):
        return self.keys.pop(0)

    def noutrefresh(self):
        pass

    def painted(self) -> str:
        return "\n".join(self.rows[y] for y in sorted(self.rows))


@pytest.fixture
def picker(multi_project, monkeypatch):
    monkeypatch.setattr(tui.curses, "curs_set", lambda n: None)
    monkeypatch.setattr(tui.curses, "doupdate", lambda: None)
    monkeypatch.setattr(tui, "_attr", lambda name, bold=False: 0)
    candidates = core.discover_projects(multi_project)

    def _run(keys):
        scr = FakeScreen(24, 80, keys)
        return scr, tui._Picker(scr, candidates).choose()

    return _run


def test_enter_chooses_the_highlighted_graph(picker):
    scr, chosen = picker([ord("\n")])
    assert chosen.name == "Alpha Graph"


def test_moving_down_then_choosing_takes_the_second(picker):
    scr, chosen = picker([ord("j"), ord("\n")])
    assert chosen.name == "Beta Graph"


def test_q_leaves_without_choosing(picker):
    scr, chosen = picker([ord("q")])
    assert chosen is None


def test_moving_back_up_returns_to_the_first(picker):
    scr, chosen = picker([ord("j"), ord("k"), ord("\n")])
    assert chosen.name == "Alpha Graph"


def test_the_ends_of_the_list_hold(picker):
    """Moving past either end stays where it is, so a held key cannot walk the
    highlight off the list and open a graph the reviewer never saw."""
    scr, chosen = picker([tui.curses.KEY_UP] * 3 + [tui.curses.KEY_DOWN] * 5 + [ord(" ")])
    assert chosen.name == "Beta Graph"


def test_escape_leaves_without_choosing(picker):
    scr, chosen = picker([27])
    assert chosen is None


def test_the_screen_names_every_candidate_and_its_path(picker):
    scr, _ = picker([ord("q")])
    painted = scr.painted()
    assert "Alpha Graph" in painted and "alpha" in painted
    assert "Beta Graph" in painted and "beta" in painted
    assert "leave without opening" in painted


def test_a_terminal_too_short_for_the_list_still_draws(multi_project, monkeypatch):
    """It draws what fits and keeps its keys, rather than raising out of curses and
    leaving the reviewer with a broken terminal (SR-0016)."""
    monkeypatch.setattr(tui.curses, "curs_set", lambda n: None)
    monkeypatch.setattr(tui.curses, "doupdate", lambda: None)
    monkeypatch.setattr(tui, "_attr", lambda name, bold=False: 0)
    scr = FakeScreen(5, 80, [ord("\n")])
    chosen = tui._Picker(scr, core.discover_projects(multi_project)).choose()
    assert chosen.name == "Alpha Graph"
    assert "leave without opening" in scr.painted()


def test_ctrl_c_at_the_picker_takes_no_decision(monkeypatch):
    """SR-0016 — the same answer quitting the worklist gives: the terminal is
    restored by curses.wrapper and nothing is opened."""
    monkeypatch.setattr(tui.curses, "wrapper",
                        lambda fn, *a: (_ for _ in ()).throw(KeyboardInterrupt))
    assert tui.choose_project([]) is None


def test_choose_project_runs_the_picker_inside_curses(multi_project, monkeypatch):
    """The wrapper is what restores the terminal on any exit, so the picker must be
    reached through it rather than beside it."""
    monkeypatch.setattr(tui, "_init_colours", lambda: None)
    monkeypatch.setattr(tui.curses, "curs_set", lambda n: None)
    monkeypatch.setattr(tui.curses, "doupdate", lambda: None)
    monkeypatch.setattr(tui, "_attr", lambda name, bold=False: 0)
    monkeypatch.setattr(tui.curses, "wrapper",
                        lambda fn, *a: fn(FakeScreen(24, 80, [ord("j"), ord("\n")]), *a))
    assert tui.choose_project(core.discover_projects(multi_project)).name == "Beta Graph"
