# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0075 — every line of the help can be read on a terminal shorter than the help.

The help is some 45 lines and was drawn from the top with no way to move. On a
24-row terminal it stopped just after the quit key, so the detail pane's keys and
the legend that explains the worklist's icons were never shown.
"""
from __future__ import annotations

import pytest

from throughline_ratify import core, tui

from test_reload_progress import FakeScreen

ESC, DOWN, UP = 27, tui.curses.KEY_DOWN, tui.curses.KEY_UP
PGDN, PGUP = tui.curses.KEY_NPAGE, tui.curses.KEY_PPAGE
HOME, END = tui.curses.KEY_HOME, tui.curses.KEY_END


class Keys(FakeScreen):
    """A screen that answers ``getch`` from a script and keeps every frame it
    was asked to show. A key may be a callable, run and then passed over."""

    def __init__(self, height, width, keys):
        super().__init__(height, width)
        self.keys = list(keys)
        self.frames: list[str] = []

    def getch(self):
        self.frames.append(self.painted())
        while callable(self.keys[0]):
            self.keys.pop(0)(self)
        return self.keys.pop(0)


@pytest.fixture
def help_on(demo_project, monkeypatch):
    """Open the help on a screen of the size given, press ``keys``, and return the
    screen. The last key has to be one that closes the help."""
    monkeypatch.setattr(tui.curses, "doupdate", lambda: None)
    monkeypatch.setattr(tui, "_attr", lambda name, bold=False: 0)

    def _open(keys, height=24, width=80):
        scr = Keys(height, width, keys)
        app = tui.App(scr, core.open_session(demo_project), "Ada Lovelace", None)
        app.show_help()
        assert scr.keys == [], "the help closed before every key was read"
        return scr

    return _open


def _body(frame: str) -> list[str]:
    """The help's own lines in a frame, without the row that says how to leave."""
    return [ln for ln in frame.splitlines()[:-1] if ln.strip()]


@pytest.fixture
def whole(help_on):
    """Every line of the help, from a screen tall enough to show it at once."""
    return _body(help_on([ord("q")], height=80).frames[0])


def test_the_help_is_longer_than_a_default_terminal(whole):
    """The premise. Were the help ever cut to fit, these tests would prove nothing."""
    assert len(whole) > 24


def test_a_short_terminal_opens_at_the_top_and_says_there_is_more(help_on, whole):
    first = help_on([ord("q")]).frames[0]
    assert _body(first)[0] == whole[0]
    assert "↓ more" in first.splitlines()[-1]
    assert "concerns:" not in first, "the end of the help is not on the first screen"


def test_every_line_can_be_reached_by_paging(help_on, whole):
    scr = help_on([PGDN] * 6 + [ord("q")])
    seen = {ln for frame in scr.frames for ln in _body(frame)}
    assert set(whole) <= seen


def test_every_line_can_be_reached_a_line_at_a_time(help_on, whole):
    scr = help_on([ord("j")] * len(whole) + [ord("q")])
    seen = {ln for frame in scr.frames for ln in _body(frame)}
    assert set(whole) <= seen


def test_the_detail_panes_keys_and_the_concerns_can_be_read_at_24_rows(help_on):
    """What the 24-row terminal never showed, including the symbols a narrow
    footer uses for the detail pane's keys (SR-0073)."""
    scr = help_on([END, ord("q")])
    end = scr.frames[-1]
    assert "ambiguous" in end and "ungrounded" in end
    seen = "\n".join(scr.frames + help_on([PGDN, ord("q")]).frames)
    assert "detail pane:" in seen and "concerns:" in seen
    assert "[⇥]" in seen and "[▾]" in seen


@pytest.mark.parametrize("down,up", [(ord("j"), ord("k")), (DOWN, UP)])
def test_the_line_keys_move_one_line(help_on, whole, down, up):
    scr = help_on([down, down, up, ord("q")])
    start, one_down, two_down, back_one = (
        tuple(frame.splitlines()[:4]) for frame in scr.frames)
    assert start[0] == whole[0]
    assert one_down[:3] == start[1:], "one press moved the text up by one line"
    assert two_down[:3] == one_down[1:]
    assert back_one == one_down


def test_the_page_keys_move_a_screenful(help_on):
    scr = help_on([PGDN, PGUP, ord(" "), ord("q")])
    first, paged, back, spaced = scr.frames
    assert not set(_body(first)) & set(_body(paged)), "a page shows all new lines"
    assert back == first
    assert spaced == paged, "space pages too"


def test_the_ends_hold(help_on):
    scr = help_on([ord("k"), PGUP, END, ord("j"), PGDN, ord("q")])
    top, still_top, also_top, bottom, still_bottom, also_bottom = scr.frames
    assert top == still_top == also_top
    assert bottom == still_bottom == also_bottom
    assert bottom != top


def test_home_and_end_go_to_the_top_and_the_bottom(help_on, whole):
    scr = help_on([ord("G"), ord("g"), END, HOME, ord("q")])
    top, bottom, back, bottom_again, back_again = scr.frames
    assert _body(bottom)[-1] == whole[-1]
    assert back == top == back_again and bottom_again == bottom


def test_the_last_row_says_which_way_there_is_more(help_on):
    scr = help_on([ord("j"), END, ord("q")])
    at_top, in_the_middle, at_the_end = (f.splitlines()[-1] for f in scr.frames)
    assert "↓ more" in at_top and "↑" not in at_top
    assert "↑↓ more" in in_the_middle
    assert "↑ more" in at_the_end and "↓" not in at_the_end


@pytest.mark.parametrize("width", [40, 60, 80, 120])
def test_the_last_row_always_says_how_to_leave_and_how_to_scroll(help_on, width):
    last = help_on([ord("q")], width=width).frames[0].splitlines()[-1]
    assert "q close" in last and "j/k scroll" in last
    assert len(last) <= width


def test_a_terminal_tall_enough_shows_it_all_and_offers_no_scrolling(help_on, whole):
    scr = help_on([ord("j"), PGDN, ord("q")], height=80)
    assert scr.frames[0] == scr.frames[1] == scr.frames[2]
    last = scr.frames[0].splitlines()[-1]
    assert "q close" in last and "more" not in last and "scroll" not in last


@pytest.mark.parametrize("key", [ord("q"), ord("Q"), ESC, ord("?")])
def test_these_keys_close_the_help(help_on, key):
    assert len(help_on([key]).frames) == 1


@pytest.mark.parametrize("key", [ord("x"), ord("r"), ord("\n"), ord("a"), ord("R"), 9])
def test_any_other_key_leaves_the_help_open_and_does_nothing(help_on, demo_project,
                                                             key):
    before = {p: p.read_bytes() for p in demo_project.rglob("*.yml")}
    scr = help_on([key, ord("q")])
    assert scr.frames[0] == scr.frames[1], "the help is still up, where it was"
    assert {p: p.read_bytes() for p in demo_project.rglob("*.yml")} == before


def test_a_terminal_that_shrinks_while_the_help_is_open_still_reaches_the_end(
        help_on, whole):
    def shrink(scr):
        scr.h = 12

    scr = help_on([shrink, END, ord("q")], height=80)
    assert _body(scr.frames[-1])[-1] == whole[-1]
    assert max(scr.rows) == 11


def test_a_terminal_that_grows_shows_no_gap_below_the_last_line(help_on, whole):
    def grow(scr):
        scr.h = 80

    scr = help_on([END, grow, ord("j"), ord("q")])
    assert _body(scr.frames[-1]) == whole
