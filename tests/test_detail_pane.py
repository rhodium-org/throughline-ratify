# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0044 — an item's paragraph breaks survive into the detail pane.

The pane wrapped each field with ``textwrap.wrap``, which replaces whitespace, so a
rationale written as four short paragraphs was drawn as one block with a double space
where each blank line had been. This is the screen a person reads an item on in order
to take accountability for it, and the reviewer had no way to tell that what they were
reading was not what the author wrote.
"""

from __future__ import annotations

import pytest

from throughline_ratify import core, tui

_TWO_PARAS = "First paragraph, short.\n\nSecond paragraph, also short."


@pytest.fixture(autouse=True)
def _no_curses(monkeypatch):
    """The pane is built without a terminal; only the text it lays out is under test."""
    monkeypatch.setattr(tui, "_attr", lambda name, bold=False: 0)


def _item(**kw) -> core.QueueItem:
    fields = dict(
        uid="FR-0001", title="A title", type="requirement", status="proposed",
        concern="proposed", grounded=True, ambiguous=False, ratifiable_now=True,
        text="", rationale="", links=[], depth=1,
    )
    fields.update(kw)
    return core.QueueItem(**fields)


def _pane(item: core.QueueItem, session, width: int = 60) -> list[str]:
    app = tui.App(None, session, "Ada Lovelace", None)
    return [text for text, _attr in app._detail_lines(item, width)]


# --------------------------------------------------------------------------- #
# The split itself
# --------------------------------------------------------------------------- #

def test_a_field_with_no_blank_line_is_one_paragraph():
    assert tui._paragraphs("one line\nand its continuation") == [
        "one line\nand its continuation"
    ]


@pytest.mark.parametrize("sep", ["\n\n", "\n\n\n", "\n   \n", "\n\t\n\n"])
def test_a_blank_line_separates_paragraphs_however_it_is_written(sep):
    assert tui._paragraphs(f"one{sep}two") == ["one", "two"]


def test_an_empty_field_is_still_one_paragraph_to_draw():
    """``wrap`` draws whatever it is given, so it must always be given something."""
    assert tui._paragraphs("") == [""]
    assert tui._paragraphs("\n \n") == [""]


# --------------------------------------------------------------------------- #
# What reaches the pane
# --------------------------------------------------------------------------- #

def test_text_and_rationale_keep_their_paragraph_breaks(demo_project):
    session = core.open_session(demo_project)
    lines = _pane(_item(text=_TWO_PARAS, rationale=_TWO_PARAS), session)

    assert "  First paragraph, short." in lines
    assert "  Second paragraph, also short." in lines
    # the defect: the break became a space inside one wrapped line
    assert not any("short.  Second" in ln for ln in lines)

    first = lines.index("  First paragraph, short.")
    assert lines[first + 1] == "", "a blank line stands between the paragraphs"


def test_an_expanded_link_target_keeps_them_too(demo_project):
    """A borrowed item is read through the same pane, so it is read the same way."""
    session = core.open_session(demo_project)
    link = core.LinkView(
        type="derives_from", ref="INT-0001", title="A parent",
        text=_TWO_PARAS, target_type="intent", target_status="ratified",
    )
    app = tui.App(None, session, "Ada Lovelace", None)
    app.expanded = {0}
    lines = [t for t, _a in app._detail_lines(_item(links=[link]), 60)]

    assert "      First paragraph, short." in lines
    assert "      Second paragraph, also short." in lines


def test_a_single_paragraph_field_gains_no_blank_line(demo_project):
    """The fix must not start spacing out fields that were never broken up."""
    session = core.open_session(demo_project)
    lines = _pane(_item(text="One paragraph, wrapped across the width of the pane "
                             "because it is long enough to need it."), session)
    body_start = lines.index("text") + 1
    assert "" not in lines[body_start:body_start + 2]
