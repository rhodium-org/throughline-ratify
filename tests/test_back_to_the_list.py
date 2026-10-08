# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""UR-0018 — leaving a graph goes back to the list it was picked from.

The pick used to be final: quitting the worklist ended the program, so a
repository of several graphs cost one start of the tool for each. These tests
hold the route back (SR-0063), the state the list comes back in (SR-0064) and
the account of a sitting that took decisions in more than one graph (SR-0065).
"""
from __future__ import annotations

import pytest

from throughline_ratify import cli, core, report, tui


class Screen:
    """Enough of a curses window to run a screen's key loop against."""

    def __init__(self, keys, height=24, width=120):
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
        key = self.keys.pop(0)
        if key is KeyboardInterrupt:
            raise KeyboardInterrupt
        return key

    def keypad(self, on):
        pass

    def timeout(self, ms):
        pass

    def noutrefresh(self):
        pass

    def painted(self) -> str:
        return "\n".join(self.rows[y] for y in sorted(self.rows))


@pytest.fixture
def no_curses(monkeypatch):
    monkeypatch.setattr(tui, "_init_colours", lambda: None)
    monkeypatch.setattr(tui.curses, "curs_set", lambda n: None)
    monkeypatch.setattr(tui.curses, "doupdate", lambda: None)
    monkeypatch.setattr(tui, "_attr", lambda name, bold=False: 0)


@pytest.fixture
def sitting(multi_project, monkeypatch):
    """A run on a terminal over the two-graph tree. ``picks`` is what the reviewer
    chooses each time the list is shown; ``leaves`` is how they leave each graph,
    True for the quit key and False for an interrupt."""
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(tui, "_init_colours", lambda: None)
    seen = {"asked": 0, "opened": [], "labels": [], "views": 0, "opening": []}

    def _wrapper(fn, *a):
        seen["views"] += 1
        return fn(None, *a)

    monkeypatch.setattr(tui.curses, "wrapper", _wrapper)
    monkeypatch.setattr(tui, "_draw_opening",
                        lambda scr, candidate: seen["opening"].append(candidate.root.name))

    def _start(picks, leaves=(), decide=None, argv=()):
        leaving = list(leaves)

        class Scripted:
            def __init__(self, candidates, search=None):
                self.picks = [candidates[i] for i in picks]

            def ask(self, stdscr):
                seen["asked"] += 1
                return self.picks.pop(0) if self.picks else None

        class Cockpit:
            def __init__(self, stdscr, session, ratifier, log=None, ratifier_id=None,
                         quit_leads_to="quit"):
                self.session, self.log = session, log
                seen["labels"].append(quit_leads_to)

            def run(self):
                seen["opened"].append(self.session.root.name)
                if decide is not None:
                    decide(self.session, self.log)
                return leaving.pop(0) if leaving else True

        monkeypatch.setattr(tui, "ProjectChooser", Scripted)
        monkeypatch.setattr(tui, "App", Cockpit)
        return cli.main(["-C", str(multi_project), "--by", "Ada Lovelace", *argv])

    return _start, seen


# --------------------------------------------------------------------------- #
# SR-0063 — the quit key leads back to the list
# --------------------------------------------------------------------------- #

def test_quitting_a_picked_graph_shows_the_list_again(sitting):
    start, seen = sitting
    assert start(picks=[1, 0]) == 0
    assert seen["opened"] == ["beta", "alpha"]
    assert seen["asked"] == 3, "asked again after each graph, and left on the third"


def test_the_same_graph_can_be_opened_twice(sitting):
    start, seen = sitting
    start(picks=[0, 0])
    assert seen["opened"] == ["alpha", "alpha"]


def test_an_interrupt_in_a_picked_graph_ends_the_program(sitting):
    start, seen = sitting
    assert start(picks=[1, 0], leaves=[False]) == 0
    assert seen["opened"] == ["beta"]
    assert seen["asked"] == 1, "the list was not shown again"


def test_a_picked_graph_names_the_quit_key_by_where_it_leads(sitting):
    start, seen = sitting
    start(picks=[0])
    assert seen["labels"] == ["projects"]


