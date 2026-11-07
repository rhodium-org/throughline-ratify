# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0085, SR-0086, SR-0096 — a draft is agreed with p or deleted with D, never
signed by r; the queue lists only what needs a signature or that decision.

Since throughline 5.0 (throughline UR-0046) every item past the draft counts only
once a person signs it, an item past ratified is signed where it stands, and a
draft is neither signed nor counted. The queue therefore has no blocked rows and
no signed-but-unsettled ones: the operator's ruling on hitl-hci was that an item
is signed or tombstoned, with nothing in between. These tests put a draft into
the fixture graph and into one governed by the plan standard's transitions.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from throughline_ratify import cli, core, report, tui

from test_help_scrolls import Keys

DRAFT = "FR-0012"
OVERSHOT = "FR-0007"       # the fixture's item at 'implemented', never signed

# The plan standard's lifecycle (rhodium-org/throughline-plan-standard), where the
# initial status sits below proposed and reaches suspect directly.
PLAN_TRANSITIONS = """[transitions]
proposed    = ["draft", "approved", "ratified", "deferred", "suspect", "rejected", "deleted"]
draft       = ["proposed", "approved", "deferred", "suspect", "rejected", "deleted"]
deferred    = ["proposed", "draft", "approved", "suspect", "rejected", "deleted"]
approved    = ["ratified", "implemented", "deferred", "suspect", "rejected", "deleted"]
ratified    = ["implemented", "suspect", "rejected", "deleted"]
implemented = ["verified", "suspect", "rejected", "deleted"]
verified    = ["implemented", "suspect", "deleted"]
suspect     = ["approved", "ratified", "implemented", "verified", "rejected", "deleted"]
rejected    = ["draft", "deleted"]
"""


@pytest.fixture(autouse=True)
def _no_curses(monkeypatch):
    monkeypatch.setattr(tui, "_attr", lambda name, bold=False: 0)
    monkeypatch.setattr(tui, "_init_colours", lambda: None)
    monkeypatch.setattr(tui.curses, "curs_set", lambda n: None)
    monkeypatch.setattr(tui.curses, "doupdate", lambda: None)


def _add_draft(root: Path) -> Path:
    """A grounded, unambiguous item at the initial status that nobody has signed."""
    (root / "requirements" / f"{DRAFT}.yml").write_text(
        f"uid: {DRAFT}\ntype: requirement\nstatus: draft\ntitle: Export a report\n"
        f"text: Body of {DRAFT}.\nnormative: true\n"
        "links:\n- target: INT-0001\n  type: derives_from\n",
        encoding="utf-8")
    return root


def _rewrite(root: Path, edit) -> Path:
    cfg = root / "throughline.toml"
    cfg.write_text(edit(cfg.read_text(encoding="utf-8")), encoding="utf-8")
    return root


def _with_transitions(text: str, table: str) -> str:
    head, rest = text.split("[transitions]\n", 1)
    return head + table + "\n" + rest[rest.index("[status.roles]"):]


@pytest.fixture
def draft(demo_project: Path) -> Path:
    """The fixture graph, with a move from draft to proposed, so a draft is agreed
    to proposed rather than to approved."""
    _rewrite(demo_project, lambda t: t.replace(
        'draft       = ["approved", "rejected", "deleted"]',
        'draft       = ["proposed", "approved", "rejected", "deleted"]'))
    return _add_draft(demo_project)


@pytest.fixture
def plan(demo_project: Path) -> Path:
    _rewrite(demo_project, lambda t: _with_transitions(
        t.replace('"draft", "approved"', '"draft", "deferred", "approved"'),
        PLAN_TRANSITIONS))
    return _add_draft(demo_project)


def _rows(root: Path, **kw) -> dict[str, core.QueueItem]:
    return {r.uid: r for r in core.build_queue(core.open_session(root), **kw)}


def _on_disk(root: Path, uid: str) -> dict:
    return yaml.safe_load(
        (root / "requirements" / f"{uid}.yml").read_text(encoding="utf-8"))


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


def _cockpit_on(root: Path, uid: str, monkeypatch, answer: bool = True):
    asked: list[str] = []

    def confirm(self, question, detail=None):
        asked.append(question)
        return answer

    monkeypatch.setattr(tui.App, "_confirm", confirm)
    app = tui.App(_Screen(), core.open_session(root), "Ada Lovelace",
                  report.DecisionLog("Ada Lovelace"))
    app.sel = [r.uid for r in app.rows].index(uid)
    return app, asked



