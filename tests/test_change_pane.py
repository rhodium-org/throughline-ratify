# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0053 / SR-0056 — the cockpit shows what moved since the signature, as a diff
for prose, and says when it cannot.

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
from throughline.ratification import HISTORY, RECORD, FieldChange, RatificationChange

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

def test_a_token_field_is_shown_as_was_and_now(demo_project, monkeypatch):
    """A value holding no whitespace — a priority, a flag — is the value as signed
    beside the value as it stands, on one line each (SR-0053, SR-0056)."""
    _answer(monkeypatch, RatificationChange(
        uid="FR-0001", outcome="changed", stamp="sha256:abc",
        revision="c0ffee1234567890" + "0" * 24,
        changes=(FieldChange("attrs.priority", "should", "must"),)))
    joined = "\n".join(_pane(_item(), core.open_session(demo_project)))

    assert "what changed since the signature" in joined
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
# A prose field is a diff, read from throughline (SR-0056, tl:SR-0200)
# --------------------------------------------------------------------------- #

PARAGRAPH = ("The Tool shall evict a cached widget after 3600 seconds. "
             "It shall record the eviction in the audit log with the widget's key. "
             "A widget evicted twice in one minute is a fault.")
REWORDED = PARAGRAPH.replace("after 3600 seconds", "when it is an hour old")


def _painted(item, session, width: int = 200) -> list[tuple[str, object]]:
    app = tui.App(None, session, "Ada Lovelace", None)
    return list(app._detail_lines(item, width))


def _runs(text: str, paint, flag: int) -> list[str]:
    """The runs of ``text`` drawn with ``flag`` set: the words that moved."""
    runs, cur, pos = [], "", 0
    for length, attr in paint:
        piece = text[pos:pos + length]
        pos += length
        if attr & flag:
            cur += piece
        elif cur:
            runs.append(cur)
            cur = ""
    if cur:
        runs.append(cur)
    return runs


def test_a_changed_paragraph_is_shown_sentence_by_sentence(demo_project, monkeypatch):
    """The removed sentence sits above its replacement inside the paragraph, the
    sentences that stayed are shown once and unmarked, and the paragraph is not
    quoted whole beside its predecessor (SR-0056)."""
    _answer(monkeypatch, RatificationChange(
        uid="FR-0001", outcome="changed", stamp="sha256:abc", revision="a" * 40,
        changes=(FieldChange("text", PARAGRAPH, REWORDED),)))
    lines = _pane(_item(), core.open_session(demo_project), width=200)
    joined = "\n".join(lines)

    assert "was:" not in joined and "now:" not in joined
    minus = next(l for l in lines if l.startswith("    - "))
    plus = next(l for l in lines if l.startswith("    + "))
    assert "after 3600 seconds." in minus and "an hour old." in plus
    assert lines.index(minus) < lines.index(plus)
    kept = [l for l in lines if l.startswith("      ") and "audit log" in l]
    assert len(kept) == 1 and joined.count("audit log") == 1


def test_removed_is_red_added_is_green_and_the_moved_words_are_marked(
        demo_project, monkeypatch):
    """Coloured as git colours a diff, and within a replaced sentence the words
    that moved form one reverse-video run, spaces included, so a reworded phrase
    reads as a phrase (SR-0056)."""
    paint_of = {"removed": 0x100, "added": 0x200}
    monkeypatch.setattr(tui, "_attr", lambda name, bold=False: paint_of.get(name, 0))
    _answer(monkeypatch, RatificationChange(
        uid="FR-0001", outcome="changed", stamp="sha256:abc", revision="a" * 40,
        changes=(FieldChange("text", PARAGRAPH, REWORDED),)))
    lines = _painted(_item(), core.open_session(demo_project))

    minus_text, minus_paint = next(l for l in lines if l[0].startswith("    - "))
    plus_text, plus_paint = next(l for l in lines if l[0].startswith("    + "))
    kept_text, kept_paint = next(l for l in lines if "audit log" in l[0])
    assert all(attr & 0x100 for _n, attr in minus_paint)      # the whole line red
    assert all(attr & 0x200 for _n, attr in plus_paint)       # the whole line green
    assert all(attr == 0 for _n, attr in kept_paint)          # a kept sentence, plain
    assert _runs(minus_text, minus_paint, tui.curses.A_REVERSE) == ["after 3600 seconds."]
    assert _runs(plus_text, plus_paint, tui.curses.A_REVERSE) == ["when it is an hour old."]


