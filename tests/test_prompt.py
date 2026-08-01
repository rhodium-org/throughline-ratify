"""SR-0023 — text being typed at the prompt stays visible as it grows.

The old prompt truncated ``label + buffer`` to the terminal width and kept the
*front*, so past one line the display froze and the person typed blind at a cursor
pinned to the right-hand edge. A rejection reason is the worst field in the tool for
that: it is the only free-text account of why an item was refused, written once and
read later by someone who was not there. These tests hold the prompt to showing all
of it — driven against the real ``_prompt`` loop through a fake screen, because the
defect was in what reached the screen, not in what the buffer held.
"""

from __future__ import annotations

import pytest

from throughline_ratify import core, tui


# --------------------------------------------------------------------------- #
# The wrap itself
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("text", ["", "a", "abc", "x" * 79, "x" * 80, "y" * 201])
@pytest.mark.parametrize("width", [1, 7, 80])
def test_wrap_keeps_every_character(text, width):
    assert "".join(tui._wrap(text, width)) == text


@pytest.mark.parametrize("width", [1, 7, 80])
def test_wrap_fills_every_line_but_the_last(width):
    """The caret is placed with divmod(offset, width), which only holds while each
    line but the last is exactly ``width`` long — so this is load-bearing, not tidiness."""
    lines = tui._wrap("z" * 201, width)
    assert all(len(ln) == width for ln in lines[:-1])
    assert 0 < len(lines[-1]) <= width


def test_wrap_of_empty_text_is_one_empty_line():
    """A prompt with nothing typed into it still occupies a line to put the caret on."""
    assert tui._wrap("", 40) == [""]


def test_wrap_tolerates_a_nonsense_width():
    assert tui._wrap("abc", 0) == ["a", "b", "c"]


# --------------------------------------------------------------------------- #
# The prompt loop, driven against a fake screen
# --------------------------------------------------------------------------- #

class FakeScreen:
    """Enough curses to run the prompt loop, recording what lands on each row."""

    def __init__(self, height: int, width: int, keys: list[int]) -> None:
        self.h, self.w = height, width
        self.keys = list(keys)
        self.rows: dict[int, str] = {}
        self.cursor: tuple[int, int] | None = None

    def getmaxyx(self):
        return self.h, self.w

    def addstr(self, y, x, text, attr=0):
        row = self.rows.get(y, "").ljust(x)
        self.rows[y] = (row[:x] + text + row[x + len(text):]).rstrip()

    def move(self, y, x):
        self.cursor = (y, x)

    def erase(self):
        self.rows.clear()

    def getch(self):
        return self.keys.pop(0)

    def noutrefresh(self):
        pass

    def painted(self) -> str:
        return "".join(self.rows[y] for y in sorted(self.rows))


@pytest.fixture
def prompt(demo_project, monkeypatch):
    """An App whose underlying view is a no-op, so only the prompt panel is painted."""
    monkeypatch.setattr(tui.curses, "curs_set", lambda n: None)
    monkeypatch.setattr(tui.curses, "doupdate", lambda: None)
    # colour pairs need a real terminal; the panel geometry does not care about them
    monkeypatch.setattr(tui, "_attr", lambda name, bold=False: 0)
    monkeypatch.setattr(tui.App, "draw", lambda self: self.scr.erase())
    session = core.open_session(demo_project)

    def _run(typed="", height: int = 24, width: int = 40, label: str = "reason: "):
        keys = list(typed) if isinstance(typed, list) else [ord(c) for c in typed]
        scr = FakeScreen(height, width, [*keys, ord("\n")])
        app = tui.App(scr, session, "Ada Lovelace", None)
        return scr, app._prompt(label)

    return _run


def test_a_long_reason_is_all_on_screen(prompt):
    """The defect, stated as a test: everything typed can be read back off the screen."""
    reason = (
        "superseded by the composition layer, which subsumes this behaviour "
        "and records the same accountability through a single path"
    )
    scr, got = prompt(reason, width=40)
    assert got == reason
    # every wrapped line of what was typed is on the screen, in order, none missing
    expected = tui._wrap("reason: " + reason, 39)
    painted = [scr.rows[y] for y in sorted(scr.rows)]
    assert [ln.rstrip() for ln in expected] == [ln.rstrip() for ln in painted]


def test_the_panel_grows_upward_one_line_at_a_time(prompt):
    """Space is borrowed from the bottom as it is needed, so the item under review
    stays on screen while the reason is written (UR-0004)."""
    width, height = 40, 24
    heights = []
    for n in (0, 20, 40, 100):
        scr, _ = prompt("x" * n, height=height, width=width)
        heights.append(len(scr.rows))
    assert heights == sorted(heights), "the panel never shrinks as text grows"
    assert heights[0] == 1, "an empty prompt takes a single line"
    assert heights[-1] > 1, "a long reason takes more"
    # and it grows from the bottom, not the top
    scr, _ = prompt("x" * 100, height=height, width=width)
    assert max(scr.rows) == height - 1


def test_the_panel_gives_the_space_back_when_the_text_shrinks(prompt):
    """Backspacing out of a wrapped reason must release the rows it borrowed rather
    than leaving a stale line standing over the view."""
    grown, _ = prompt([ord("x")] * 100)
    shrunk, got = prompt([ord("x")] * 100 + [tui.curses.KEY_BACKSPACE] * 98)
    assert got == "xx"
    assert len(grown.rows) > 1, "the text really did wrap before being deleted"
    assert len(shrunk.rows) == 1, "the borrowed rows were released"


def test_the_cursor_sits_at_the_insertion_point(prompt):
    scr, _ = prompt("abcde", width=40)
    # label 'reason: ' is 8 chars, plus 5 typed = column 13 on the only line
    assert scr.cursor == (23, 13)


def test_the_cursor_follows_the_text_onto_the_next_line(prompt):
    scr, _ = prompt("x" * 40, width=40)
    # width used for wrapping is w - 1 = 39; 8 + 40 = 48 -> row 1, column 9
    assert scr.cursor[1] == 9
    assert scr.cursor[0] == max(scr.rows)


def test_nothing_is_dropped_in_a_very_narrow_terminal(prompt):
    """No entered character is hidden or discarded because the terminal is narrow."""
    scr, got = prompt("abcdefghij", width=12)
    assert got == "abcdefghij"
