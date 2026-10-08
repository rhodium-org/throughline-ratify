# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0007 — a full-screen cockpit with header, summary, list, detail and footer.

The layout is painted onto a screen that records what lands on each row, at more
than one size, and the keys that move through the worklist are pressed against
it. What is asserted is where each part is and what it carries, not its exact
wording, which other requirements own.
"""
from __future__ import annotations

import pytest

from throughline_ratify import core, tui

from test_reload_progress import FakeScreen


@pytest.fixture
def cockpit(demo_project, monkeypatch):
    """The cockpit on a screen of the size asked for, with the colours it asks
    for recorded by name."""
    asked = []
    monkeypatch.setattr(tui.curses, "doupdate", lambda: None)
    monkeypatch.setattr(tui, "_attr",
                        lambda name, bold=False: asked.append(name) or 0)

    def _open(height=24, width=120):
        app = tui.App(FakeScreen(height, width), core.open_session(demo_project),
                      "Ada Lovelace", None)
        app.asked = asked
        app.draw()
        return app

    return _open


def _selected_row(app) -> str:
    return next(row for row in app.scr.rows.values() if row.startswith("▸"))


@pytest.mark.parametrize("height,width", [(24, 100), (40, 120), (12, 160)])
def test_the_view_fills_the_terminal_from_the_first_row_to_the_last(cockpit, height,
                                                                    width):
    app = cockpit(height, width)
    rows = app.scr.rows
    assert "Ratifier Fixture" in rows[0], "the header is the first row"
    assert rows[1].lstrip().startswith("queue:"), "the summary is the second"
    assert "q:quit" in rows[height - 1], "the footer is the last"
    assert max(rows) == height - 1
    assert all(len(row) <= width for row in rows.values())


@pytest.mark.parametrize("height,width", [(24, 80), (12, 60), (6, 40)])
def test_a_narrow_terminal_keeps_every_part_in_its_place(cockpit, height, width):
    """What each part can say shrinks with the width. Where each part is does not."""
    app = cockpit(height, width)
    rows = app.scr.rows
    assert tui.__version__ in rows[0]
    assert rows[1].lstrip().startswith("queue:")
    assert rows[2].startswith("\u25b8"), "the worklist starts on the third row"
    assert rows[height - 1].lstrip().startswith("j/k:")
    assert max(rows) == height - 1
    assert all(len(row) <= width for row in rows.values())


def test_the_header_names_the_project(cockpit):
    assert "Ratifier Fixture" in cockpit().scr.rows[0]


def test_the_summary_counts_each_concern_and_asks_for_its_colour(cockpit):
    app = cockpit()
    summary = app.scr.rows[1]
    counts = {}
    for row in app.rows:
        counts[row.concern] = counts.get(row.concern, 0) + 1
    for concern in ("proposed", "ready", "stale", "blocked", "ungrounded", "ambiguous"):
        assert f"{core.CONCERN_ICONS[concern]} {counts.get(concern, 0)} " in summary
        assert concern in app.asked, f"no colour was asked for {concern}"


def test_the_worklist_shows_every_row_when_they_fit(cockpit):
    app = cockpit(height=40)
    painted = app.scr.painted()
    assert len(app.rows) > 3
    for row in app.rows:
        assert row.uid in painted


def test_the_detail_pane_shows_the_selected_item_its_grounding_and_its_links(cockpit):
    app = cockpit(height=40)
    app.sel = next(i for i, r in enumerate(app.rows) if r.uid == "FR-0002")
    app.draw()
    list_width = app._list_width()
    pane = "\n".join(row[list_width:] for row in app.scr.rows.values())
    assert "FR-0002" in pane and "Rate-limit login" in pane
    assert "grounded:" in pane
    assert "mitigates → RISK-0001" in pane
    assert "relates → FR-0001" in pane


def test_the_list_and_the_detail_pane_sit_side_by_side(cockpit):
    app = cockpit()
    list_width = app._list_width()
    body = [row for y, row in app.scr.rows.items() if 2 <= y < app.scr.h - 2]
    assert all(row[list_width:list_width + 1] in ("│", "") for row in body)
    assert any(row[list_width:list_width + 1] == "│" for row in body)


def test_the_footer_names_the_keys(cockpit):
    footer = cockpit().scr.rows[23]
    for key in ("j/k", "r/", "x:", "Tab", "?:help", "q:"):
        assert key in footer


def test_the_keys_move_through_the_worklist_and_the_detail_follows(cockpit):
    app = cockpit(height=40)
    first, second, last = app.rows[0].uid, app.rows[1].uid, app.rows[-1].uid
    assert first in _selected_row(app)
    app.handle(ord("j"))
    app.draw()
    assert second in _selected_row(app)
    assert second in app.scr.rows[2][app._list_width():], "the pane shows the new item"
    app.handle(ord("k"))
    app.draw()
    assert first in _selected_row(app)
    app.handle(ord("G"))
    app.draw()
    assert last in _selected_row(app)
    app.handle(ord("g"))
    app.draw()
    assert first in _selected_row(app)


def test_the_ends_of_the_worklist_hold(cockpit):
    app = cockpit(height=40)
    app.handle(ord("k"))
    assert app.sel == 0
    for _ in range(len(app.rows) + 3):
        app.handle(ord("j"))
    assert app.sel == len(app.rows) - 1


def test_a_worklist_longer_than_the_screen_scrolls_to_keep_the_selection_in_view(
        cockpit):
    app = cockpit(height=8)            # room for four rows of a longer worklist
    assert len(app.rows) > 4
    assert app.rows[-1].uid not in app.scr.painted()
    assert "▼" in app.scr.painted(), "the list says it runs on below"
    app.handle(ord("G"))
    app.draw()
    assert app.rows[-1].uid in _selected_row(app)
    assert app.rows[0].uid not in "\n".join(
        row[:app._list_width()] for row in app.scr.rows.values())
    assert "▲" in app.scr.painted(), "and that it runs on above"


def test_a_terminal_too_small_to_lay_out_says_so(cockpit):
    app = cockpit(height=5, width=30)
    assert app.scr.painted() == "terminal too small"
