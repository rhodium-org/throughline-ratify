# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0091 to SR-0093 — the selection screen over a large tree.

Over 427 graphs, a picked graph that would not open ended the program, the
widest name and reason pushed every path off the screen, and nothing narrowed
the list. These hold the screen to coming back, fitting, and filtering.
"""
from __future__ import annotations

import os
from dataclasses import replace

import pytest

from conftest import _named_project
from test_back_to_the_list import Screen, no_curses  # noqa: F401 - fixture
from test_read_older_format import format3_project  # noqa: F401 - fixture
from throughline_ratify import core, tui


@pytest.fixture
def caseflow(multi_project):
    """Graphs named alike, told apart only by path, beside two that are not."""
    for role in ("developer", "tester"):
        _named_project(multi_project / "caseflow" / role / "idd", f"Caseflow {role}")
    return multi_project


def _pick(base, keys, width=120, **kwargs):
    screen = Screen(keys, width=width)
    picker = tui._Picker(screen, core.discover_projects(base), **kwargs)
    return screen, picker.choose(), picker


def _typed(text: str) -> list[int]:
    return [ord(ch) for ch in text]


# --------------------------------------------------------------------------- #
# SR-0091 — a picked graph that will not open brings the list back
# --------------------------------------------------------------------------- #

def _sitting(monkeypatch, base, picks, refuse):
    """Run work_through over ``base`` with the screen stood in for: ``picks``
    are the rows chosen in turn, and opening a graph named in ``refuse`` raises
    its reason. Returns the graphs opened and what the screen said each time."""
    monkeypatch.setattr(tui.curses, "wrapper", lambda fn, *a: fn(None, *a))
    monkeypatch.setattr(tui, "_draw_opening", lambda scr, candidate: None)
    shown, opened = [], []

    def _ask(self, stdscr):
        shown.append((self.note, self.last))
        if not picks:
            return None
        chosen = self.candidates[picks.pop(0)]
        self.last = chosen.root
        return chosen

    class Cockpit:
        def __init__(self, stdscr, session, *a, **k):
            self.session = session

        def run(self):
            opened.append(self.session)
            return True

    def _open(candidate):
        if candidate.root.name in refuse:
            raise refuse[candidate.root.name]
        return candidate.root.name, "Ada", None

    monkeypatch.setattr(tui.ProjectChooser, "ask", _ask)
    monkeypatch.setattr(tui, "App", Cockpit)
    tui.work_through(core.discover_projects(base), _open)
    return opened, shown


def test_an_older_graph_picked_brings_the_list_back_saying_why(multi_project, no_curses,
                                                                 monkeypatch):
    older = core.RatifierError("throughline.toml is at format version 3 — run `tl migrate`")
    opened, shown = _sitting(monkeypatch, multi_project, [1, 0], {"beta": older})
    assert shown[1] == (f"{older} \u2014 beta", multi_project / "beta"), \
        "the list comes back on that graph, saying why"
    assert opened == ["alpha"], "the next pick still opens"


def test_an_identity_that_cannot_be_settled_brings_the_list_back(multi_project,
                                                                 no_curses, monkeypatch):
    roles = core.RatifierError("this graph declares roles (senior) — say which you sign in with --as <role>")
    opened, shown = _sitting(monkeypatch, multi_project, [0], {"alpha": roles})
    assert shown[1][0].startswith("this graph declares roles")
    assert shown[1][0].endswith("\u2014 alpha")
    assert opened == []


def test_the_reason_shows_until_the_next_key(multi_project, no_curses):
    screen = Screen([ord("j"), ord("q")])
    picker = tui._Picker(screen, core.discover_projects(multi_project), note="beta: refused")
    picker.choose()
    assert "beta: refused" not in screen.painted()


def test_a_graph_opened_directly_is_still_refused_on_standard_error(format3_project, capsys,
                                                                   monkeypatch):
    from throughline_ratify import cli
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True, raising=False)
    assert cli.main(["-C", str(format3_project), "--by", "Ada"]) == 2
    assert "tl migrate" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# SR-0092 — every row fits, and shows its path
# --------------------------------------------------------------------------- #

def _rows(screen: Screen) -> list[str]:
    return [row for y, row in sorted(screen.rows.items())
            if tui._PICKER_TOP <= y < screen.h - 1]


def test_a_long_name_is_cut_to_a_third_of_the_screen(multi_project, no_curses):
    found = core.discover_projects(multi_project)
    found[0] = replace(found[0], name="A" * 200)
    screen = Screen([ord("q")], width=90)
    tui._Picker(screen, found).choose()
    row = _rows(screen)[0]
    assert "A" * 29 + "…" in row and "A" * 31 not in row
    assert row.rstrip().endswith("alpha"), "the path is still shown"


def test_an_unreadable_graph_shows_a_mark_not_its_reason(multi_project, no_curses):
    found = core.discover_projects(multi_project)
    reason = "throughline.toml is at format version 3; " + "x" * 300
    found[1] = replace(found[1], error=reason)
    screen = Screen([ord("q")], width=100)
    tui._Picker(screen, found).choose()
    alpha, beta = _rows(screen)
    assert "⚠ cannot be read" in beta and "format version" not in beta
    assert beta.rstrip().endswith("beta") and alpha.rstrip().endswith("alpha")


def test_the_reason_is_given_above_the_list_while_its_graph_is_highlighted(multi_project,
                                                                           no_curses):
    found = core.discover_projects(multi_project)
    found[1] = replace(found[1], error="format version 3 — run `tl migrate`")
    screen = Screen([ord("q")])
    picker = tui._Picker(screen, found)
    picker.draw()
    assert "format version 3" not in screen.rows.get(3, "")
    picker.pos = 1
    picker.draw()
    assert screen.rows[3].strip() == "format version 3 — run `tl migrate` — beta"


def test_the_reason_leaves_out_the_graphs_own_path(multi_project, no_curses):
    found = core.discover_projects(multi_project)
    beta = found[1]
    found[1] = replace(beta, error=f"{beta.root / 'throughline.toml'} is at format version 3")
    screen = Screen([ord("q")])
    picker = tui._Picker(screen, found)
    picker.pos = 1
    picker.draw()
    assert screen.rows[3].strip() == "throughline.toml is at format version 3 — beta"


def test_a_note_takes_the_line_before_the_reason(multi_project, no_curses):
    found = core.discover_projects(multi_project)
    found[0] = replace(found[0], error="unreadable")
    screen = Screen([ord("q")])
    tui._Picker(screen, found, note="reloaded from disk").draw()
    assert screen.rows[3].strip() == "reloaded from disk"


def test_a_long_path_keeps_its_end(no_curses, tmp_path):
    deep = tmp_path / ("very-long-directory-name-" * 3) / "one" / "two" / "idd"
    _named_project(deep, "Deep")
    _named_project(tmp_path / "short", "Short")
    screen = Screen([ord("q")], width=60)
    tui._Picker(screen, core.discover_projects(tmp_path)).choose()
    row = next(r for r in _rows(screen) if "Deep" in r)
    assert len(row) <= 60
    assert "…" in row and row.rstrip().endswith(os.path.join("one", "two", "idd"))


def test_every_row_fits_the_width(caseflow, no_curses):
    found = core.discover_projects(caseflow)
    found = [replace(c, name=c.name * 9, error="e" * 400) for c in found]
    screen = Screen([ord("q")], width=80)
    tui._Picker(screen, found).choose()
    assert all(len(row) <= 80 for row in _rows(screen))


# --------------------------------------------------------------------------- #
# SR-0093 — / filters the list by name or path
# --------------------------------------------------------------------------- #

def test_slash_narrows_the_list_and_names_the_filter(caseflow, no_curses):
    screen, _, picker = _pick(caseflow, [ord("/"), *_typed("CASEFLOW"), ord("\n"), ord("q")])
    assert [c.name for c in picker.candidates] == ["Caseflow developer", "Caseflow tester"]
    assert "filter:CASEFLOW" in screen.painted()
    assert "view:all 2/4" in screen.painted()


def test_a_path_fragment_finds_graphs_whose_name_lacks_it(caseflow, no_curses):
    _, _, picker = _pick(caseflow, [ord("/"), *_typed(os.path.join("tester", "idd")),
                                    ord("\n"), ord("q")])
    assert [c.name for c in picker.candidates] == ["Caseflow tester"]


def test_escape_keeps_the_filter_as_it_was(caseflow, no_curses):
    _, _, picker = _pick(caseflow, [ord("/"), *_typed("alpha"), ord("\n"),
                                    ord("/"), *_typed("zzz"), 27, ord("q")])
    assert picker.filter == "alpha"
    assert [c.name for c in picker.candidates] == ["Alpha Graph"]


def test_the_filter_in_force_is_offered_for_editing(caseflow, no_curses):
    # Backspace twice over "tester" leaves "test", which still matches it.
    _, _, picker = _pick(caseflow, [ord("/"), *_typed("tester"), ord("\n"),
                                    ord("/"), 127, 127, ord("\n"), ord("q")])
    assert picker.filter == "test"


def test_an_empty_filter_shows_the_view_again(caseflow, no_curses):
    _, _, picker = _pick(caseflow, [ord("/"), *_typed("beta"), ord("\n"),
                                    ord("/"), 127, 127, 127, 127, ord("\n"), ord("q")])
    assert picker.filter == ""
    assert len(picker.candidates) == 4


def test_the_highlight_stays_on_its_graph_or_goes_to_the_first_row(caseflow, no_curses):
    # Down to Beta; "a" still lists Alpha, Beta and both Caseflow graphs.
    _, chosen, _ = _pick(caseflow, [ord("j"), ord("/"), ord("a"), ord("\n"), ord("\n")])
    assert chosen.name == "Beta Graph"
    # Down to Beta; "caseflow" does not list it, so the highlight goes to the top.
    _, chosen, _ = _pick(caseflow, [ord("j"), ord("/"), *_typed("caseflow"), ord("\n"),
                                    ord("\n")])
    assert chosen.name == "Caseflow developer"


def test_a_filter_matching_nothing_says_so_and_opens_nothing(caseflow, no_curses):
    screen, chosen, _ = _pick(caseflow, [ord("/"), *_typed("nothing"), ord("\n"),
                                         ord("\n"), ord("q")])
    assert chosen is None
    assert 'nothing here matches the filter "nothing"' in screen.painted()
    assert "/ changes it" in screen.painted()


def test_the_filter_applies_within_the_view(caseflow, no_curses):
    core.Favourites().toggle(caseflow / "caseflow" / "tester" / "idd")
    _, _, picker = _pick(caseflow, [ord("/"), *_typed("caseflow"), ord("\n"), ord("q")])
    assert picker.view == "favourites"
    assert [c.name for c in picker.candidates] == ["Caseflow tester"]


def test_the_filter_is_kept_for_the_sitting(caseflow, no_curses):
    chooser = tui.ProjectChooser(core.discover_projects(caseflow))
    chooser.ask(Screen([ord("/"), *_typed("caseflow"), ord("\n"), ord("\n")]))
    screen = Screen([ord("q")])
    chooser.ask(screen)
    assert "filter:caseflow" in screen.painted()


def test_the_footer_names_the_filter_key_at_eighty_columns(multi_project, no_curses):
    screen, _, _ = _pick(multi_project, [ord("q")], width=80)
    footer = screen.rows[screen.h - 1]
    assert "/ filter" in footer and "leave without opening" in footer


def test_matching_ignores_case_over_name_and_path(caseflow):
    found = core.discover_projects(caseflow)
    assert [c.name for c in core.matching(found, "  GRAPH ")] == ["Alpha Graph", "Beta Graph"]
    assert core.matching(found, "") == found
