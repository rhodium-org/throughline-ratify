# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0085, SR-0086 — an item not yet proposed is put forward with p, never
signed by r, and the cockpit says it is not yet proposed rather than blocked.

Found on the plan standard's conformance example: seventeen items at the initial
status, below proposed, were offered only the overshoot round trip of SR-0019.
Under that project's transitions it walked draft, suspect, ratified and back to
draft, so each item ended where it began carrying a signature. Proposing and
signing are two acts, as table.iddn.uk keeps them (table REQ-0214). These tests
put an item at the initial status into the fixture graph and into one governed by
the plan standard's own transitions, and check what p and r do and what is drawn.
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
    """The fixture graph, with the move from draft to proposed it lacks."""
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


# ------------------------------------------------------------------ SR-0085

def test_an_item_before_ratified_can_be_put_forward(draft):
    """The fixture's draft cannot move to ratified, and may move to proposed:
    table's putForwardTo would offer Put forward, and so does the row."""
    row = _rows(draft)[DRAFT]
    assert row.concern == "blocked" and not row.ratifiable_now
    assert row.put_forward_to == "proposed" and row.not_yet_proposed
    assert row.reratify_path is None                    # no round trip, no carry


def test_p_puts_it_forward_and_takes_no_signature(draft, monkeypatch):
    app, asked = _cockpit_on(draft, DRAFT, monkeypatch)
    app.handle(ord("p"))
    assert asked == []                                  # a status move, not a decision to confirm
    item = _on_disk(draft, DRAFT)
    assert item["status"] == "proposed"
    assert "ratifications" not in item
    assert app.flash.text == f"\u25cf {DRAFT} put forward: draft \u2192 proposed"
    (decision,) = app.log.decisions
    assert decision.kind == report.PUT_FORWARD and decision.route == ("draft", "proposed")
    row = _rows(draft)[DRAFT]
    assert row.concern == "proposed" and row.ratifiable_now   # r signs it now


def test_r_on_an_item_not_yet_proposed_refuses_and_names_p(draft, monkeypatch):
    app, asked = _cockpit_on(draft, DRAFT, monkeypatch)
    app.do_ratify()
    assert asked == []
    assert app.flash.text == (f"{DRAFT} is at 'draft' and not yet proposed \u2014 press p "
                              "to put it forward to 'proposed', then r to sign it")
    item = _on_disk(draft, DRAFT)
    assert item["status"] == "draft" and "ratifications" not in item
    with pytest.raises(core.RatifierError, match="no route"):
        core.reratify_item(core.open_session(draft), DRAFT, by="tester")
    assert "ratifications" not in _on_disk(draft, DRAFT)


def test_the_plan_standard_lifecycle_puts_draft_forward(plan):
    """The reported case: the old round trip ran draft, suspect, ratified, suspect,
    approved, deferred, draft. Now p proposes and r signs, two acts."""
    row = _rows(plan)[DRAFT]
    assert row.reratify_path is None and row.put_forward_to == "proposed"
    session = core.open_session(plan)
    assert core.put_forward(session, DRAFT) == "proposed"
    core.ratify_item(core.open_session(plan), DRAFT, by="tester")
    item = _on_disk(plan, DRAFT)
    assert item["status"] == "ratified"
    assert item["ratifications"][-1]["by"] == "tester"


@pytest.mark.parametrize("graph", ["draft", "plan"])
def test_an_overshot_item_still_takes_the_round_trip(graph, request):
    """An item past ratified keeps the route of SR-0019 and its own status, and
    is never offered p."""
    root = request.getfixturevalue(graph)
    row = _rows(root)[OVERSHOT]
    assert row.reratify_path[0] == row.reratify_path[-1] == "implemented"
    assert "ratified" in row.reratify_path
    assert not row.not_yet_proposed
    core.reratify_item(core.open_session(root), OVERSHOT, by="tester")
    assert _on_disk(root, OVERSHOT)["status"] == "implemented"


def test_p_refuses_an_item_that_cannot_be_put_forward(draft, monkeypatch):
    """Signable as it stands (proposed, approved), past ratified, or with no move
    to proposed: p offers nothing and writes nothing."""
    for uid in ("FR-0001", "FR-0002", OVERSHOT):
        before = _on_disk(draft, uid)
        app, _ = _cockpit_on(draft, uid, monkeypatch)
        app.handle(ord("p"))
        assert app.flash.text == f"{uid} has nothing to put forward"
        assert _on_disk(draft, uid) == before
        with pytest.raises(core.RatifierError, match="cannot be put forward"):
            core.put_forward(core.open_session(draft), uid)


def test_a_draft_with_no_move_to_proposed_is_not_offered_p(demo_project):
    _add_draft(demo_project)
    row = _rows(demo_project)[DRAFT]
    assert row.put_forward_to is None and not row.not_yet_proposed
    with pytest.raises(core.RatifierError, match="cannot be put forward"):
        core.put_forward(core.open_session(demo_project), DRAFT)


def test_no_suspect_role_offers_no_round_trip(draft):
    """Without a suspect role forward cannot be told from back, and on the plan
    standard's transitions the old round trip is the walk that went wrong. Put
    forward needs only the proposed role, so it is still offered."""
    _rewrite(draft, lambda t: t.replace('suspect = "suspect"\n', ""))
    rows = _rows(draft)
    assert rows[OVERSHOT].reratify_path is None
    assert rows[DRAFT].put_forward_to == "proposed"


# ------------------------------------------------------------------ SR-0086

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


def test_the_row_and_the_printed_list_say_not_yet_proposed(draft, capsys):
    app = tui.App(_Screen(), core.open_session(draft), "Ada Lovelace", None)
    app._draw_list(0, 20, 120)
    painted = app.scr.painted()
    assert f"\u25cc {DRAFT}" in painted
    assert f"\u25cb {OVERSHOT}" in painted

    cli.main(["-C", str(draft), "--list"])
    lines = capsys.readouterr().out.splitlines()
    mine = next(ln for ln in lines if DRAFT in ln)
    assert "\u25cc" in mine and "not-yet-proposed" in mine and "blocked" not in mine
    other = next(ln for ln in lines if OVERSHOT in ln)
    assert "\u25cb" in other and "blocked" in other


def test_the_summary_counts_not_yet_proposed_apart_from_blocked(draft):
    app = tui.App(_Screen(), core.open_session(draft), "Ada Lovelace", None)
    app._draw_summary(200)
    summary = app.scr.painted()
    assert "\u25cc 1 not yet proposed" in summary
    assert "\u25cb 1 blocked" in summary


def test_the_pane_names_p(draft, monkeypatch):
    app, _ = _cockpit_on(draft, DRAFT, monkeypatch)
    lines = [text for text, _ in app._detail_lines(app.rows[app.sel], 120)]
    assert lines[0] == f"\u25cc {DRAFT}  not yet proposed"
    assert "  \u25cc not yet proposed \u2014 at 'draft'" in lines
    assert "  \u25cf press p to put it forward to 'proposed'" in lines
    assert not any("press r" in ln for ln in lines)


def test_the_help_tells_not_yet_proposed_from_blocked(draft):
    scr = Keys(90, 80, [ord("q")])
    tui.App(scr, core.open_session(draft), "Ada Lovelace", None).show_help()
    text = scr.frames[0]
    assert "  p            put the selected item forward to proposed" in text
    assert "\u25cc not yet proposed" in text
    assert "p puts it forward, then r signs it" in text
    assert "\u25cb blocked" in text
    assert "leaves its status as it" in text
