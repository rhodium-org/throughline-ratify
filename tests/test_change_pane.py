# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0053 — the cockpit shows what moved since the signature, and says when it cannot.

SR-0030 made a stale signature visible and stopped the cockpit reporting full marks
over one. It did not make the change legible: the reviewer was told the words they
accepted had been rewritten and had to leave the cockpit to find out what moved.

What counts as a change is throughline's judgement, resolved against the stamp
(tl:SR-0165). These tests hold the layout to that answer and check that nothing
about the comparison is decided here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from throughline.ratification import FieldChange, RatificationChange

from throughline_ratify import core, tui


@pytest.fixture(autouse=True)
def _no_curses(monkeypatch):
    """The pane is built without a terminal; only the text it lays out is tested."""
    monkeypatch.setattr(tui, "_attr", lambda name, bold=False: 0)


def _item(**kw) -> core.QueueItem:
    fields = dict(
        uid="FR-0001", title="A title", type="requirement", status="ratified",
        concern="stale", grounded=True, ambiguous=False, ratifiable_now=True,
        text="The wording as it now stands.", rationale="", links=[], depth=1,
        stale=True, ratified_by="Ada Lovelace",
    )
    fields.update(kw)
    return core.QueueItem(**fields)


def _pane(item, session, width: int = 72) -> list[str]:
    app = tui.App(None, session, "Ada Lovelace", None)
    return [text for text, _a in app._detail_lines(item, width)]


def _answer(monkeypatch, change):
    """Make the library return ``change``, so the pane is tested against throughline's
    answer rather than against a second comparison of its own."""
    monkeypatch.setattr(tui, "change_since_signature", lambda _s, _uid: change)


# --------------------------------------------------------------------------- #
# Laying out a resolved difference
# --------------------------------------------------------------------------- #

def test_the_changed_fields_are_shown_with_both_values(demo_project, monkeypatch):
    """The value as signed beside the value as it stands, per field (SR-0053)."""
    _answer(monkeypatch, RatificationChange(
        uid="FR-0001", outcome="changed", stamp="sha256:abc",
        revision="c0ffee1234567890" + "0" * 24,
        changes=(FieldChange("text", "Sixty minutes.", "Fifteen minutes."),
                 FieldChange("attrs.priority", "should", "must"))))
    joined = "\n".join(_pane(_item(), core.open_session(demo_project)))

    assert "what changed since the signature" in joined
    assert "text" in joined
    assert "was: Sixty minutes." in joined
    assert "now: Fifteen minutes." in joined
    assert "attrs.priority" in joined
    assert "was: should" in joined and "now: must" in joined


def test_the_revision_the_signed_content_came_from_is_named(demo_project, monkeypatch):
    """A reviewer who doubts what they are shown needs a handle they can go and
    look at, and it is throughline's answer reproduced, not a date inferred here."""
    _answer(monkeypatch, RatificationChange(
        uid="FR-0001", outcome="changed", stamp="sha256:abc",
        revision="c0ffee123" + "0" * 31,
        changes=(FieldChange("text", "was", "now"),)))
    joined = "\n".join(_pane(_item(), core.open_session(demo_project)))
    assert "c0ffee123" in joined


def test_the_change_is_shown_above_the_wording_it_no_longer_covers(
        demo_project, monkeypatch):
    """The reviewer has just been told the signature no longer covers what follows;
    the answer to that belongs before the wording, not after it."""
    _answer(monkeypatch, RatificationChange(
        uid="FR-0001", outcome="changed", stamp="sha256:abc", revision="a" * 40,
        changes=(FieldChange("text", "old wording", "new wording"),)))
    lines = _pane(_item(), core.open_session(demo_project))
    changed_at = next(i for i, l in enumerate(lines) if "what changed since" in l)
    text_at = next(i for i, l in enumerate(lines) if l.strip() == "text")
    assert changed_at < text_at