def test_the_diff_is_wrapped_to_the_pane(demo_project, monkeypatch):
    """No line runs past the pane, a wrapped sentence keeps its mark on its first
    line only, and every span covers exactly the text it paints (SR-0056)."""
    _answer(monkeypatch, RatificationChange(
        uid="FR-0001", outcome="changed", stamp="sha256:abc", revision="a" * 40,
        changes=(FieldChange("text", PARAGRAPH, REWORDED),)))
    lines = _painted(_item(), core.open_session(demo_project), width=44)
    diff = [(t, pnt) for t, pnt in lines if isinstance(pnt, tuple)]
    assert len(diff) > 4                                       # four units, some wrapped
    assert all(len(t) <= 44 for t, _p in diff), [t for t, _p in diff]
    assert sum(t.startswith(("    - ", "    + ")) for t, _p in diff) == 2
    assert all(sum(n for n, _a in pnt) == len(t) for t, pnt in diff)


def test_which_words_moved_is_throughlines_answer_not_a_second_diff(
        demo_project, monkeypatch):
    """The pane lays out the units throughline hands it and computes none of its
    own; the rule for what moved lives in one place (SR-0053, tl:SR-0200)."""
    from throughline.ratification import DiffUnit, KEPT, REMOVED, ADDED
    units = (DiffUnit(REMOVED, (("alpha", False), ("beta", True))),
             DiffUnit(ADDED, (("alpha", False), ("gamma", True))),
             DiffUnit(KEPT, (("delta", False),)))
    asked = []

    def _fake(was, now):
        asked.append((was, now))
        return units

    monkeypatch.setattr(tui, "diff_prose", _fake)
    _answer(monkeypatch, RatificationChange(
        uid="FR-0001", outcome="changed", stamp="sha256:abc", revision="a" * 40,
        changes=(FieldChange("text", "one two", "one three"),)))
    lines = _pane(_item(), core.open_session(demo_project), width=200)
    assert asked == [("one two", "one three")]
    assert "    - alpha beta" in lines and "    + alpha gamma" in lines
    assert "      delta" in lines


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


# --------------------------------------------------------------------------- #
# A span-painted line reaches the screen span by span
# --------------------------------------------------------------------------- #

class _Window:
    """A stand-in screen that records what is drawn where, and under what."""
    def __init__(self):
        self.calls: list[tuple[int, int, str, int]] = []

    def getmaxyx(self):
        return 40, 200

    def addstr(self, y, x, text, attr):
        self.calls.append((y, x, text, attr))


def test_a_span_painted_line_is_drawn_piece_by_piece_in_place():
    """The drawer splits a diff line at its span boundaries and puts every piece
    at the column it belongs to, so a marked word lands exactly where the text
    says it is (SR-0056)."""
    win = _Window()
    tui._addline(win, 3, 5, "    - after 3600 old", ((6, 7), (5, 7), (1, 7), (4, 9), (1, 7), (3, 7)))
    assert win.calls == [
        (3, 5, "    - ", 7), (3, 11, "after", 7), (3, 16, " ", 7),
        (3, 17, "3600", 9), (3, 21, " ", 7), (3, 22, "old", 7),
    ]
    assert "".join(t for _y, _x, t, _a in win.calls) == "    - after 3600 old"


def test_a_plainly_painted_line_is_drawn_whole():
    win = _Window()
    tui._addline(win, 1, 2, "text", 5)
    assert win.calls == [(1, 2, "text", 5)]


def test_content_resolved_from_the_record_says_so_rather_than_naming_no_revision(
        demo_project, monkeypatch):
    """From 3.10.0 a ratification record carries the content it was taken over, so the
    earlier wording needs no history and there is no revision to name. The pane used to
    print an em dash there, which reads as "we could not tell" (SR-0053, tl:SR-0216)."""
    _answer(monkeypatch, RatificationChange(
        uid="FR-0001", outcome="changed", stamp="sha256:abc", source=RECORD,
        changes=(FieldChange("text", "was", "now"),)))
    joined = "\n".join(_pane(_item(), core.open_session(demo_project)))
    assert "signed content from the record" in joined
    assert "signed content at" not in joined


def test_content_resolved_from_history_still_names_the_revision(demo_project, monkeypatch):
    """The other route is unchanged: a reviewer who doubts it gets a handle to look at."""
    _answer(monkeypatch, RatificationChange(
        uid="FR-0001", outcome="changed", stamp="sha256:abc", source=HISTORY,
        revision="c0ffee123" + "0" * 31,
        changes=(FieldChange("text", "was", "now"),)))
    joined = "\n".join(_pane(_item(), core.open_session(demo_project)))
    assert "signed content at c0ffee123" in joined
    assert "from the record" not in joined
