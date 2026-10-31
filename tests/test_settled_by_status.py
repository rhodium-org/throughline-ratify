# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0087 — a signed item counts as ratified only once its status has reached
ratified.

Seen on the plan standard's conformance example at 54f5b87: seventeen items were
moved back to proposed by hand still carrying signatures. The Tool called each
ratified because the signature covered the wording, so the cockpit read 18/18
ratified and offered nothing while seventeen stood at proposed. These tests make
the same state — sign an item, then move its status back — and check what the
worklist, the progress figure and r do with it.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from throughline import ratification_progress as tool_progress
from throughline_ratify import cli, core, report, tui

SIGNED = "FR-0001"         # the fixture's proposed item, signed and then moved back


@pytest.fixture(autouse=True)
def _no_curses(monkeypatch):
    monkeypatch.setattr(tui, "_attr", lambda name, bold=False: 0)
    monkeypatch.setattr(tui, "_init_colours", lambda: None)
    monkeypatch.setattr(tui.curses, "curs_set", lambda n: None)
    monkeypatch.setattr(tui.curses, "doupdate", lambda: None)


def _path(root: Path) -> Path:
    return root / "requirements" / f"{SIGNED}.yml"


def _on_disk(root: Path) -> dict:
    return yaml.safe_load(_path(root).read_text(encoding="utf-8"))


def _sign_then_move_back(root: Path) -> Path:
    """The state on the conformance example: a signature that covers the wording,
    on an item whose status was put back to proposed by hand."""
    core.ratify_item(core.open_session(root), SIGNED, by="Grace Hopper")
    doc = _on_disk(root)
    doc["status"] = "proposed"
    _path(root).write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return root


@pytest.fixture
def signed(demo_project: Path) -> Path:
    return _sign_then_move_back(demo_project)


def _rows(root: Path, **kw) -> dict[str, core.QueueItem]:
    return {r.uid: r for r in core.build_queue(core.open_session(root), **kw)}


class _Screen:
    def __init__(self, height=24, width=160):
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


def _cockpit_on(root: Path, monkeypatch, answer: bool):
    asked: list[str] = []

    def confirm(self, question, detail=None):
        asked.append(question)
        return answer

    monkeypatch.setattr(tui.App, "_confirm", confirm)
    app = tui.App(_Screen(), core.open_session(root), "Ada Lovelace",
                  report.DecisionLog("Ada Lovelace"))
    app.sel = [r.uid for r in app.rows].index(SIGNED)
    return app, asked


def test_a_signed_item_below_ratified_is_outstanding(signed):
    row = _rows(signed)[SIGNED]                     # the default worklist
    assert row.concern == "ratified"                # the Tool's word, kept
    assert row.unsettled
    assert row.settle_path == ["proposed", "ratified"]


def test_the_progress_figure_does_not_count_it(signed):
    session = core.open_session(signed)
    done, total = core.ratification_progress(session)
    assert (done + 1, total) == tool_progress(session.project, index=session.index)


def test_r_settles_its_status_on_the_signature_it_carries(signed, monkeypatch):
    before = _on_disk(signed)["ratifications"]
    app, asked = _cockpit_on(signed, monkeypatch, answer=True)
    app.do_ratify()
    assert asked == [f"{SIGNED} is signed by Grace Hopper but at 'proposed'. Move it "
                     "to ratified on that signature via proposed → ratified?"]
    doc = _on_disk(signed)
    assert doc["status"] == "ratified"
    assert doc["ratifications"] == before            # no new signature taken
    assert SIGNED not in _rows(signed)
    (decision,) = app.log.decisions
    assert decision.kind == report.SETTLED
    assert decision.route == ("proposed", "ratified")


def test_declining_the_confirmation_writes_nothing(signed, monkeypatch):
    before = _path(signed).read_text(encoding="utf-8")
    app, _ = _cockpit_on(signed, monkeypatch, answer=False)
    app.do_ratify()
    assert app.flash.text == "settle cancelled"
    assert _path(signed).read_text(encoding="utf-8") == before


def test_a_signed_item_past_ratified_stays_settled(demo_project):
    """FR-0006 was signed and then advanced to implemented: ratified reaches
    implemented moving forward, so it is settled where it stands."""
    row = _rows(demo_project, show_all=True)["FR-0006"]
    assert row.concern == "ratified" and not row.unsettled
    assert "FR-0006" not in _rows(demo_project)
    with pytest.raises(core.RatifierError, match="nothing|no signed status"):
        core.settle_item(core.open_session(demo_project), "FR-0006")


def test_in_place_ratification_is_settled_by_the_signature(in_place_project):
    """Where ratify leaves status alone, the signature is the whole of it."""
    core.ratify_item(core.open_session(in_place_project), SIGNED, by="Grace Hopper")
    assert _on_disk(in_place_project)["status"] == "proposed"
    assert SIGNED not in _rows(in_place_project)
    assert not _rows(in_place_project, show_all=True)[SIGNED].unsettled


def test_the_row_says_signed_but_not_settled(signed, monkeypatch, capsys):
    app, _ = _cockpit_on(signed, monkeypatch, answer=False)
    lines = [text for text, _ in app._detail_lines(app.rows[app.sel], 120)]
    assert lines[0] == f"☑ {SIGNED}  signed, unsettled"
    assert ("  ☑ signed by Grace Hopper, but at 'proposed' — its status "
            "is not settled") in lines
    assert ("  ↺ press r to move it to ratified on that signature via "
            "proposed → ratified") in lines
    app._draw_summary(200)
    assert "☑ 1 signed, unsettled" in app.scr.painted()

    cli.main(["-C", str(signed), "--list"])
    line = next(ln for ln in capsys.readouterr().out.splitlines() if SIGNED in ln)
    assert "☑" in line and "unsettled" in line