def test_a_graph_that_was_not_picked_still_quits(demo_project, monkeypatch):
    """No list was shown, so there is none to go back to: the cockpit opens once,
    calls the key what it is, and the program ends."""
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(tui, "ProjectChooser",
                        lambda c: pytest.fail("asked which graph, with one to open"))
    labels = []

    class Cockpit:
        def __init__(self, *a, quit_leads_to="quit", **k):
            labels.append(quit_leads_to)

        def run(self):
            return True

    monkeypatch.setattr(tui, "App", Cockpit)
    monkeypatch.setattr(tui, "_init_colours", lambda: None)
    monkeypatch.setattr(tui.curses, "wrapper", lambda fn, *a: fn(None, *a))
    assert cli.main(["-C", str(demo_project), "--by", "Ada Lovelace"]) == 0
    assert labels == ["quit"]


def _app(root, monkeypatch, keys, **kwargs):
    monkeypatch.setattr(tui.App, "draw", lambda self: None)
    return tui.App(Screen(keys), core.open_session(root), "Ada Lovelace", **kwargs)


def test_the_cockpit_says_it_was_left_with_the_quit_key(demo_project, monkeypatch,
                                                        no_curses):
    assert _app(demo_project, monkeypatch, [ord("q")]).run() is True


def test_the_cockpit_says_it_was_interrupted(demo_project, monkeypatch, no_curses):
    assert _app(demo_project, monkeypatch, [KeyboardInterrupt]).run() is False


def test_an_interrupt_at_the_curses_boundary_is_an_interrupt_too(demo_project,
                                                                 monkeypatch):
    """SR-0016 absorbs an interrupt at the wrapper as well as in the key loop, and
    both have to say the same thing or a Ctrl-C during a prompt would go back to
    the list while one at the worklist ended the program."""
    monkeypatch.setattr(tui.curses, "wrapper",
                        lambda fn, *a: (_ for _ in ()).throw(KeyboardInterrupt))
    assert tui.run(core.open_session(demo_project), "Ada Lovelace") is False


@pytest.mark.parametrize("label", ["quit", "projects"])
def test_the_legend_and_the_help_call_the_key_what_it_does(demo_project, monkeypatch,
                                                           no_curses, label):
    app = _app(demo_project, monkeypatch, [ord("x")], quit_leads_to=label)
    app._draw_footer(0, 120)
    assert f"q:{label}" in app.scr.painted().replace(" ", "")
    app.show_help()
    assert f"q            {label}" in app.scr.painted()


# --------------------------------------------------------------------------- #
# SR-0064 — the list comes back where it was left
# --------------------------------------------------------------------------- #

@pytest.fixture
def chooser(multi_project, no_curses):
    def _choose(chooser_, keys):
        screen = Screen(keys)
        return chooser_.ask(screen), screen

    return tui.ProjectChooser(core.discover_projects(multi_project)), _choose


def test_the_highlight_comes_back_to_the_graph_just_closed(chooser):
    projects, choose = chooser
    first, _ = choose(projects, [ord("j"), ord("\n")])
    assert first.name == "Beta Graph"
    again, _ = choose(projects, [ord("\n")])
    assert again.name == "Beta Graph", "enter alone reopens the graph just left"


def test_the_order_the_reviewer_chose_is_kept(chooser):
    projects, choose = chooser
    choose(projects, [ord("s"), ord("\n")])
    _, screen = choose(projects, [ord("q")])
    assert f"sort:{core.PICKER_SORTS[1]}" in screen.painted()


def test_leaving_the_list_without_choosing_keeps_the_place(chooser):
    projects, choose = chooser
    choose(projects, [ord("j"), ord("\n")])
    choose(projects, [ord("q")])
    assert projects.last.name == "beta"


def test_the_figure_is_read_again_each_time_the_list_is_shown(chooser, multi_project):
    """The reviewer has usually just signed something in one of these graphs. The
    row for it must not go on showing the figure from before."""
    projects, choose = chooser
    _, before = choose(projects, [ord("q")])
    session = core.open_root(multi_project / "alpha")
    done, total = core.ratification_progress(session)
    row = next(r for r in core.build_queue(session) if r.ratifiable_now)
    core.ratify_item(session, row.uid, "Ada Lovelace")
    _, after = choose(projects, [ord("q")])
    assert f"{done}/{total} ratified" in before.painted()
    assert f"{done + 1}/{total} ratified" in after.painted()


def test_showing_the_list_again_composes_nothing(chooser, monkeypatch):
    projects, choose = chooser
    choose(projects, [ord("\n")])
    monkeypatch.setattr(
        core, "_compose_if_declared",
        lambda *a, **k: pytest.fail("composed a graph to show the list again"))
    choose(projects, [ord("q")])


