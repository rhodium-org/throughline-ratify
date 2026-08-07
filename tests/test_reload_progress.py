# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0033 — a reload shows itself before it blocks, not after it returns.

Reloading re-reads the whole graph, and on a composed project resolves every source
before it returns. The only feedback the cockpit used to give was a flash set *after*
that call came back, so for the whole of the wait the screen was indistinguishable
from a hung terminal — the defect UR-0007 names.

The obligation is therefore about *ordering*, not about wording, and these tests are
written against it directly: the reload is driven with ``open_session`` replaced by a
probe that photographs the screen at the moment it is entered. What the probe sees is
what the reviewer sees for the duration of a slow read.
"""

from __future__ import annotations

import pytest

from throughline_ratify import core, tui


class FakeScreen:
    """Enough curses to paint a frame, recording what lands on each row."""

    def __init__(self, height: int = 24, width: int = 80) -> None:
        self.h, self.w = height, width
        self.rows: dict[int, str] = {}

    def getmaxyx(self):
        return self.h, self.w

    def addstr(self, y, x, text, attr=0):
        row = self.rows.get(y, "").ljust(x)
        self.rows[y] = (row[:x] + text + row[x + len(text):]).rstrip()

    def erase(self):
        self.rows.clear()

    def noutrefresh(self):
        pass

    def painted(self) -> str:
        return "\n".join(self.rows[y] for y in sorted(self.rows))


@pytest.fixture
def app(demo_project, monkeypatch):
    monkeypatch.setattr(tui.curses, "doupdate", lambda: None)
    # colour pairs need a real terminal; none of this cares about them
    monkeypatch.setattr(tui, "_attr", lambda name, bold=False: 0)
    scr = FakeScreen()
    return tui.App(scr, core.open_session(demo_project), "Ada Lovelace", None)


def test_the_notice_is_on_screen_while_the_read_blocks(app, monkeypatch):
    """The defect, stated as a test. The probe stands in for a slow read and looks at
    the screen from inside it — the one vantage point the old code left blank."""
    seen: list[str] = []
    real = core.open_session

    def slow(root):
        seen.append(app.scr.painted())
        return real(root)

    monkeypatch.setattr(core, "open_session", slow)
    app.reload_from_disk()

    assert seen, "open_session was never reached"
    assert "reloading" in seen[0].lower(), (
        "the reader was shown nothing while the read blocked:\n" + seen[0]
    )


def test_the_notice_is_gone_once_the_reload_returns(app):
    app.reload_from_disk()
    assert app.busy == ""
    app.draw()
    painted = app.scr.painted().lower()
    assert "reloading" not in painted
    assert "reloaded from disk" in painted, "the completed reload still reports itself"


def test_a_failed_reload_does_not_leave_the_footer_claiming_work(app, monkeypatch):
    """A read that raises must not strand the notice on screen — a permanent
    'reloading…' is a worse lie than the silence this requirement replaced."""
    def boom(root):
        raise OSError("graph went away")

    monkeypatch.setattr(core, "open_session", boom)
    with pytest.raises(OSError):
        app.reload_from_disk()
    assert app.busy == ""


def test_the_notice_outranks_the_key_legend(app):
    """While the notice stands the keys are not being read, so the footer must not
    keep offering them."""
    app.busy = "reloading from disk…"
    app.draw()
    footer = app.scr.rows[app.scr.h - 1]
    assert "reloading" in footer.lower()
    assert "ratify" not in footer.lower(), "the legend was still offering keys"


def test_an_idle_cockpit_shows_no_notice(app):
    app.draw()
    assert "reloading" not in app.scr.painted().lower()
