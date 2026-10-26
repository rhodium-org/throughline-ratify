# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""UR-0020 — ratify a proposed deletion from the cockpit, knowing what it undoes
and what it marks suspect.

Since throughline 4.1.0 `tl delete` leaves a *proposed* tombstone (tl:SR-0267):
the item is live scope until a human signs the deletion record (tl:SR-0269), and
the signature that retires it marks everything grounded on it suspect
(tl:SR-0270). The Tool refuses to sign such a deletion unless the caller receives
that cascade, so a cockpit built before the rule failed loudly rather than sign a
deletion whose consequences it never wrote. These tests drive the cockpit over a
graph holding one proposed deletion with two dependents — one its lifecycle can
mark suspect, one it cannot — and check what is written, shown and reported.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from throughline_ratify import cli, core, report, tui

RISK = "RISK-0002"
MARKABLE = "FR-0012"       # approved: approved -> suspect is a declared transition
UNMARKABLE = "FR-0013"     # proposed: proposed -> suspect is not, so it is refused
RETIRED_FINGERPRINT = "sha256:" + "ab" * 32


@pytest.fixture(autouse=True)
def _no_curses(monkeypatch):
    monkeypatch.setattr(tui, "_attr", lambda name, bold=False: 0)
    monkeypatch.setattr(tui, "_init_colours", lambda: None)
    monkeypatch.setattr(tui.curses, "curs_set", lambda n: None)
    monkeypatch.setattr(tui.curses, "doupdate", lambda: None)


def _propose_deletion(root: Path) -> None:
    """A tombstone whose deletion awaits a signature, and two live items grounded
    on it. The risk was signed by alice, so the deletion undoes her acceptance;
    the record is the one `tl delete` writes (tl:SR-0267), less the signature."""
    (root / "risks" / f"{RISK}.yml").write_text(
        f"uid: {RISK}\n"
        "type: risk\n"
        "status: deleted\n"
        "title: Credential stuffing\n"
        f"text: Body of {RISK}.\n"
        "normative: true\n"
        "attrs:\n  ratified_by: alice\n"
        "deleted:\n"
        "  date: '2026-10-26'\n"
        "  reason: folded into RISK-0001\n"
        f"  fingerprint: {RETIRED_FINGERPRINT}\n"
        "  from: ratified\n",
        encoding="utf-8")
    for uid, status, title in ((MARKABLE, "approved", "Lock out after ten failures"),
                               (UNMARKABLE, "proposed", "Alert on a burst of failures")):
        (root / "requirements" / f"{uid}.yml").write_text(
            f"uid: {uid}\ntype: requirement\nstatus: {status}\ntitle: {title}\n"
            f"text: Body of {uid}.\nnormative: true\n"
            f"links:\n- target: {RISK}\n  type: mitigates\n",
            encoding="utf-8")


@pytest.fixture
def deletion(demo_project: Path) -> Path:
    _propose_deletion(demo_project)
    return demo_project


def _rows(root: Path, **kw) -> dict[str, core.QueueItem]:
    return {r.uid: r for r in core.build_queue(core.open_session(root), **kw)}


def _on_disk(root: Path, folder: str, uid: str) -> dict:
    return yaml.safe_load((root / folder / f"{uid}.yml").read_text(encoding="utf-8"))


def _pane(root: Path, uid: str, width: int = 90) -> list[str]:
    session = core.open_session(root)
    row = {r.uid: r for r in core.build_queue(session)}[uid]
    app = tui.App(None, session, "Ada Lovelace", None)
    return [text for text, _attr in app._detail_lines(row, width)]


# ------------------------------------------------------------- the worklist row

def test_a_proposed_deletion_is_in_the_backlog_as_a_deletion(deletion):
    """The Tool lists an unsigned tombstone as proposed (tl:SR-0267); the row
    carries that it is a deletion and what ratifying it reaches (SR-0084)."""
    row = _rows(deletion)[RISK]
    assert row.concern == "proposed" and row.status == "deleted"
    assert row.deletion and row.ratifiable_now
    assert row.dependents == (MARKABLE, UNMARKABLE)
    assert row.ratified_by == "alice"


def test_a_tombstone_that_stands_is_dead_not_a_deletion(demo_project):
    """The fixture's retired tombstone is what it always was: hidden, dead, and
    not offered — only a tombstone awaiting its signature is a deletion."""
    assert "FR-0009" not in _rows(demo_project)
    row = _rows(demo_project, show_all=True)["FR-0009"]
    assert row.concern == "deleted" and not row.deletion and not row.ratifiable_now


