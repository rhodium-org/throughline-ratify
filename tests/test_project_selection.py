# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""UR-0013 — choosing which graph to open when the given path holds more than one.

Resolution used to answer only "which project am I inside", by walking upward.
These tests hold it to the whole of SR-0045..SR-0048: what the downward search
finds, what it refuses to offer, what happens when nobody can be asked, and the
screen that asks.
"""
from __future__ import annotations

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


def test_the_screen_names_every_candidate_and_its_path(picker):
    scr, _ = picker([ord("q")])
    painted = scr.painted()
    assert "Alpha Graph" in painted and "alpha" in painted
    assert "Beta Graph" in painted and "beta" in painted
    assert "leave without opening" in painted