def test_showing_the_list_again_does_not_search_again(chooser, monkeypatch):
    projects, choose = chooser
    choose(projects, [ord("\n")])
    monkeypatch.setattr(core, "discover_projects",
                        lambda *a, **k: pytest.fail("searched beneath the path again"))
    choose(projects, [ord("q")])


# --------------------------------------------------------------------------- #
# SR-0065 — one account for each graph
# --------------------------------------------------------------------------- #

def _deciding(session, log):
    log.ratified(f"{session.root.name.upper()}-{len(log) + 1}", "An item")


def test_each_graph_gets_its_own_account_in_the_order_opened(sitting, tmp_path):
    start, _ = sitting
    dest = tmp_path / "summary.txt"
    start(picks=[1, 0], decide=_deciding, argv=["--summary", str(dest)])
    text = dest.read_text(encoding="utf-8")
    assert text.count("tl-ratify session summary") == 2
    assert text.index("Beta Graph") < text.index("Alpha Graph")
    assert f"{report.TRAILER_TOKEN}: BETA-1" in text
    assert f"{report.TRAILER_TOKEN}: ALPHA-1" in text


def test_two_visits_to_one_graph_are_one_account(sitting, tmp_path):
    start, _ = sitting
    dest = tmp_path / "summary.txt"
    start(picks=[0, 1, 0], decide=_deciding, argv=["--summary", str(dest)])
    text = dest.read_text(encoding="utf-8")
    assert text.count("tl-ratify session summary") == 2
    assert f"{report.TRAILER_TOKEN}: ALPHA-1, ALPHA-2" in text


def test_a_graph_where_nothing_was_decided_has_no_account(sitting, tmp_path):
    start, _ = sitting
    dest = tmp_path / "summary.txt"
    start(picks=[0, 1], argv=["--summary", str(dest)],
          decide=lambda session, log: session.root.name == "beta"
          and _deciding(session, log))
    text = dest.read_text(encoding="utf-8")
    assert text.count("tl-ratify session summary") == 1
    assert "Alpha Graph" not in text


def test_a_sitting_with_no_decisions_anywhere_writes_no_file(sitting, tmp_path):
    start, _ = sitting
    dest = tmp_path / "summary.txt"
    start(picks=[0, 1], argv=["--summary", str(dest)])
    assert not dest.exists()


def test_the_accounts_go_to_stdout_one_after_another(capsys, sitting, monkeypatch):
    start, _ = sitting
    # capsys stands a stream of its own in for stdout, which is not a terminal.
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    start(picks=[0, 1], decide=_deciding, argv=["--summary"])
    assert capsys.readouterr().out.count("tl-ratify session summary") == 2


def test_an_account_written_earlier_is_replaced_not_added_to(sitting, tmp_path):
    """Appending is for the graphs of one sitting. The file from the sitting before
    is still replaced, as it always was."""
    start, _ = sitting
    dest = tmp_path / "summary.txt"
    dest.write_text("yesterday\n", encoding="utf-8")
    start(picks=[0, 1], decide=_deciding, argv=["--summary", str(dest)])
    assert "yesterday" not in dest.read_text(encoding="utf-8")


def test_decisions_already_taken_are_reported_when_a_later_graph_will_not_open(
        sitting, tmp_path, multi_project, monkeypatch):
    start, seen = sitting
    dest = tmp_path / "summary.txt"
    opening = core.open_root

    def _open(root):
        if root.name == "beta":
            raise core.RatifierError("source 'base' could not be resolved")
        return opening(root)

    monkeypatch.setattr(core, "open_root", _open)
    assert start(picks=[0, 1], decide=_deciding, argv=["--summary", str(dest)]) == 2
    assert seen["opened"] == ["alpha"]
    assert f"{report.TRAILER_TOKEN}: ALPHA-1" in dest.read_text(encoding="utf-8")


