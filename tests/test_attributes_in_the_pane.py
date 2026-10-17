# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0076 — the detail pane shows every attribute the item carries, and marks the
ones the signature covers.

The pane drew an item's text, rationale and links and nothing else. An item whose
schema declares normative attributes — a source's url and publisher, a
requirement's priority — was signed from a screen that never showed them, though
the fingerprint under the signature reads every one. throughline's own `tl ratify`
names them to the signer; the cockpit did not.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from throughline_ratify import core, tui


@pytest.fixture(autouse=True)
def _no_curses(monkeypatch):
    """The pane is built without a terminal; only the text it lays out is tested."""
    monkeypatch.setattr(tui, "_attr", lambda name, bold=False: 0)


_DECLARED = (
    '[types.requirement]\n'
    'attrs.origin = { type = "enum", values = ["human", "ai", "hybrid"] }\n'
    'attrs.priority = { type = "enum", values = ["must", "should"], normative = true }\n'
    'attrs.notes = { type = "text" }\n'
)


def _declare(project: Path) -> None:
    """Give the fixture's requirement type one normative attribute and two that
    are not, so the pane has both kinds to tell apart."""
    cfg = project / "throughline.toml"
    text = cfg.read_text(encoding="utf-8")
    old = ('[types.requirement]\n'
           'attrs.origin = { type = "enum", values = ["human", "ai", "hybrid"] }\n')
    assert old in text
    cfg.write_text(text.replace(old, _DECLARED, 1), encoding="utf-8")


def _with_attrs(project: Path, uid: str, yaml_attrs: str, *, flags: str = "") -> None:
    """Append an ``attrs:`` block (and, with ``flags``, replace the normative line)
    on one fixture item, written as YAML the way an author would."""
    path = project / "requirements" / f"{uid}.yml"
    text = path.read_text(encoding="utf-8")
    if flags:
        text = text.replace("normative: true\n", flags, 1)
    path.write_text(text + yaml_attrs, encoding="utf-8")


def _pane(project: Path, uid: str, width: int = 80) -> list[str]:
    session = core.open_session(project)
    rows = {r.uid: r for r in core.build_queue(session, show_all=True)}
    app = tui.App(None, session, "Ada Lovelace", None)
    return [text for text, _a in app._detail_lines(rows[uid], width)]


def _row(project: Path, uid: str) -> core.QueueItem:
    session = core.open_session(project)
    return {r.uid: r for r in core.build_queue(session, show_all=True)}[uid]


# --------------------------------------------------------------------------- #
# Every attribute, as written
# --------------------------------------------------------------------------- #

def test_every_attribute_the_author_wrote_is_in_the_pane(demo_project):
    """Each attribute the file holds is drawn as ``name: value``, in the file's
    order, under a heading of its own (SR-0076)."""
    _declare(demo_project)
    _with_attrs(demo_project, "FR-0001",
                "attrs:\n  origin: ai\n  priority: must\n  notes: reviewed twice\n")
    lines = _pane(demo_project, "FR-0001")
    heading = next(i for i, l in enumerate(lines) if l.startswith("attributes"))
    body = [l.strip() for l in lines[heading + 1:heading + 4]]
    assert body == ["origin: ai", "✓ priority: must", "notes: reviewed twice"]


def test_an_item_without_attributes_draws_no_attributes_heading(demo_project):
    """Nothing to show, nothing drawn: an empty section would read as a claim that
    the item has attributes and they are blank (SR-0076)."""
    lines = _pane(demo_project, "FR-0003")
    assert not any(l.startswith("attributes") for l in lines)


def test_a_value_on_several_lines_is_read_on_several_lines(demo_project):
    """A block value keeps its lines, continued under the name rather than run
    together into one (SR-0076, as SR-0044 holds for prose)."""
    _declare(demo_project)
    _with_attrs(demo_project, "FR-0001",
                "attrs:\n  notes: |-\n    first line\n    second line\n")
    lines = _pane(demo_project, "FR-0001")
    first = next(i for i, l in enumerate(lines) if l.strip() == "notes: first line")
    assert lines[first + 1].strip() == "second line"
    assert lines[first + 1].startswith("      "), "a continuation sits under the value"


def test_a_list_value_is_one_element_per_line(demo_project):
    """A list arrives only undeclared — the schema declares no list type — and is
    still read one element to a line (SR-0076)."""
    _with_attrs(demo_project, "FR-0001", "attrs:\n  tags:\n  - alpha\n  - beta\n")
    lines = [l.strip() for l in _pane(demo_project, "FR-0001")]
    first = lines.index("tags: alpha")
    assert lines[first + 1] == "beta"