def test_the_list_row_and_the_printed_list_say_deletion(deletion, monkeypatch, capsys):
    session = core.open_session(deletion)
    app = tui.App(_Screen(), session, "Ada Lovelace", None)
    app.sel = [r.uid for r in app.rows].index(RISK)
    app._draw_list(0, 20, 120)
    painted = app.scr.painted()
    assert f"{RISK}" in painted
    assert "☠ deletion: Credential stuffing" in painted

    cli.main(["-C", str(deletion), "--list"])
    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if RISK in ln)
    assert "[deleted   ]" in line and "deletion" in line and "ratify-ready" not in line


# --------------------------------------------------------------- the detail pane

def test_the_pane_shows_the_deletion_record_as_the_tool_renders_it(deletion):
    """What the signature is taken over is the record (tl:SR-0269), so the pane
    shows the record in the Tool's own lines and not the item's wording as content
    (SR-0083)."""
    lines = _pane(deletion, RISK)
    text = "\n".join(lines)
    assert "proposed deletion" in lines[0]
    assert f"DELETION of {RISK}  [risk/was ratified] Credential stuffing" in text
    assert "reason: folded into RISK-0001" in text
    assert "date:   2026-10-26" in text
    assert f"content retired: {RETIRED_FINGERPRINT}" in text
    assert "this deletion undoes the acceptance of: alice" in text
    assert "ratifying it marks 2 dependent(s) suspect:" in text
    assert f"{MARKABLE}  [requirement/approved] Lock out after ten failures" in text
    assert f"{UNMARKABLE}  [requirement/proposed] Alert on a burst of failures" in text
    assert "the item said:" in text and f"Body of {RISK}." in text
    # The readiness line says what pressing r does, and the content headings a
    # live item gets are not drawn: nothing here is signed as wording.
    assert any("press r to ratify the deletion as Ada Lovelace" in ln for ln in lines)
    assert any("retires it and marks 2 dependent(s) suspect" in ln for ln in lines)
    assert "text" not in lines and "rationale" not in lines
    assert not any(ln.startswith("  grounded:") for ln in lines)


def test_the_pane_says_when_nothing_is_grounded_on_the_deletion(deletion):
    for uid in (MARKABLE, UNMARKABLE):
        (deletion / "requirements" / f"{uid}.yml").unlink()
    lines = _pane(deletion, RISK)
    assert any("retires it; nothing is grounded on it" in ln for ln in lines)
    assert any("marks no dependent suspect" in ln for ln in lines)


# ------------------------------------------------------------- signing it (core)

def test_ratifying_a_deletion_writes_the_dependents_the_cascade_marked(deletion):
    """The Tool marks; the cockpit receives the cascade and writes what moved
    (SR-0082). Without the writer the Tool refuses, so this is also the proof the
    cockpit no longer fails on a tombstone with dependents."""
    session = core.open_session(deletion)
    signing = core.ratify_item(session, RISK, by="Ada Lovelace")
    assert signing.retired
    assert signing.marked == [MARKABLE]
    assert [(r.uid, r.frm, r.to) for r in signing.refused] == [
        (UNMARKABLE, "proposed", "suspect")]

    marked = _on_disk(deletion, "requirements", MARKABLE)
    assert marked["status"] == "suspect"
    assert marked["attrs"]["suspect_reasons"] == [f"upstream {RISK} deleted"]
    assert _on_disk(deletion, "requirements", UNMARKABLE)["status"] == "proposed"

    tombstone = _on_disk(deletion, "risks", RISK)
    assert tombstone["status"] == "deleted"
    signature = tombstone["ratifications"][-1]
    assert signature["by"] == "Ada Lovelace"
    assert signature["content"] == {"deleted": tombstone["deleted"]}

    fresh = _rows(deletion, show_all=True)
    assert fresh[RISK].concern == "deleted" and not fresh[RISK].deletion
    assert fresh[MARKABLE].status == "suspect"


def test_a_signature_over_wording_marks_nothing(deletion):
    signing = core.ratify_item(core.open_session(deletion), "FR-0001", by="Ada Lovelace")
    assert not signing.retired and signing.marked == [] and signing.refused == []


