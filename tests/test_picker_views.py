# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0090 — v switches the selection screen between favourites, every graph and
the graphs not yet favourites.
"""
from __future__ import annotations

import pytest

from conftest import _named_project
from test_back_to_the_list import Screen, no_curses  # noqa: F401 - fixture
from throughline_ratify import core, tui


@pytest.fixture
def three(multi_project):
    """Three graphs, so a view of the rest still holds more than one."""
    _named_project(multi_project / "gamma", "Gamma Graph")
    return multi_project


def _favour(*roots):
    favourites = core.Favourites()
    for root in roots:
        favourites.toggle(root)


def _pick(base, keys, width=120):
    screen = Screen(keys, width=width)
    picker = tui._Picker(screen, core.discover_projects(base))
    return screen, picker.choose(), picker


def _listed(screen: Screen) -> list[str]:
    return [row for y, row in sorted(screen.rows.items())
            if tui._PICKER_TOP <= y < screen.h - 1 and "Graph" in row]


def test_with_no_favourites_the_screen_opens_on_every_graph(three, no_curses):
    screen, _, picker = _pick(three, [ord("q")])
    assert picker.view == "all"
    assert "view:all 3/3" in screen.painted()
    assert len(_listed(screen)) == 3


def test_with_a_favourite_the_screen_opens_on_the_favourites(three, no_curses):
    _favour(three / "beta")
    screen, chosen, _ = _pick(three, [ord("\n")])
    assert "view:favourites 1/3" in screen.painted()
    assert [r for r in _listed(screen)] == [_listed(screen)[0]]
    assert chosen.name == "Beta Graph"


def test_v_cycles_favourites_every_graph_and_the_rest(three, no_curses):
    _favour(three / "beta")
    screen = Screen([ord("v"), ord("q")])
    picker = tui._Picker(screen, core.discover_projects(three))
    seen = []
    for _ in range(3):
        seen.append((core.VIEW_NAMES[picker.view], [c.name for c in picker.candidates]))
        picker.next_view()
    assert seen == [
        ("favourites", ["Beta Graph"]),
        ("not yet favourites", ["Alpha Graph", "Gamma Graph"]),
        ("all", ["Alpha Graph", "Beta Graph", "Gamma Graph"]),
    ]
    assert picker.view == "favourites"


def test_the_view_in_force_is_named(three, no_curses):
    _favour(three / "beta")
    screen, _, _ = _pick(three, [ord("v"), ord("q")])
    assert "view:not yet favourites 2/3" in screen.painted()


def test_changing_view_keeps_the_highlight_on_its_graph(three, no_curses):
    _favour(three / "beta")
    # favourites -> the rest -> every graph, down to Beta, then to the
    # favourites again: Beta is listed there, so the highlight stays on it.
    _, chosen, picker = _pick(three, [ord("v"), ord("v"), ord("j"), ord("v"), ord("\n")])
    assert picker.view == "favourites"
    assert chosen.name == "Beta Graph"


def test_changing_view_puts_the_highlight_on_the_first_row_otherwise(three, no_curses):
    _favour(three / "beta")
    _, chosen, _ = _pick(three, [ord("v"), ord("\n")])
    assert chosen.name == "Alpha Graph"


def test_unmarking_in_the_favourites_view_takes_the_graph_out(three, no_curses):
    _favour(three / "alpha", three / "gamma")
    screen, chosen, picker = _pick(three, [ord("j"), ord("f"), ord("\n")])
    assert [c.name for c in picker.candidates] == ["Alpha Graph"]
    assert chosen.name == "Alpha Graph", "the highlight stays on a listed row"


def test_marking_in_the_view_of_the_rest_takes_the_graph_out(three, no_curses):
    _favour(three / "beta")
    _, chosen, picker = _pick(three, [ord("v"), ord("f"), ord("\n")])
    assert [c.name for c in picker.candidates] == ["Gamma Graph"]
    assert chosen.name == "Gamma Graph"


def test_an_empty_view_says_so_and_opens_nothing(multi_project, no_curses):
    _favour(multi_project / "alpha", multi_project / "beta")
    screen, chosen, _ = _pick(multi_project, [ord("v"), ord("\n"), ord("q")])
    assert chosen is None
    assert "every one of these graphs is a favourite" in screen.painted()
    assert "v shows them" in screen.painted()


def test_unmarking_the_last_favourite_leaves_an_empty_view_that_names_v(multi_project,
                                                                       no_curses):
    _favour(multi_project / "alpha")
    screen, chosen, _ = _pick(multi_project, [ord("f"), ord("\n"), ord("q")])
    assert chosen is None
    assert "none of these graphs is a favourite yet" in screen.painted()


def test_the_order_in_force_applies_within_a_view(three, no_curses):
    _favour(three / "alpha", three / "gamma")
    screen = Screen([ord("q")])
    picker = tui._Picker(screen, core.discover_projects(three))
    picker.found = [c if c.root.name != "gamma" else
                    core.replace(c, gradable=5, ratified=0) for c in picker.found]
    picker.resort()
    assert picker.sort == "outstanding"
    assert [c.name for c in picker.candidates] == ["Gamma Graph", "Alpha Graph"]


def test_the_footer_names_f_and_v_at_eighty_columns(multi_project, no_curses):
    screen, _, _ = _pick(multi_project, [ord("q")], width=80)
    footer = screen.rows[screen.h - 1]
    assert "f favourite" in footer and "v view" in footer
    assert "leave without opening" in footer


def test_the_view_is_kept_for_the_sitting(three, no_curses):
    _favour(three / "beta")
    chooser = tui.ProjectChooser(core.discover_projects(three))
    chooser.ask(Screen([ord("v"), ord("\n")]))
    screen = Screen([ord("q")])
    chooser.ask(screen)
    assert "view:not yet favourites" in screen.painted()


def test_the_view_is_not_remembered_between_runs(three, no_curses):
    _favour(three / "beta")
    tui.ProjectChooser(core.discover_projects(three)).ask(Screen([ord("v"), ord("q")]))
    screen = Screen([ord("q")])
    tui.ProjectChooser(core.discover_projects(three)).ask(screen)
    assert "view:favourites" in screen.painted()