# --------------------------------------------------------------------------- #
# Which of them the signature covers
# --------------------------------------------------------------------------- #

def test_the_attributes_the_signature_covers_are_marked(demo_project):
    """The schema's normative attributes carry the mark and the heading explains
    it; the rest carry none (SR-0076)."""
    _declare(demo_project)
    _with_attrs(demo_project, "FR-0001",
                "attrs:\n  priority: must\n  notes: reviewed twice\n  origin: ai\n")
    lines = _pane(demo_project, "FR-0001")
    heading = next(l for l in lines if l.startswith("attributes"))
    assert "✓ covered by the signature" in heading
    marked = [l.strip() for l in lines if l.strip().startswith("✓ ")
              and ":" in l and "ready" not in l and "ratified" not in l]
    assert marked == ["✓ priority: must"]
    assert any(l.strip() == "notes: reviewed twice" for l in lines)
    assert any(l.strip() == "origin: ai" for l in lines)


def test_the_signed_names_are_the_schemas_normative_attributes(demo_project):
    """The row carries the names the fingerprint reads, asked of the project's
    schema, not decided here (SR-0076, SR-0022)."""
    _declare(demo_project)
    _with_attrs(demo_project, "FR-0001", "attrs:\n  priority: must\n")
    row = _row(demo_project, "FR-0001")
    assert row.signed_attrs == ("priority",)
    assert row.attrs == {"priority": "must"}


def test_a_heading_without_a_marked_attribute_carries_no_legend(demo_project):
    """Where none of the item's attributes is covered, the legend would explain a
    mark that appears nowhere (SR-0076)."""
    _declare(demo_project)
    _with_attrs(demo_project, "FR-0001", "attrs:\n  origin: ai\n")
    heading = next(l for l in _pane(demo_project, "FR-0001") if l.startswith("attributes"))
    assert heading == "attributes"


def test_an_undeclared_attribute_is_shown_too(demo_project):
    """The fixture's intent carries ``source_ref`` with no schema entry for it. It
    is on the item, so it is on the screen (SR-0076)."""
    lines = [l.strip() for l in _pane(demo_project, "INT-0001")]
    assert "source_ref: ASVS-V1.2.3" in lines


# --------------------------------------------------------------------------- #
# What is left out, and what is not
# --------------------------------------------------------------------------- #

def test_the_ratification_record_is_not_drawn_as_an_attribute(demo_project):
    """FR-0010 carries ``ratified_by`` and a fingerprint. The readiness line
    already names the signer; the record's own keys and hash are noise to a
    reader and are the Tool's, not the author's (SR-0076)."""
    lines = _pane(demo_project, "FR-0010")
    joined = "\n".join(lines)
    assert "ratified by alice" in joined, "the readiness line still names the signer"
    assert "ratified_by" not in joined
    assert "sha256:" not in joined
    assert not any(l.startswith("attributes") for l in lines)


def test_the_clarification_record_is_drawn(demo_project):
    """A removed ambiguity flag is about the words being signed, and the Tool puts
    it in front of a signer itself (tl:SR-0214); the pane does the same (SR-0076)."""
    _with_attrs(demo_project, "FR-0001",
                "attrs:\n  clarified_by: Ada Lovelace\n  clarified_reason: the two readings were one\n")
    lines = [l.strip() for l in _pane(demo_project, "FR-0001")]
    assert "clarified_by: Ada Lovelace" in lines
    assert "clarified_reason: the two readings were one" in lines


def test_the_record_is_left_out_by_asking_the_tool_which_names_are_its(demo_project):
    """Which names make up the ratification record is throughline's to say
    (SR-0057, SR-0076): the row leaves out exactly the names ``attribute_owner``
    assigns to that record, and no others."""
    from throughline import attribute_owner
    _with_attrs(demo_project, "FR-0001",
                "attrs:\n  ratified_supersedes: FR-0000\n  ratified_revision: abc\n  origin: ai\n")
    row = _row(demo_project, "FR-0001")
    assert attribute_owner("ratified_supersedes") is not None
    assert row.attrs == {"origin": "ai"}


# --------------------------------------------------------------------------- #
# The two flags the fingerprint reads
# --------------------------------------------------------------------------- #

def test_a_non_normative_or_derived_item_says_so_in_its_header(demo_project):
    """``normative`` and ``derived`` are signed content; a departure from the
    default is on the header line, the default is left unsaid (SR-0076)."""
    _with_attrs(demo_project, "FR-0001", "", flags="normative: false\nderived: true\n")
    header = _pane(demo_project, "FR-0001")[1]
    assert "non-normative" in header and "derived" in header
    default = _pane(demo_project, "FR-0002")[1]
    assert "non-normative" not in default and "derived" not in default