# ------------------------------------------------------------------ SR-0085

def test_a_draft_is_offered_agreement_not_a_signature(demo_project):
    """The hitl-hci case: under transitions where a draft moves to approved and not
    to proposed, the draft is agreed to approved, as throughline names it."""
    _add_draft(demo_project)
    row = _rows(demo_project)[DRAFT]
    assert row.concern == "draft" and row.draft and not row.ratifiable_now
    assert row.agree_to == "approved"
    assert "is a draft" in row.obstacle


def test_p_agrees_it_and_takes_no_signature(draft, monkeypatch):
    app, asked = _cockpit_on(draft, DRAFT, monkeypatch)
    app.handle(ord("p"))
    assert asked == []                                  # a status move, not a decision to confirm
    item = _on_disk(draft, DRAFT)
    assert item["status"] == "proposed"
    assert "ratifications" not in item
    assert app.flash.text == f"\u25cf {DRAFT} agreed: draft \u2192 proposed \u2014 r signs it"
    (decision,) = app.log.decisions
    assert decision.kind == report.AGREED and decision.route == ("draft", "proposed")
    row = _rows(draft)[DRAFT]
    assert row.concern == "proposed" and row.ratifiable_now   # r signs it now


def test_r_on_a_draft_refuses_in_throughlines_words(draft, monkeypatch):
    app, asked = _cockpit_on(draft, DRAFT, monkeypatch)
    app.do_ratify()
    assert asked == []
    assert app.flash.text.startswith(f"{DRAFT} is a draft, and a draft is neither "
                                     "signed nor counted")
    assert "tl delete" in app.flash.text
    item = _on_disk(draft, DRAFT)
    assert item["status"] == "draft" and "ratifications" not in item


def test_the_plan_standard_lifecycle_agrees_then_signs(plan):
    """Agreeing and signing are two acts, as table.iddn.uk keeps them."""
    assert _rows(plan)[DRAFT].agree_to == "proposed"
    assert core.agree_item(core.open_session(plan), DRAFT) == "proposed"
    core.ratify_item(core.open_session(plan), DRAFT, by="tester")
    item = _on_disk(plan, DRAFT)
    assert item["status"] == "ratified"
    assert item["ratifications"][-1]["by"] == "tester"


def test_p_refuses_what_is_no_draft(draft, monkeypatch):
    """Signable as it stands (proposed, approved, past ratified): p offers nothing
    and writes nothing."""
    for uid in ("FR-0001", "FR-0002", OVERSHOT):
        before = _on_disk(draft, uid)
        app, _ = _cockpit_on(draft, uid, monkeypatch)
        app.handle(ord("p"))
        assert app.flash.text == f"{uid} is no draft that can be agreed"
        assert _on_disk(draft, uid) == before
        with pytest.raises(core.RatifierError, match="cannot be agreed"):
            core.agree_item(core.open_session(draft), uid)


def test_a_draft_with_nowhere_to_go_can_only_be_deleted(demo_project, monkeypatch):
    _rewrite(demo_project, lambda t: t.replace(
        'draft       = ["approved", "rejected", "deleted"]',
        'draft       = ["rejected", "deleted"]'))
    _add_draft(demo_project)
    row = _rows(demo_project)[DRAFT]
    assert row.draft and row.agree_to is None
    app, _ = _cockpit_on(demo_project, DRAFT, monkeypatch)
    app.handle(ord("p"))
    assert app.flash.text == f"{DRAFT} is no draft that can be agreed \u2014 press D to delete it"
    assert _on_disk(demo_project, DRAFT)["status"] == "draft"


# ------------------------------------------------------------------ SR-0086

def test_the_row_and_the_printed_list_say_draft(draft, capsys):
    app = tui.App(_Screen(), core.open_session(draft), "Ada Lovelace", None)
    app._draw_list(0, 20, 120)
    painted = app.scr.painted()
    assert f"\u25cc {DRAFT}" in painted
    assert f"\u25c9 {OVERSHOT}" in painted            # ready: signed where it stands

    cli.main(["-C", str(draft), "--list"])
    lines = capsys.readouterr().out.splitlines()
    mine = next(ln for ln in lines if DRAFT in ln)
    assert "\u25cc" in mine and " draft " in mine
    other = next(ln for ln in lines if OVERSHOT in ln)
    assert "ratify-ready" in other and "blocked" not in other


