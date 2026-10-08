# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0006 — grounding is evaluated over the composed union, and writes land only
on the consumer.

The consumer here holds one item, FR-0009, whose only route to a root runs
through a source it composes. Nothing is stubbed: the source is resolved by the
throughline installed.
"""
from __future__ import annotations

import pytest

from throughline_ratify import core

from test_core import _composed_consumer

ADA = "Ada Lovelace"


def _files(root):
    return {p.relative_to(root): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture
def composed(tmp_path):
    consumer = _composed_consumer(tmp_path)
    return consumer, tmp_path / "base"


def _row(session, uid):
    return {r.uid: r for r in core.build_queue(session, show_all=True)}[uid]


def test_a_chain_that_reaches_a_root_through_a_source_counts(composed):
    consumer, _ = composed
    session = core.open_session(consumer)
    assert session.composed
    row = _row(session, "FR-0009")
    assert row.grounded and row.ratifiable_now


def test_the_borrowed_root_is_in_the_union_and_not_in_the_consumer(composed):
    consumer, _ = composed
    session = core.open_session(consumer)
    link = _row(session, "FR-0009").links[0]
    assert link.ref == "base:INT-0001"
    assert link.title == "Frictionless onboarding", "resolved through the union"
    assert not (consumer / "intents" / "base:INT-0001.yml").exists()


def test_borrowed_items_are_not_offered_for_ratification(composed):
    consumer, _ = composed
    session = core.open_session(consumer)
    assert not [r.uid for r in core.build_queue(session, show_all=True) if ":" in r.uid]


def test_ratifying_writes_the_consumers_item_and_leaves_the_source_alone(composed):
    consumer, base = composed
    before = _files(base)
    session = core.open_session(consumer)
    core.ratify_item(session, "FR-0009", ADA)
    assert f"ratified_by: {ADA}" in (
        consumer / "requirements" / "FR-0009.yml").read_text(encoding="utf-8")
    assert _files(base) == before


def test_rejecting_leaves_the_source_alone_too(composed):
    consumer, base = composed
    before = _files(base)
    session = core.open_session(consumer)
    core.reject_item(session, "FR-0009", "not wanted")
    assert "status: rejected" in (
        consumer / "requirements" / "FR-0009.yml").read_text(encoding="utf-8")
    assert _files(base) == before


def test_removing_the_link_into_the_source_is_refused_as_orphaning(composed):
    """The link into the source is the item's only grounding, so the union is
    what the refusal is judged against."""
    consumer, base = composed
    before = _files(base)
    session = core.open_session(consumer)
    with pytest.raises(core.RatifierError):
        core.remove_link(session, "FR-0009", 0)
    assert _files(base) == before


def test_without_the_source_declared_the_same_item_is_ungrounded(composed):
    consumer, _ = composed
    cfg = consumer / "throughline.toml"
    cfg.write_text(cfg.read_text(encoding="utf-8").split("[[sources]]")[0],
                   encoding="utf-8")
    session = core.open_session(consumer)
    assert not session.composed
    assert not _row(session, "FR-0009").grounded