def test_the_ratifier_offered_is_asked_of_each_graph(multi_project, monkeypatch):
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(core, "default_ratifier", lambda root: f"signer of {root.name}")
    offered = []

    class Scripted:
        def __init__(self, candidates, search=None):
            self.picks = list(candidates)

        def ask(self, stdscr):
            return self.picks.pop(0) if self.picks else None

    class Cockpit:
        def __init__(self, stdscr, session, ratifier, *a, **k):
            offered.append(ratifier)

        def run(self):
            return True

    monkeypatch.setattr(tui, "ProjectChooser", Scripted)
    monkeypatch.setattr(tui, "App", Cockpit)
    monkeypatch.setattr(tui, "_init_colours", lambda: None)
    monkeypatch.setattr(tui, "_draw_opening", lambda scr, candidate: None)
    monkeypatch.setattr(tui.curses, "wrapper", lambda fn, *a: fn(None, *a))
    cli.main(["-C", str(multi_project)])
    assert offered == ["signer of alpha", "signer of beta"]


# --------------------------------------------------------------------------- #
# SR-0066 — one full-screen view for the whole sitting
# --------------------------------------------------------------------------- #

def test_the_terminal_is_not_handed_back_between_the_list_and_a_graph(sitting):
    """The defect: a view for each screen, so the shell showed while a graph was
    composed and again on the way back to the list."""
    start, seen = sitting
    start(picks=[1, 0, 1])
    assert seen["opened"] == ["beta", "alpha", "beta"]
    assert seen["views"] == 1


def test_the_view_says_which_graph_it_is_opening_before_it_opens_it(
        sitting, monkeypatch):
    start, seen = sitting
    opening = core.open_root
    order = []

    def _open(root):
        order.append((root.name, list(seen["opening"])))
        return opening(root)

    monkeypatch.setattr(core, "open_root", _open)
    start(picks=[1, 0])
    assert order == [("beta", ["beta"]), ("alpha", ["beta", "alpha"])]


def test_the_opening_screen_names_the_graph_and_its_path(multi_project, no_curses):
    screen = Screen([])
    beta = core.discover_projects(multi_project)[1]
    tui._draw_opening(screen, beta)
    assert "opening Beta Graph  beta" in screen.painted()


def test_a_graph_that_will_not_open_is_reported_after_the_view_has_closed(
        capfd, sitting, monkeypatch):
    """The reason has to outlive the view, so it is printed once curses.wrapper
    has returned and not drawn inside it (SR-0048)."""
    start, seen = sitting
    # capfd stands a stream of its own in for stdout, which is not a terminal.
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    closed = []
    wrapper = tui.curses.wrapper

    def _wrapper(fn, *a):
        try:
            return wrapper(fn, *a)
        finally:
            closed.append(capfd.readouterr().err)

    monkeypatch.setattr(tui.curses, "wrapper", _wrapper)
    monkeypatch.setattr(core, "open_root", lambda root: (_ for _ in ()).throw(
        core.RatifierError("source 'base' could not be resolved")))
    assert start(picks=[0]) == 2
    assert closed == [""], "nothing was printed while the view was up"
    assert "source 'base' could not be resolved" in capfd.readouterr().err


def test_an_interrupt_while_a_graph_is_opening_ends_cleanly(sitting, monkeypatch):
    start, seen = sitting
    monkeypatch.setattr(core, "open_root",
                        lambda root: (_ for _ in ()).throw(KeyboardInterrupt))
    assert start(picks=[0]) == 0
    assert seen["opened"] == []


# --------------------------------------------------------------------------- #
# SR-0068 — R reloads the list from disk
# --------------------------------------------------------------------------- #

@pytest.fixture
def reloading(multi_project, no_curses):
    """The selection screen as the program builds it, with the search it repeats.
    A key may be a callable, run when the screen asks for it and then passed over,
    so the tree can change while the screen is up."""
    class Changing(Screen):
        def getch(self):
            while callable(self.keys[0]) and self.keys[0] is not KeyboardInterrupt:
                self.keys.pop(0)()
            return super().getch()

    projects = tui.ProjectChooser(
        core.discover_projects(multi_project),
        search=lambda: cli._search_beneath(multi_project))

    def _choose(keys):
        screen = Changing(keys)
        return projects.ask(screen), screen

    return _choose


def _sign_one(root):
    session = core.open_root(root)
    row = next(r for r in core.build_queue(session) if r.ratifiable_now)
    core.ratify_item(session, row.uid, "Ada Lovelace")
    return core.ratification_progress(session)


