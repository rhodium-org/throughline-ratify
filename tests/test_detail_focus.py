# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0013 — the detail pane takes focus, and its links can be walked and expanded.

Driven through the keys on a consumer that composes a source, so the link that is
expanded reaches an item the consumer does not hold: the borrowed clause has to
be readable where the reviewer is.
"""
from __future__ import annotations

import pytest

from throughline_ratify import core, tui

from test_core import _composed_consumer
from test_reload_progress import FakeScreen

TAB, ESC, UP, DOWN = 9, 27, tui.curses.KEY_UP, tui.curses.KEY_DOWN


@pytest.fixture
def open_on(tmp_path, monkeypatch):
    monkeypatch.setattr(tui.curses, "doupdate", lambda: None)
    monkeypatch.setattr(tui, "_attr", lambda name, bold=False: 0)
    consumer = _composed_consumer(tmp_path)

    def _open(uid):
        app = tui.App(FakeScreen(40, 120), core.open_session(consumer),
                      "Ada Lovelace", None)
        app.sel = next(i for i, r in enumerate(app.rows) if r.uid == uid)
        app.draw()
        return app

    return _open


def _press(app, *keys):
    """Press each key and draw after it, as the cockpit's own loop does."""
    for key in keys:
        app.handle(key)
        app.draw()
    return app.scr.painted()


def _cursor_line(app) -> str:
    """The line of the detail pane the link cursor is on."""
    width = app._list_width()
    return next(row[width:] for row in app.scr.rows.values()
                if row[width:].lstrip("│ ").startswith("▸"))


def test_tab_moves_focus_to_the_detail_pane_and_back(open_on):
    app = open_on("FR-0002")
    assert app.focus == "list"
    _press(app, TAB)
    assert app.focus == "detail"
    _press(app, TAB)
    assert app.focus == "list"


def test_escape_returns_focus_to_the_worklist(open_on):
    app = open_on("FR-0002")
    _press(app, TAB, ESC)
    assert app.focus == "list"


def test_the_footer_and_the_pane_say_which_has_focus(open_on):
    app = open_on("FR-0002")
    assert "Tab:detail" in app.scr.rows[39]
    painted = _press(app, TAB)
    assert "Tab:list" in app.scr.rows[39]
    assert "e expand" in painted


def test_an_item_with_no_links_keeps_focus_on_the_worklist_and_says_why(open_on):
    app = open_on("FR-0003")
    painted = _press(app, TAB)
    assert app.focus == "list"
    assert "no links to inspect" in painted


@pytest.mark.parametrize("down,up", [(DOWN, UP), (ord("j"), ord("k"))])
def test_up_and_down_move_a_cursor_over_the_links(open_on, down, up):
    app = open_on("FR-0002")             # mitigates RISK-0001, relates FR-0001
    _press(app, TAB)
    assert "RISK-0001" in _cursor_line(app)
    _press(app, down)
    assert "FR-0001" in _cursor_line(app)
    _press(app, down)
    assert "FR-0001" in _cursor_line(app), "the last link holds"
    _press(app, up)
    assert "RISK-0001" in _cursor_line(app)
    _press(app, up)
    assert "RISK-0001" in _cursor_line(app), "the first link holds"


def test_with_focus_on_the_pane_the_keys_do_not_move_the_worklist(open_on):
    app = open_on("FR-0002")
    before = app.sel
    _press(app, TAB, DOWN, DOWN)
    assert app.sel == before


@pytest.mark.parametrize("key", [ord("\n"), ord("e")])
def test_expanding_a_link_shows_the_targets_type_status_and_body(open_on, key):
    app = open_on("FR-0002")
    painted = _press(app, TAB)
    assert "Body of RISK-0001." not in painted
    painted = _press(app, key)
    assert "risk · ratified" in painted
    assert "Body of RISK-0001." in painted
    painted = _press(app, key)
    assert "Body of RISK-0001." not in painted, "the same key closes it again"


def test_only_the_link_under_the_cursor_is_expanded(open_on):
    app = open_on("FR-0002")
    painted = _press(app, TAB, DOWN, ord("e"))
    assert "Body of FR-0001." in painted
    assert "Body of RISK-0001." not in painted


def test_a_borrowed_clause_is_read_in_place(open_on):
    """FR-0009 grounds through base:INT-0001, an item the consumer does not hold.
    Its content comes from the composed union."""
    app = open_on("FR-0009")
    painted = _press(app, TAB, ord("e"))
    assert "base:INT-0001" in painted
    assert "intent · ratified" in painted
    assert "Body of INT-0001." in painted


def test_moving_to_another_item_closes_what_was_expanded(open_on):
    app = open_on("FR-0002")
    _press(app, TAB, ord("e"), TAB, ord("j"), ord("k"))
    assert "Body of RISK-0001." not in app.scr.painted()