def test_a_deletion_short_of_its_requirement_is_signed_but_retires_nothing(deletion):
    """Where the kind requires two signatures (tl:SR-0260) the first leaves the
    tombstone proposed, so no dependent is touched yet."""
    cfg = deletion / "throughline.toml"
    cfg.write_text(cfg.read_text(encoding="utf-8")
                   + "\n[types.risk]\n"
                   + '\n[ratify.roles]\nsenior = ["github:ada"]\n'
                   + "\n[ratify.requires.risk]\nsignatures = 2\n", encoding="utf-8")
    signing = core.ratify_item(core.open_session(deletion), RISK, by="Ada Lovelace",
                               by_id="github:ada", role="senior")
    assert not signing.retired and signing.marked == [] and signing.refused == []
    assert _on_disk(deletion, "requirements", MARKABLE)["status"] == "approved"
    row = _rows(deletion)[RISK]
    assert row.concern == "awaiting" and row.deletion


# ---------------------------------------------------------- signing it (cockpit)

class _Screen:
    """Enough of a curses window for the list and a confirmation to draw on."""

    def __init__(self, keys=(), height=24, width=120):
        self.h, self.w = height, width
        self.keys = list(keys)
        self.rows: dict[int, str] = {}

    def getmaxyx(self):
        return self.h, self.w

    def addstr(self, y, x, text, attr=0):
        row = self.rows.get(y, "").ljust(x)
        self.rows[y] = (row[:x] + text + row[x + len(text):]).rstrip()

    def erase(self):
        self.rows.clear()

    def getch(self):
        return self.keys.pop(0)

    def noutrefresh(self):
        pass

    def painted(self) -> str:
        return "\n".join(self.rows[y] for y in sorted(self.rows))


def _cockpit_on(root: Path, uid: str, monkeypatch, answer: bool = True):
    """The cockpit with the row selected and the confirmation scripted; returns
    the app and the questions it asked, each with the detail shown above it."""
    asked: list[tuple[str, list[str] | None]] = []

    def confirm(self, question, detail=None):
        asked.append((question, detail))
        return answer

    monkeypatch.setattr(tui.App, "_confirm", confirm)
    log = report.DecisionLog("Ada Lovelace")
    app = tui.App(_Screen(), core.open_session(root), "Ada Lovelace", log)
    app.sel = [r.uid for r in app.rows].index(uid)
    return app, asked


def test_the_confirmation_names_the_deletion_and_its_dependents(deletion, monkeypatch):
    """The question states what the signature is over and what it does, as the
    cockpit has established it (SR-0084, SR-0025)."""
    app, asked = _cockpit_on(deletion, RISK, monkeypatch, answer=False)
    app.do_ratify()
    (question, detail), = asked
    assert question == ("Ratify the deletion of RISK-0002 as Ada Lovelace? "
                        "The item is retired.")
    assert detail == ["2 dependent(s) become suspect:", f"{MARKABLE}, {UNMARKABLE}"]
    assert app.flash.text == "ratify cancelled"
    assert _on_disk(deletion, "risks", RISK).get("ratifications") is None


def test_ratifying_from_the_cockpit_reports_what_was_marked_and_what_was_refused(
        deletion, monkeypatch):
    """What the flash and the sitting's account say is what happened (SR-0082):
    retired, one dependent suspect, one the lifecycle refused — named, not
    dropped (SR-0037)."""
    app, _asked = _cockpit_on(deletion, RISK, monkeypatch)
    app.do_ratify()
    assert app.flash.text == (f"☠ {RISK} deletion ratified by Ada Lovelace "
                              f"— retired; 1 dependent(s) now suspect; "
                              f"1 left unflagged: {UNMARKABLE}")
    assert _on_disk(deletion, "requirements", MARKABLE)["status"] == "suspect"
    assert RISK not in {r.uid for r in app.rows}          # settled: off the backlog
    assert {r.uid: r.status for r in app.rows}[MARKABLE] == "suspect"

    (decision,) = app.log.decisions
    assert decision.kind == report.RETIRED and decision.uid == RISK
    assert decision.suspected == (MARKABLE,)
    assert decision.refused == ((UNMARKABLE, "proposed", "suspect"),)
    rendered = report.render(app.log, project_name="Ratifier Fixture", composed=False)
    assert f"retired      {RISK}" in rendered
    assert "deletion ratified" in rendered
    assert f"dependents made suspect: {MARKABLE}" in rendered
    assert f"left unflagged, no route to suspect: {UNMARKABLE} (proposed -> suspect)" in rendered
    assert "Tally: 1 retired" in rendered


def test_a_confirmation_for_wording_shows_no_dependents(deletion, monkeypatch):
    app, asked = _cockpit_on(deletion, "FR-0001", monkeypatch, answer=False)
    app.do_ratify()
    (question, detail), = asked
    assert question == "Ratify FR-0001 as Ada Lovelace?" and detail is None
