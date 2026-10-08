# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0073 — the footer names its keys in whatever room there is.

At 80 columns the worklist's legend ran off the right-hand edge and took the help
and quit keys with it. The legend now uses words where they fit, symbols where
they do not, and leaves keys out only when even the symbols are too wide, never
the help key or the quit key.
"""
from __future__ import annotations

import pytest

from throughline_ratify import core, tui

from test_reload_progress import FakeScreen

SYMBOLS = {"move": "↕", "ratify": "✓", "reject": "✗", "detail": "⇥",
           "all": "∀", "sort": "⇅", "filter": "⌕", "reload": "↻"}
WORDS_FIT = 95            # the worklist's legend in words, with q:quit, and a spare cell


@pytest.fixture
def footer(demo_project, monkeypatch):
    """The footer's text at a width, for the worklist or the detail pane."""
    monkeypatch.setattr(tui.curses, "doupdate", lambda: None)
    monkeypatch.setattr(tui, "_attr", lambda name, bold=False: 0)

    def _footer(width, focus="list", quit_leads_to="quit"):
        app = tui.App(FakeScreen(24, width), core.open_session(demo_project),
                      "Ada Lovelace", None, quit_leads_to=quit_leads_to)
        app.sel = next(i for i, r in enumerate(app.rows) if r.uid == "FR-0002")
        app.focus = focus
        app.draw()
        return app.scr.rows[23]

    return _footer


def _named(footer_text: str) -> dict[str, str]:
    return dict(entry.split(":", 1) for entry in footer_text.split())


# --------------------------------------------------------------------------- #
# Words where they fit
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("width", [WORDS_FIT, 120, 200])
def test_a_wide_footer_names_every_key_in_words(footer, width):
    assert _named(footer(width)) == {
        "j/k": "move", "r/↵": "ratify", "x": "reject", "Tab": "detail", "a": "all",
        "s": "sort", "/": "filter", "R": "reload", "?": "help", "q": "quit"}


def test_the_words_are_kept_up_to_the_last_column_they_fit_in(footer):
    assert "j/k:move" in footer(WORDS_FIT)
    assert "j/k:move" not in footer(WORDS_FIT - 1)


def test_a_longer_name_for_the_quit_key_needs_more_room(footer):
    """The quit key is named by where it leads (SR-0063), and the longer name
    moves the width at which the words stop fitting."""
    assert "j/k:move" in footer(WORDS_FIT + 4, quit_leads_to="projects")
    assert "j/k:move" not in footer(WORDS_FIT + 3, quit_leads_to="projects")


# --------------------------------------------------------------------------- #
# Symbols where the words do not fit
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("quit_leads_to", ["quit", "projects"])
def test_at_eighty_columns_every_key_is_named_and_help_and_quit_are_in_words(
        footer, quit_leads_to):
    """The defect: at the default terminal width the legend lost its last two keys."""
    named = _named(footer(80, quit_leads_to=quit_leads_to))
    assert named == {
        "j/k": SYMBOLS["move"], "r/↵": SYMBOLS["ratify"], "x": SYMBOLS["reject"],
        "Tab": SYMBOLS["detail"], "a": SYMBOLS["all"], "s": SYMBOLS["sort"],
        "/": SYMBOLS["filter"], "R": SYMBOLS["reload"],
        "?": "help", "q": quit_leads_to}


def test_the_symbols_are_all_or_nothing(footer):
    """A footer that mixed words and symbols would have to be read twice."""
    for width in range(40, 130):
        names = set(_named(footer(width)).values()) - {"help", "quit"}
        assert names <= set(SYMBOLS) or names <= set(SYMBOLS.values()), width


def test_every_symbol_is_one_cell_wide():
    """A symbol two cells wide is drawn differently by different terminals, and
    the footer's own arithmetic would be wrong for it."""
    import unicodedata
    for symbol in [*SYMBOLS.values(), "▾"]:
        assert len(symbol) == 1
        assert unicodedata.east_asian_width(symbol) not in ("W", "F"), symbol


# --------------------------------------------------------------------------- #
# Keys left out when even the symbols do not fit
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("width", range(40, 130))
@pytest.mark.parametrize("quit_leads_to", ["quit", "projects"])
def test_the_footer_always_fits_and_always_names_help_and_quit(footer, width,
                                                               quit_leads_to):
    text = footer(width, quit_leads_to=quit_leads_to)
    assert len(text) < width
    named = _named(text)
    assert named["?"] == "help" and named["q"] == quit_leads_to


def test_moving_signing_and_rejecting_are_never_left_out(footer):
    for width in range(40, 130):
        assert {"j/k", "r/↵", "x"} <= set(_named(footer(width)))


def test_keys_are_left_out_in_a_fixed_order_reload_first(footer):
    """Reload goes first because the cockpit reloads by itself (SR-0062), then
    filter, sort, the wide view, and the detail pane last."""
    gone_at = {}
    for width in range(129, 39, -1):
        for key in {"Tab", "a", "s", "/", "R"} - set(_named(footer(width))):
            gone_at.setdefault(key, width)
    assert gone_at["R"] > gone_at["/"] > gone_at["s"] > gone_at["a"] > gone_at["Tab"]


def test_a_key_left_out_of_the_footer_still_works(demo_project, monkeypatch):
    monkeypatch.setattr(tui.curses, "doupdate", lambda: None)
    monkeypatch.setattr(tui, "_attr", lambda name, bold=False: 0)
    app = tui.App(FakeScreen(24, 44), core.open_session(demo_project), "Ada Lovelace",
                  None)
    app.draw()
    assert "s:" not in app.scr.rows[23]
    before = app.sort
    app.handle(ord("s"))
    assert app.sort != before


# --------------------------------------------------------------------------- #
# The detail pane's legend, and the help screen
# --------------------------------------------------------------------------- #

def test_the_detail_panes_legend_follows_the_same_rule(footer):
    assert _named(footer(120, focus="detail")) == {
        "j/k": "link", "e/↵": "expand", "x": "remove", "Tab": "list",
        "?": "help", "q": "quit"}
    narrow = _named(footer(44, focus="detail"))
    assert narrow["?"] == "help" and narrow["q"] == "quit"
    assert narrow["j/k"] == "↕" and narrow["e/↵"] == "▾"


def test_the_help_screen_shows_each_symbol_beside_its_key(demo_project, monkeypatch):
    monkeypatch.setattr(tui.curses, "doupdate", lambda: None)
    monkeypatch.setattr(tui, "_attr", lambda name, bold=False: 0)

    class Tall(FakeScreen):
        def getch(self):
            return ord("x")

    app = tui.App(Tall(60, 100), core.open_session(demo_project), "Ada Lovelace", None)
    app.show_help()
    help_text = app.scr.painted()
    for symbol in [*SYMBOLS.values(), "▾"]:
        assert f"[{symbol}]" in help_text


def test_the_legend_is_decided_without_a_screen():
    keys = [("a", "alpha", "A", 0), ("b", "beta", "B", 2), ("c", "gamma", "C", 1),
            ("?", "help", None, 0)]
    assert tui._legend(keys, 80) == [("a", "alpha"), ("b", "beta"), ("c", "gamma"),
                                     ("?", "help")]
    assert tui._legend(keys, 30) == [("a", "A"), ("b", "B"), ("c", "C"), ("?", "help")]
    assert tui._legend(keys, 21) == [("a", "A"), ("c", "C"), ("?", "help")]
    assert tui._legend(keys, 16) == [("a", "A"), ("?", "help")]
    assert tui._legend(keys, 3) == [("a", "A"), ("?", "help")], "rank 0 is never left out"