def test_an_absent_value_reads_as_unset_not_as_none(demo_project, monkeypatch):
    """A normative attribute that was absent when the signature was given is a real
    and different thing from one holding the string 'None'."""
    _answer(monkeypatch, RatificationChange(
        uid="FR-0001", outcome="changed", stamp="sha256:abc", revision="b" * 40,
        changes=(FieldChange("attrs.priority", None, "must"),)))
    joined = "\n".join(_pane(_item(), core.open_session(demo_project)))
    assert "was: (unset)" in joined
    assert "None" not in joined


# --------------------------------------------------------------------------- #
# Unable to establish it is its own state
# --------------------------------------------------------------------------- #

def test_an_unresolvable_change_says_so_rather_than_showing_nothing(
        demo_project, monkeypatch):
    """An empty difference would assert the wording still stands as signed — the one
    reading that sends a reviewer past the change they are accepting (SR-0053)."""
    _answer(monkeypatch, RatificationChange(
        uid="FR-0001", outcome="unresolvable", stamp="sha256:abc",
        reason="the item has no committed history"))
    joined = "\n".join(_pane(_item(), core.open_session(demo_project)))
    assert "CANNOT BE ESTABLISHED" in joined
    assert "no committed history" in joined
    assert "nobody can state what you would be accepting" in joined
    assert "what changed since the signature" not in joined   # not both claims


def test_nothing_is_shown_for_an_item_whose_signature_still_stands(
        demo_project, monkeypatch):
    """The block belongs to a stale row only; a settled item has nothing to answer."""
    _answer(monkeypatch, RatificationChange(
        uid="FR-0001", outcome="unchanged", stamp="sha256:abc"))
    joined = "\n".join(_pane(_item(stale=False, concern="ratified"),
                             core.open_session(demo_project)))
    assert "what changed" not in joined
    assert "CANNOT BE ESTABLISHED" not in joined


def test_a_stale_row_the_library_reports_settled_renders_no_block(
        demo_project, monkeypatch):
    """The library's answer governs, not the row's flag — the two cannot be allowed
    to give different accounts of one item (SR-0030)."""
    _answer(monkeypatch, RatificationChange(uid="FR-0001", outcome="unchanged"))
    joined = "\n".join(_pane(_item(), core.open_session(demo_project)))
    assert "what changed" not in joined


# --------------------------------------------------------------------------- #
# The answer comes from throughline (SR-0022, SR-0030, tl:SR-0165)
# --------------------------------------------------------------------------- #

def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, check=True).stdout


def test_the_difference_is_resolved_by_throughline_and_memoised(
        demo_project, monkeypatch):
    """Resolution is asked of the library, and asked once per (item, stamp): a
    redraw must not pay the walk again, and re-signing must not be answered from the
    entry its old stamp left behind (tl:SR-0166)."""
    session = core.open_session(demo_project)
    item = next(iter(session.project.items()))
    item.attrs["ratified_fingerprint"] = "sha256:deadbeef"

    calls = []
    sentinel = RatificationChange(uid=item.uid, outcome="changed",
                                  stamp="sha256:deadbeef", revision="f" * 40,
                                  changes=(FieldChange("text", "a", "b"),))

    def _fake(project, it):
        calls.append(it.uid)
        return sentinel

    monkeypatch.setattr(core, "change_since_ratification", _fake)

    assert core.change_since_signature(session, item.uid) is sentinel
    assert core.change_since_signature(session, item.uid) is sentinel
    assert calls == [item.uid]                      # resolved once, not twice

    # A new stamp is a different question and must not reuse the old answer.
    item.attrs["ratified_fingerprint"] = "sha256:0ther"
    core.change_since_signature(session, item.uid)
    assert calls == [item.uid, item.uid]


def test_an_unknown_uid_resolves_to_nothing(demo_project):
    """A borrowed item is not local and has no local record to resolve against."""
    session = core.open_session(demo_project)
    assert core.change_since_signature(session, "tl:SR-9999") is None