def test_a_reload_reads_the_figures_again(reloading, multi_project):
    seen = {}

    def _sign():
        seen["now"] = _sign_one(multi_project / "alpha")

    chosen, screen = reloading([_sign, ord("R"), ord("q")])
    done, total = seen["now"]
    assert chosen is None
    assert f"{done}/{total} ratified" in screen.painted()
    assert f"{done - 1}/{total} ratified" in screen.painted(), "beta is as it was"


def test_without_a_reload_the_figure_stays_as_first_read(reloading, multi_project):
    """The other half of the test above: the figure moves because R was pressed,
    not because the screen was drawn again."""
    seen = {}

    def _sign():
        seen["now"] = _sign_one(multi_project / "alpha")

    _, screen = reloading([_sign, ord("j"), ord("q")])
    done, total = seen["now"]
    assert f"{done}/{total} ratified" not in screen.painted()


def test_a_reload_finds_a_graph_added_since_the_program_started(reloading,
                                                                multi_project):
    from conftest import _named_project
    chosen, screen = reloading([
        ord("j"), lambda: _named_project(multi_project / "aardvark", "Aardvark Graph"),
        ord("R"), ord("\n")])
    assert "3 throughline projects" in screen.painted()
    assert "Aardvark Graph" in screen.painted()
    assert chosen.name == "Beta Graph", "the highlight stayed on the graph it was on"


def test_a_reload_drops_a_graph_that_has_gone(reloading, multi_project):
    import shutil
    chosen, screen = reloading([
        ord("j"), lambda: shutil.rmtree(multi_project / "beta"), ord("R"), ord("\n")])
    assert "Beta Graph" not in screen.painted()
    assert chosen.name == "Alpha Graph", "the highlight is on a row that is listed"


def test_a_reload_says_so_until_the_next_key(reloading):
    _, screen = reloading([ord("R"), ord("q")])
    assert "reloaded from disk" in screen.painted()
    _, screen = reloading([ord("R"), ord("j"), ord("q")])
    # The last draw before q was read is the one after j.
    assert "reloaded from disk" not in screen.painted()


def test_a_reload_keeps_the_order_in_force(reloading):
    _, screen = reloading([ord("s"), ord("R"), ord("q")])
    assert f"sort:{core.PICKER_SORTS[1]}" in screen.painted()


def test_a_reload_that_finds_nothing_leaves_an_empty_list_that_opens_nothing(
        reloading, multi_project):
    import shutil

    def _empty():
        shutil.rmtree(multi_project / "alpha")
        shutil.rmtree(multi_project / "beta")

    chosen, screen = reloading([_empty, ord("R"), ord("\n"), ord("j"), ord("k"),
                                ord("s"), ord("R"), ord("q")])
    assert chosen is None
    assert "0 throughline projects" in screen.painted()


def test_a_path_that_has_gone_is_not_searched_from_its_parent(reloading,
                                                              multi_project):
    """discover_projects searches the parent of a path that is not a directory.
    A graph beside the path the reviewer gave is not one they pointed at."""
    import shutil
    from conftest import _named_project

    def _replace():
        shutil.rmtree(multi_project)
        _named_project(multi_project.parent / "neighbour", "Neighbour Graph")

    chosen, screen = reloading([_replace, ord("R"), ord("q")])
    assert "Neighbour Graph" not in screen.painted()
    assert "0 throughline projects" in screen.painted()


def test_a_reload_composes_nothing(reloading, monkeypatch):
    monkeypatch.setattr(
        core, "_compose_if_declared",
        lambda *a, **k: pytest.fail("composed a graph to reload the list"))
    reloading([ord("R"), ord("q")])


def test_the_small_letter_does_not_reload(reloading, monkeypatch):
    monkeypatch.setattr(core, "discover_projects",
                        lambda *a, **k: pytest.fail("searched on a key that is not R"))
    _, screen = reloading([ord("r"), ord("q")])
    assert "reloaded from disk" not in screen.painted()


def test_the_footer_of_the_list_names_the_key(reloading):
    _, screen = reloading([ord("q")])
    assert "R reload" in screen.painted()


def test_the_program_hands_the_list_the_search_beneath_the_path_given(
        multi_project, monkeypatch):
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True, raising=False)
    found = []
    monkeypatch.setattr(
        tui, "work_through",
        lambda candidates, open_graph, ratifier_id=None, search=None:
        found.extend(search()))
    assert cli.main(["-C", str(multi_project), "--by", "Ada Lovelace"]) == 0
    assert [c.name for c in found] == ["Alpha Graph", "Beta Graph"]
