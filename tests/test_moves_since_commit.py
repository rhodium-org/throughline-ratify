# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0097 — no status move is written that the project's transitions forbid from
the last commit.

tl check judges a status against the last commit; throughline's set_status judges
each move against the status in memory. Two permitted moves in one sitting can
therefore add up to a forbidden one. On 7 November 2026 tl-ratify 0.18.0 moved
throughline's SR-0008 and SR-0105 deferred -> proposed -> ratified in one sitting,
and tl check --strict reported deferred -> ratified. These tests commit the
fixture graph, make one permitted move, and show that the second, which would add
up to a forbidden one, writes nothing.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from throughline_ratify import core, report, tui

from test_drafts import DRAFT, _Screen, _add_draft, _no_curses, _rewrite  # noqa: F401

VERIFIED = "FR-0013"

# The fixture's lifecycle, with a verified status that may not be rejected
# directly, as throughline's own graph has it.
WITH_VERIFIED = (
    'implemented = ["verified", "suspect", "rejected", "deleted"]\n'
    '    verified    = ["implemented", "suspect", "deleted"]'
)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout


def _commit(root: Path) -> Path:
    if not (root / ".git").exists():
        _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "c")
    return root


def _on_disk(root: Path, uid: str) -> dict:
    return yaml.safe_load((root / "requirements" / f"{uid}.yml").read_text())


def _with_verified(root: Path) -> Path:
    """A signed, verified item grounded on INT-0001, so rejecting the intent makes
    it suspect, and rejecting it then would add up to verified -> rejected."""
    _rewrite(root, lambda t: t.replace(
        'implemented = ["verified", "suspect", "rejected", "deleted"]', WITH_VERIFIED))
    (root / "requirements" / f"{VERIFIED}.yml").write_text(
        f"uid: {VERIFIED}\ntype: requirement\nstatus: verified\ntitle: Checked\n"
        f"text: Body of {VERIFIED}.\nnormative: true\n"
        "attrs:\n  ratified_by: alice\n"
        "links:\n- target: INT-0001\n  type: derives_from\n",
        encoding="utf-8")
    return root


def _cockpit_on(root: Path, uid: str, monkeypatch):
    asked: list[str] = []

    def confirm(self, question, detail=None):
        asked.append(question)
        return True

    monkeypatch.setattr(tui.App, "_confirm", confirm)
    monkeypatch.setattr(tui.App, "_prompt", lambda self, *a, **k: "a reason")
    app = tui.App(_Screen(), core.open_session(root), "Ada Lovelace",
                  report.DecisionLog("Ada Lovelace"))
    app.sel = [r.uid for r in app.rows].index(uid)
    return app, asked


def test_a_rejection_that_would_net_a_forbidden_move_writes_nothing(demo_project):
    root = _commit(_with_verified(demo_project))
    core.reject_item(core.open_session(root), "INT-0001", "withdrawn")
    assert _on_disk(root, VERIFIED)["status"] == "suspect"     # verified -> suspect: permitted
    before = _on_disk(root, VERIFIED)
    with pytest.raises(core.RatifierError) as refused:
        core.reject_item(core.open_session(root), VERIFIED, "gone")
    assert str(refused.value) == (
        f"nothing written: {VERIFIED} was 'verified' at the last commit, and "
        "'verified' -> 'rejected' is not a move this project's transitions permit; "
        f"commit this sitting's work, then reject {VERIFIED} again")
    assert _on_disk(root, VERIFIED) == before
    _commit(root)                                    # suspect is now where it stood
    core.reject_item(core.open_session(root), VERIFIED, "gone")
    assert _on_disk(root, VERIFIED)["status"] == "rejected"


def test_a_cascade_that_would_net_a_forbidden_move_writes_nothing(demo_project):
    """Agreeing a draft is permitted; a rejection that then marks it suspect would
    add up to draft -> suspect, which the fixture's draft row does not allow. The
    item named is the dependent, not the one rejected."""
    root = _commit(_add_draft(demo_project))
    core.agree_item(core.open_session(root), DRAFT)
    session = core.open_session(root)
    (found,) = [f for f in core.forbidden_moves(session, "INT-0001", core.REJECT)]
    assert (found.uid, found.was, found.to) == (DRAFT, "draft", "suspect")
    with pytest.raises(core.RatifierError, match=f"{DRAFT} was 'draft'"):
        core.reject_item(session, "INT-0001", "withdrawn")
    assert yaml.safe_load((root / "intents" / "INT-0001.yml").read_text())["status"] \
        == "ratified"
    assert _on_disk(root, DRAFT)["status"] == "approved"


def test_signing_a_draft_agreed_this_sitting_writes_nothing(demo_project):
    """The hitl-hci shape: p agrees draft -> approved, and r would sign it to
    ratified, adding up to draft -> ratified."""
    root = _commit(_add_draft(demo_project))
    core.agree_item(core.open_session(root), DRAFT)
    with pytest.raises(core.RatifierError, match="'draft' -> 'ratified'"):
        core.ratify_item(core.open_session(root), DRAFT, by="tester")
    item = _on_disk(root, DRAFT)
    assert item["status"] == "approved" and "ratifications" not in item


def test_a_permitted_move_is_written_and_judged_from_the_commit(demo_project):
    root = _commit(_add_draft(demo_project))
    assert core.forbidden_moves(core.open_session(root), DRAFT, core.AGREE) == []
    core.agree_item(core.open_session(root), DRAFT)
    _commit(root)
    core.ratify_item(core.open_session(root), DRAFT, by="tester")
    item = _on_disk(root, DRAFT)
    assert item["status"] == "ratified" and item["ratifications"][-1]["by"] == "tester"
    # An item new since the commit was created, not moved: nothing to judge.
    (root / "requirements" / "FR-0014.yml").write_text(
        (root / "requirements" / f"{DRAFT}.yml").read_text().replace(DRAFT, "FR-0014")
        .replace("status: ratified", "status: draft"), encoding="utf-8")
    core.agree_item(core.open_session(root), "FR-0014")


def test_without_a_commit_nothing_is_judged(demo_project):
    root = _add_draft(demo_project)
    core.agree_item(core.open_session(root), DRAFT)
    core.ratify_item(core.open_session(root), DRAFT, by="tester")
    assert _on_disk(root, DRAFT)["status"] == "ratified"


def test_the_cockpit_refuses_before_asking(demo_project, monkeypatch):
    root = _commit(_add_draft(_with_verified(demo_project)))
    app, asked = _cockpit_on(root, DRAFT, monkeypatch)
    app.handle(ord("p"))
    app.refresh_queue()
    app.sel = [r.uid for r in app.rows].index(DRAFT)
    app.do_ratify()
    assert asked == []
    assert app.flash.text.startswith(f"nothing written: {DRAFT} was 'draft'")
    assert "ratifications" not in _on_disk(root, DRAFT)

    _commit(root)                  # the agreed draft would block the cascade below
    core.reject_item(core.open_session(root), "INT-0001", "withdrawn")
    app, asked = _cockpit_on(root, VERIFIED, monkeypatch)
    app.do_reject()
    assert asked == []
    assert app.flash.text.startswith(f"nothing written: {VERIFIED} was 'verified'")
    assert _on_disk(root, VERIFIED)["status"] == "suspect"
