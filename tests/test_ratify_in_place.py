# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""Signing off without moving the item (throughline SR-0172).

A project whose statuses track progress rather than agreement binds the ratified
role to a workflow state, and declares that ratification records the sign-off where
the item already stands. The cockpit must then stop treating "can this status reach
ratified?" as the question — there is no transition to make, so every status can
take a sign-off, and the round trip that exists for an overshot item must not be
offered. Walking one would fabricate the history that setting exists to avoid.

FR-0007 is the fixture's overshot item: advanced to `implemented`, never signed off.
It is the case that separates the two modes.
"""
from __future__ import annotations

from throughline_ratify import core


def _by_uid(rows):
    return {r.uid: r for r in rows}


def test_default_still_needs_the_round_trip(demo_project):
    """The premise. Where ratification advances the item, an overshot one cannot be
    signed off directly and is offered the itinerary instead."""
    session = core.open_session(demo_project)
    row = _by_uid(core.build_queue(session))["FR-0007"]
    assert row.status == "implemented"
    assert not row.ratifiable_now
    assert row.concern == "blocked"
    assert row.reratify_path is not None


def test_in_place_makes_an_overshot_item_directly_ratifiable(in_place_project):
    """The same item, same status, one declaration different — no longer blocked and
    no itinerary, because none is needed."""
    session = core.open_session(in_place_project)
    row = _by_uid(core.build_queue(session))["FR-0007"]
    assert row.status == "implemented"
    assert row.ratifiable_now
    assert row.concern != "blocked"
    assert row.reratify_path is None


def test_in_place_sign_off_leaves_the_status_where_it_was(in_place_project):
    session = core.open_session(in_place_project)
    core.ratify_item(session, "FR-0007", by="tester")

    reloaded = core.open_session(in_place_project)
    item = reloaded.project.get("FR-0007")
    assert item.status == "implemented"          # not advanced
    assert item.attrs["ratified_by"] == "tester"
    assert item.attrs["ratified_fingerprint"].startswith("sha256:")


def test_in_place_sign_off_settles_the_item(in_place_project):
    """Having signed it, it must drop out of the pending worklist — the stamp is the
    witness, since the status never moved to become one."""
    session = core.open_session(in_place_project)
    core.ratify_item(session, "FR-0007", by="tester")

    reloaded = core.open_session(in_place_project)
    assert "FR-0007" not in _by_uid(core.build_queue(reloaded))


def test_in_place_does_not_read_the_ratified_status_as_a_signature(in_place_project):
    """The trap this mode opens. A project doing in-place sign-off binds the ratified
    role to an ordinary workflow state, so reading that status as a signature would
    settle every item merely passing through it — signed by nobody. FR-0005 sits at
    `ratified` in the fixture with no `ratified_by`, and must still be pending."""
    session = core.open_session(in_place_project)
    item = session.project.get("FR-0005")
    assert item.status == "ratified"
    assert not item.attrs.get("ratified_by")
    assert "FR-0005" in _by_uid(core.build_queue(session))


def test_in_place_leaves_the_ungrounded_and_ambiguous_gates_alone(in_place_project):
    """Turning off the status move must not turn off what may be signed off. FR-0003
    is the fixture's ungrounded item and FR-0004 its ambiguous one."""
    rows = _by_uid(core.build_queue(core.open_session(in_place_project)))
    assert not rows["FR-0003"].ratifiable_now
    assert not rows["FR-0004"].ratifiable_now
