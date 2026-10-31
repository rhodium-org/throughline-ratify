# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0085, SR-0086 — an item not yet proposed is carried forward to ratified,
and the cockpit says it is not yet proposed rather than blocked.

Found on the plan standard's conformance example: seventeen items at the initial
status, below proposed, were offered only the overshoot round trip of SR-0019.
Under that project's transitions it walked draft, suspect, ratified and back to
draft, so each item ended where it began carrying a signature. These tests put an
item at the initial status into the fixture graph and into one governed by the
plan standard's own transitions, and check the route, what is written and what is
drawn.
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

def test_an_item_before_ratified_is_carried_forward_not_round_tripped(draft):
    """The fixture's draft reaches ratified only through approved, and nothing
    moving forward from ratified reaches draft: the route ends on ratified."""
    row = _rows(draft)[DRAFT]
    assert row.concern == "blocked" and not row.ratifiable_now
    assert row.reratify_path == ["draft", "approved", "ratified"]
    assert row.not_yet_proposed


def test_carrying_it_forward_signs_it_and_leaves_it_at_ratified(draft):
    walked = core.reratify_item(core.open_session(draft), DRAFT, by="tester")
    assert walked == ["draft", "approved", "ratified"]
    item = _on_disk(draft, DRAFT)
    assert item["status"] == "ratified"
    assert item["ratifications"][-1]["by"] == "tester"
    assert DRAFT not in _rows(draft)
    assert _rows(draft, show_all=True)[DRAFT].concern == "ratified"


def test_the_plan_standard_lifecycle_carries_draft_through_proposed(plan):
    """The reported case. The old round trip here was draft, suspect, ratified,
    suspect, approved, deferred, draft; the carry goes through proposal."""
    row = _rows(plan)[DRAFT]
    assert row.reratify_path == ["draft", "proposed", "ratified"]
    core.reratify_item(core.open_session(plan), DRAFT, by="tester")
    item = _on_disk(plan, DRAFT)
    assert item["status"] == "ratified"
    assert item["ratifications"][-1]["by"] == "tester"


def test_the_carry_never_walks_through_suspect(demo_project):
    """Draft reaches ratified in two moves through suspect, and in three without
    it. Walking an item through suspect records a withdrawal that never happened."""
    _rewrite(demo_project, lambda t: t.replace(
        'draft       = ["approved", "rejected", "deleted"]',
        'draft       = ["suspect", "approved", "rejected", "deleted"]').replace(
        'approved    = ["ratified", "implemented", "suspect", "rejected", "deleted"]',
        'approved    = ["proposed", "suspect", "rejected", "deleted"]'))
    _add_draft(demo_project)
    row = _rows(demo_project)[DRAFT]
    assert row.reratify_path == ["draft", "approved", "proposed", "ratified"]
    assert "suspect" not in row.reratify_path


@pytest.mark.parametrize("graph", ["draft", "plan"])
def test_an_overshot_item_still_takes_the_round_trip(graph, request):
    """An item past ratified keeps the route of SR-0019 and its own status."""
    root = request.getfixturevalue(graph)
    row = _rows(root)[OVERSHOT]
    assert row.reratify_path[0] == row.reratify_path[-1] == "implemented"
    assert "ratified" in row.reratify_path
    assert not row.not_yet_proposed
    core.reratify_item(core.open_session(root), OVERSHOT, by="tester")
    assert _on_disk(root, OVERSHOT)["status"] == "implemented"


def test_no_suspect_role_offers_no_carry(draft):
    """Without a suspect role forward cannot be told from back, and on the plan
    standard's transitions the old round trip is the walk that went wrong."""
    _rewrite(draft, lambda t: t.replace('suspect = "suspect"\n', ""))
    rows = _rows(draft)
    assert rows[DRAFT].reratify_path is None
    assert rows[OVERSHOT].reratify_path is None
    with pytest.raises(core.RatifierError, match="no route"):
        core.reratify_item(core.open_session(draft), DRAFT, by="tester")


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
    assert f"◌ {DRAFT}" in painted
    assert f"○ {OVERSHOT}" in painted

    cli.main(["-C", str(draft), "--list"])
    lines = capsys.readouterr().out.splitlines()
    mine = next(ln for ln in lines if DRAFT in ln)
    assert "◌" in mine and "not-yet-proposed" in mine and "blocked" not in mine
    other = next(ln for ln in lines if OVERSHOT in ln)
    assert "○" in other and "blocked" in other


def test_the_summary_counts_not_yet_proposed_apart_from_blocked(draft):
    app = tui.App(_Screen(), core.open_session(draft), "Ada Lovelace", None)
    app._draw_summary(200)
    summary = app.scr.painted()
    assert "◌ 1 not yet proposed" in summary
    assert "○ 1 blocked" in summary


def test_the_pane_and_the_confirmation_name_the_carry(draft, monkeypatch):
    app, asked = _cockpit_on(draft, DRAFT, monkeypatch, answer=False)
    row = app.rows[app.sel]
    lines = [text for text, _ in app._detail_lines(row, 120)]
    assert lines[0] == f"◌ {DRAFT}  not yet proposed"
    assert "  ◌ not yet proposed — at 'draft'" in lines
    assert ("  ↺ press r to sign it and carry it to ratified via "
            "draft → approved → ratified") in lines

    app.do_ratify()
    assert asked == [f"{DRAFT} is at 'draft' and not yet proposed. Sign it as "
                     "Ada Lovelace and carry it to ratified via "
                     "draft → approved → ratified?"]
    assert "ratifications" not in _on_disk(draft, DRAFT)

    app, _ = _cockpit_on(draft, DRAFT, monkeypatch, answer=True)
    app.do_ratify()
    assert _on_disk(draft, DRAFT)["status"] == "ratified"
    assert app.flash.text.startswith(f"✓ {DRAFT} ratified by Ada Lovelace")


def test_the_help_tells_not_yet_proposed_from_blocked(draft):
    scr = Keys(80, 80, [ord("q")])
    tui.App(scr, core.open_session(draft), "Ada Lovelace", None).show_help()
    text = scr.frames[0]
    assert "◌ not yet proposed" in text
    assert "○ blocked" in text
    assert "item not yet proposed, sign it and carry it forward to" in text
    assert "leaves its status as it was" in text
