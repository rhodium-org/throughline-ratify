# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0061, SR-0062 — a screen left open does not sign wording it never showed.

The cockpit writes from the copy of the graph it read when it opened. While it sits
open, something else can rewrite an item: an agent amending a requirement is the
ordinary case. Signing then used to write the *old* wording back over the new one
and stamp it, so the record said a human had accepted text that was no longer what
the file had held a moment before, and the amendment was gone.

These tests rewrite a file behind an open cockpit and then press the keys.
"""

from __future__ import annotations

import os
import time

import pytest

from throughline_ratify import core, tui

from test_reload_progress import FakeScreen

ADA = "Ada Lovelace"


class Keys(FakeScreen):
    """A screen that also answers ``getch`` from a script and records ``timeout``."""

    def __init__(self, keys=()) -> None:
        super().__init__()
        self.keys = list(keys)
        self.timeouts: list[int] = []
        self.waited_with: list[int] = []

    def keypad(self, on):
        pass

    def timeout(self, ms):
        self.timeouts.append(ms)

    def getch(self):
        self.waited_with.append(self.timeouts[-1] if self.timeouts else -1)
        return self.keys.pop(0)


@pytest.fixture
def app(demo_project, monkeypatch):
    monkeypatch.setattr(tui.curses, "doupdate", lambda: None)
    monkeypatch.setattr(tui.curses, "curs_set", lambda n: None)
    monkeypatch.setattr(tui, "_attr", lambda name, bold=False: 0)
    a = tui.App(Keys(), core.open_session(demo_project), ADA, None)
    a.sel = next(i for i, r in enumerate(a.rows) if r.uid == "FR-0001")
    return a


def _file(app, uid="FR-0001"):
    return app.session.root / "requirements" / f"{uid}.yml"


def amend(app, uid="FR-0001", old="Guided setup wizard", new="Guided setup wizard, with a skip button"):
    """Somebody else rewrites the item while the cockpit is open."""
    f = _file(app, uid)
    f.write_text(f.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
    later = time.time() + 5                      # a filesystem with coarse timestamps must still notice
    os.utime(f, (later, later))


def yes(app, monkeypatch):
    monkeypatch.setattr(app, "_confirm", lambda question, detail=None: True)


def test_a_signature_over_a_changed_file_is_not_taken(app, monkeypatch):
    """The defect, stated as a test: the old wording must not go back over the new."""
    yes(app, monkeypatch)
    amend(app)
    app.do_ratify()

    on_disk = _file(app).read_text(encoding="utf-8")
    assert "with a skip button" in on_disk, "the amendment was overwritten"
    assert "ratified_by" not in on_disk and "status: proposed" in on_disk, "it was signed anyway"
    assert "changed on disk" in app.flash.text and "nothing was signed" in app.flash.text
    assert app.current.uid == "FR-0001", "the reload moved the cursor off the item"
    assert "skip button" in app.current.title, "the screen still shows the old wording"


def test_the_same_key_then_signs_the_wording_now_shown(app, monkeypatch):
    yes(app, monkeypatch)
    amend(app)
    app.do_ratify()                                # refused, reloaded
    app.do_ratify()                                # the reviewer has now been shown it
    on_disk = _file(app).read_text(encoding="utf-8")
    assert "with a skip button" in on_disk and f"ratified_by: {ADA}" in on_disk
    fresh = core.open_session(app.session.root)
    assert not next(r for r in core.build_queue(fresh, show_all=True) if r.uid == "FR-0001").stale


def test_a_change_made_while_the_question_is_up_is_caught(app, monkeypatch):
    def confirm(question, detail=None):
        amend(app)                                 # it changes between the question and the answer
        return True

    monkeypatch.setattr(app, "_confirm", confirm)
    app.do_ratify()
    on_disk = _file(app).read_text(encoding="utf-8")
    assert "with a skip button" in on_disk and "ratified_by" not in on_disk


def test_a_rejection_over_a_changed_file_is_not_taken(app, monkeypatch):
    yes(app, monkeypatch)
    monkeypatch.setattr(app, "_prompt", lambda label, initial="": "not wanted")
    amend(app)
    app.do_reject()
    on_disk = _file(app).read_text(encoding="utf-8")
    assert "status: proposed" in on_disk and "with a skip button" in on_disk
    assert "nothing was rejected" in app.flash.text


def test_a_link_is_not_removed_over_a_changed_file(app, monkeypatch):
    yes(app, monkeypatch)
    app.sel = next(i for i, r in enumerate(app.rows) if r.uid == "FR-0002")
    app.link_sel = 1
    amend(app, "FR-0002", "Rate-limit login", "Rate-limit login attempts")
    app.do_remove_link()
    on_disk = _file(app, "FR-0002").read_text(encoding="utf-8")
    assert "relates" in on_disk and "login attempts" in on_disk
    assert "nothing was removed" in app.flash.text


def test_the_cockpits_own_writes_are_not_mistaken_for_somebody_elses(app, monkeypatch):
    yes(app, monkeypatch)
    app.do_ratify()
    assert f"ratified_by: {ADA}" in _file(app).read_text(encoding="utf-8")
    assert not core.changed_on_disk(app.session)

    opened = []
    monkeypatch.setattr(core, "open_session", lambda root: opened.append(root))
    app.idle()
    assert opened == [], "the cockpit reloaded over its own signature"
    app.sel = next(i for i, r in enumerate(app.rows) if r.uid == "FR-0002")
    monkeypatch.undo()
    yes(app, monkeypatch)
    app.do_ratify()                                # a second decision in the same sitting still goes through
    assert f"ratified_by: {ADA}" in _file(app, "FR-0002").read_text(encoding="utf-8")


def test_an_idle_cockpit_reloads_when_the_graph_changes_and_says_so(app):
    amend(app)
    app.idle()
    assert "skip button" in app.current.title
    assert "changed on disk" in app.flash.text and "reloaded" in app.flash.text
    assert not core.changed_on_disk(app.session)


def test_an_idle_cockpit_with_nothing_changed_does_nothing(app, monkeypatch):
    opened = []
    monkeypatch.setattr(core, "open_session", lambda root: opened.append(root))
    app.flash = tui._Flash("kept", "ok")
    app.idle()
    assert opened == [] and app.flash.text == "kept"


def test_a_new_item_appears_without_a_key(app):
    f = _file(app)
    new = f.with_name("FR-0012.yml")
    new.write_text(f.read_text(encoding="utf-8").replace("FR-0001", "FR-0012").replace("Guided setup wizard", "Added while open"),
                   encoding="utf-8")
    app.idle()
    assert "FR-0012" in [r.uid for r in app.rows]
    assert app.current.uid == "FR-0001"


def test_the_wait_is_bounded_only_between_keys_never_inside_a_question(app, monkeypatch):
    """A question must wait for the reviewer: the timeout that lets the cockpit look
    at the disk is set for the idle wait and cleared before any key is handled."""
    amend(app)
    app.scr.keys = [-1, ord("r"), ord("y"), ord("q")]
    app.run()
    scr = app.scr
    # the idle wait and the next key were bounded; the y/N answer was not
    assert scr.waited_with == [tui.IDLE_MS, tui.IDLE_MS, -1, tui.IDLE_MS]
    assert "skip button" in _file(app).read_text(encoding="utf-8")
    assert f"ratified_by: {ADA}" in _file(app).read_text(encoding="utf-8")     # reloaded while idle, then signed as shown