def test_the_summary_counts_drafts(draft):
    app = tui.App(_Screen(), core.open_session(draft), "Ada Lovelace", None)
    app._draw_summary(200)
    summary = app.scr.painted()
    assert "\u25cc 1 draft" in summary
    assert "blocked" not in summary and "unsettled" not in summary


def test_the_pane_names_p_and_d(draft, monkeypatch):
    app, _ = _cockpit_on(draft, DRAFT, monkeypatch)
    lines = [text for text, _ in app._detail_lines(app.rows[app.sel], 120)]
    assert "  \u25cf press p to agree it (draft \u2192 proposed), then r to sign it" in lines
    assert "  \u2620 press D to delete it" in lines
    assert not any("press r to" in ln for ln in lines)


def test_d_deletes_a_draft_after_a_reason_and_a_confirmation(draft, monkeypatch):
    app, asked = _cockpit_on(draft, DRAFT, monkeypatch)
    monkeypatch.setattr(tui.App, "_prompt", lambda self, label, initial="": "not needed")
    app.handle(ord("D"))
    assert asked and asked[0].startswith(f"Delete draft {DRAFT}?")
    item = _on_disk(draft, DRAFT)
    assert item["status"] == "deleted"                  # retired outright: nobody signed it
    assert item["deleted"]["reason"] == "not needed"
    assert app.flash.text == f"\u2620 {DRAFT} deleted"
    (decision,) = app.log.decisions
    assert decision.kind == report.DRAFT_DELETED and decision.reason == "not needed"
    assert DRAFT not in _rows(draft)


def test_declining_d_writes_nothing(draft, monkeypatch):
    app, _ = _cockpit_on(draft, DRAFT, monkeypatch, answer=False)
    monkeypatch.setattr(tui.App, "_prompt", lambda self, label, initial="": "why")
    before = _on_disk(draft, DRAFT)
    app.handle(ord("D"))
    assert app.flash.text == "delete cancelled"
    assert _on_disk(draft, DRAFT) == before


def test_d_refuses_what_is_no_draft(draft, monkeypatch):
    for uid in ("FR-0001", OVERSHOT):
        before = _on_disk(draft, uid)
        app, asked = _cockpit_on(draft, uid, monkeypatch)
        app.handle(ord("D"))
        assert asked == [] and app.flash.text == f"{uid} is not a draft \u2014 x rejects it"
        assert _on_disk(draft, uid) == before
        with pytest.raises(core.RatifierError, match="not a draft"):
            core.delete_draft(core.open_session(draft), uid, reason="no")


def test_the_help_names_p_d_and_the_draft(draft):
    scr = Keys(90, 80, [ord("q")])
    tui.App(scr, core.open_session(draft), "Ada Lovelace", None).show_help()
    text = scr.frames[0]
    assert "  p            agree the selected draft" in text
    assert "  D            delete the selected draft" in text
    assert "\u25cc draft       neither signed nor counted" in text
    assert "blocked" not in text and "unsettled" not in text


# ------------------------------------------------------------------ SR-0096

def _sign_below_ratified(root: Path) -> None:
    """FR-0013: signed, at approved — a status short of ratified."""
    (root / "requirements" / "FR-0013.yml").write_text(
        "uid: FR-0013\ntype: requirement\nstatus: approved\ntitle: Signed early\n"
        "text: Body of FR-0013.\nnormative: true\nattrs:\n  ratified_by: alice\n"
        "links:\n- target: INT-0001\n  type: derives_from\n", encoding="utf-8")


def test_the_queue_holds_only_what_needs_a_signature_or_a_decision(draft):
    """No row is blocked; a signed item is settled whatever its status, and drops
    out of the queue; the progress figure counts it and leaves the draft out."""
    _sign_below_ratified(draft)
    session = core.open_session(draft)
    rows = {r.uid: r for r in core.build_queue(session)}
    assert "FR-0013" not in rows
    assert {r.concern for r in rows.values()} <= {
        "proposed", "ready", "awaiting", "stale", "ungrounded", "ambiguous", "draft"}
    assert "blocked" not in core.CONCERN_ICONS
    done, total = core.ratification_progress(session)
    gradable = [r for r in core.build_queue(session, show_all=True)
                if r.concern not in ("draft", "rejected", "deleted")]
    assert total == len(gradable)
    assert done == sum(1 for r in gradable if r.concern == "ratified")
