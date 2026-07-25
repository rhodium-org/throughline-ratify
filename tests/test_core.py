# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest

from throughline_ratify import core


def _by_uid(rows):
    return {r.uid: r for r in rows}


def test_open_session_finds_project_from_subdir(demo_project):
    session = core.open_session(demo_project / "requirements")
    assert session.root == demo_project
    assert not session.composed
    assert session.ratified_status == "ratified"
    assert session.proposed_status == "proposed"


def test_queue_excludes_ratified_and_roots_by_default(demo_project):
    session = core.open_session(demo_project)
    rows = _by_uid(core.build_queue(session))
    # ratified item and the two ratified roots are not pending
    assert "FR-0005" not in rows
    assert "INT-0001" not in rows
    assert "RISK-0001" not in rows
    # FR-0007 is 'blocked' (overshot, never signed off) so it IS pending
    assert set(rows) == {"FR-0001", "FR-0002", "FR-0003", "FR-0004", "FR-0007"}


def test_show_all_includes_ratified(demo_project):
    session = core.open_session(demo_project)
    rows = _by_uid(core.build_queue(session, show_all=True))
    assert "FR-0005" in rows


def test_dead_items_hidden_by_default_visible_under_show_all(demo_project):
    # A rejected/tombstoned item must not silently vanish: it is excluded from the
    # default backlog but reappears under show_all so a reviewer can see it (SR-0020).
    session = core.open_session(demo_project)
    default = _by_uid(core.build_queue(session))
    assert "FR-0008" not in default  # rejected
    assert "FR-0009" not in default  # deleted
    allrows = _by_uid(core.build_queue(session, show_all=True))
    assert "FR-0008" in allrows
    assert "FR-0009" in allrows


def test_dead_items_get_role_derived_concern_and_are_not_actionable(demo_project):
    session = core.open_session(demo_project)
    rows = _by_uid(core.build_queue(session, show_all=True))
    rejected = rows["FR-0008"]
    deleted = rows["FR-0009"]
    assert rejected.concern == "rejected"        # invalidated role
    assert deleted.concern == "deleted"          # tombstone role
    assert not rejected.ratifiable_now
    assert not deleted.ratifiable_now
    # the rejection reason travels with the row for the detail pane
    assert rejected.reason == "superseded by FR-0002"


def test_reject_then_show_all_reveals_the_rejected_item(demo_project):
    # The reported bug: rejecting made an item disappear even under show_all. After a
    # reject, the item is dead but must still be visible in the wide view.
    session = core.open_session(demo_project)
    core.reject_item(session, "FR-0002", reason="not needed")
    fresh = core.open_session(demo_project)
    assert "FR-0002" not in _by_uid(core.build_queue(fresh))          # gone from backlog
    allrows = _by_uid(core.build_queue(fresh, show_all=True))
    assert "FR-0002" in allrows                                       # still visible
    assert allrows["FR-0002"].concern == "rejected"
    assert allrows["FR-0002"].reason == "not needed"


def test_ratified_items_get_their_own_concern(demo_project):
    # a signed-off item is "ratified", NOT conflated with the "ready" state used
    # for approved-but-unratified items (SR-0010).
    session = core.open_session(demo_project)
    rows = _by_uid(core.build_queue(session, show_all=True))
    assert rows["FR-0005"].concern == "ratified"  # already signed off
    assert rows["FR-0002"].concern == "ready"      # approved, not yet ratified


def test_ratification_progress_counts_whole_project(demo_project):
    session = core.open_session(demo_project)
    # non-dead items: 2 roots + FR-0001..0007 = 9; ratified: 2 roots + FR-0005 +
    # FR-0006 (ratified-then-implemented, counted via its stamp) = 4
    assert core.ratification_progress(session) == (4, 9)


def test_ratified_then_advanced_item_is_done_not_pending(demo_project):
    # FR-0006 was ratified then moved on to 'implemented'. It carries the
    # ratified_by stamp, so it must be treated as signed off — excluded from the
    # pending queue and never re-offered for a ratification 'implemented' can't take.
    session = core.open_session(demo_project)
    pending = _by_uid(core.build_queue(session))
    assert "FR-0006" not in pending
    rows = _by_uid(core.build_queue(session, show_all=True))
    assert rows["FR-0006"].concern == "ratified"
    assert not rows["FR-0006"].ratifiable_now


def test_overshot_item_is_blocked_with_computed_reratify_route(demo_project):
    # FR-0007 advanced to 'implemented' but was never signed off (no stamp). It is
    # grounded and unambiguous, so it is 'blocked', not ratifiable now, and carries a
    # re-ratify itinerary computed purely from the project's [transitions].
    session = core.open_session(demo_project)
    rows = _by_uid(core.build_queue(session, show_all=True))
    row = rows["FR-0007"]
    assert row.concern == "blocked"
    assert not row.ratifiable_now
    # implemented -> suspect -> ratified -> implemented under the fixture transitions
    assert row.reratify_path == ["implemented", "suspect", "ratified", "implemented"]
    # a directly-ratifiable item earns no route
    assert rows["FR-0001"].reratify_path is None
    # nor does an already-signed-off overshoot
    assert rows["FR-0006"].reratify_path is None


def test_reratify_records_signoff_and_restores_status(demo_project):
    session = core.open_session(demo_project)
    route = core.reratify_item(session, "FR-0007", by="tester")
    assert route == ["implemented", "suspect", "ratified", "implemented"]
    # reopen from disk: the item ends exactly where it started, now stamped, and it
    # is no longer pending.
    fresh = core.open_session(demo_project)
    item = fresh.project.get("FR-0007")
    assert item.status == "implemented"          # restored to its original status
    assert item.attrs.get("ratified_by") == "tester"
    assert "FR-0007" not in _by_uid(core.build_queue(fresh))
    assert _by_uid(core.build_queue(fresh, show_all=True))["FR-0007"].concern == "ratified"


def test_reratify_refuses_when_no_route_and_gates_apply(demo_project):
    session = core.open_session(demo_project)
    # ungrounded item is refused on the grounding gate, before any routing
    with pytest.raises(core.RatifierError, match="grounded"):
        core.reratify_item(session, "FR-0003", by="tester")
    # a directly-ratifiable item has no round-trip overshoot route
    with pytest.raises(core.RatifierError, match="no route"):
        core.reratify_item(session, "FR-0001", by="tester")


def test_progress_climbs_as_items_are_ratified(demo_project):
    session = core.open_session(demo_project)
    before, total = core.ratification_progress(session)
    core.ratify_item(session, "FR-0001", by="tester")
    after, total_after = core.ratification_progress(session)
    assert after == before + 1
    assert total_after == total  # gradable set unchanged; only the ratified count moves


def test_grounding_depth_on_rows(demo_project):
    session = core.open_session(demo_project)
    rows = _by_uid(core.build_queue(session, show_all=True))
    assert rows["INT-0001"].depth == 0           # a root
    assert rows["FR-0001"].depth == 1            # derives_from INT-0001
    assert rows["FR-0002"].depth == 1            # mitigates RISK-0001
    assert rows["FR-0003"].depth is None         # ungrounded — never reaches a root


def test_sort_roots_orders_shallowest_first(demo_project):
    session = core.open_session(demo_project)
    order = [r.uid for r in core.build_queue(session, show_all=True, sort="roots")]
    # roots (depth 0) precede their children (depth 1); ungrounded FR-0003 sorts last
    assert order.index("INT-0001") < order.index("FR-0001")
    assert order.index("RISK-0001") < order.index("FR-0002")
    assert order[-1] == "FR-0003"


def test_sort_leaves_orders_deepest_first(demo_project):
    session = core.open_session(demo_project)
    order = [r.uid for r in core.build_queue(session, show_all=True, sort="leaves")]
    # children (depth 1) precede roots (depth 0); ungrounded still sorts last
    assert order.index("FR-0001") < order.index("INT-0001")
    assert order[-1] == "FR-0003"


def test_build_queue_rejects_unknown_sort(demo_project):
    session = core.open_session(demo_project)
    with pytest.raises(core.RatifierError, match="sort"):
        core.build_queue(session, sort="sideways")


def test_concern_classification(demo_project):
    session = core.open_session(demo_project)
    rows = _by_uid(core.build_queue(session))
    assert rows["FR-0001"].concern == "proposed"
    assert rows["FR-0001"].ratifiable_now
    assert rows["FR-0002"].concern == "ready"
    assert rows["FR-0002"].ratifiable_now
    assert rows["FR-0003"].concern == "ungrounded"
    assert not rows["FR-0003"].ratifiable_now
    assert rows["FR-0004"].concern == "ambiguous"
    assert not rows["FR-0004"].ratifiable_now


def test_queue_sorted_most_actionable_first(demo_project):
    session = core.open_session(demo_project)
    order = [r.uid for r in core.build_queue(session)]
    # proposed(0) < ready(1) < ungrounded(3) < ambiguous(4)
    assert order.index("FR-0001") < order.index("FR-0002")
    assert order.index("FR-0002") < order.index("FR-0003")
    assert order.index("FR-0003") < order.index("FR-0004")


def test_links_resolve_titles(demo_project):
    session = core.open_session(demo_project)
    rows = _by_uid(core.build_queue(session))
    lv = rows["FR-0001"].links[0]
    assert (lv.type, lv.ref) == ("derives_from", "INT-0001")
    assert lv.title == "Frictionless onboarding"
    assert lv.resolved
    assert not lv.external  # a local reference, not from a composed source


def test_links_carry_target_source_ref(demo_project):
    # A link view exposes the target's authoritative clause reference
    # (attrs.source_ref) so the detail pane can show it instead of the namespace.
    session = core.open_session(demo_project)
    rows = _by_uid(core.build_queue(session))
    lv = rows["FR-0001"].links[0]  # derives_from INT-0001
    assert lv.source_ref == "ASVS-V1.2.3"
    # a target without a source_ref yields an empty string, not an error
    lv2 = rows["FR-0002"].links[0]  # mitigates RISK-0001 (no source_ref)
    assert lv2.source_ref == ""


def test_ratify_persists_and_leaves_queue(demo_project):
    session = core.open_session(demo_project)
    core.ratify_item(session, "FR-0001", by="tester")
    # reopen from disk: the change is durable and FR-0001 is no longer pending
    fresh = core.open_session(demo_project)
    rows = _by_uid(core.build_queue(fresh))
    assert "FR-0001" not in rows
    item = fresh.project.get("FR-0001")
    assert item.status == "ratified"
    assert item.attrs.get("ratified_by") == "tester"


def test_ratify_refuses_ungrounded(demo_project):
    session = core.open_session(demo_project)
    with pytest.raises(core.RatifierError, match="grounded"):
        core.ratify_item(session, "FR-0003", by="tester")


def test_ratify_refuses_ambiguous(demo_project):
    session = core.open_session(demo_project)
    with pytest.raises(core.RatifierError, match="ambiguous"):
        core.ratify_item(session, "FR-0004", by="tester")


def test_reject_invalidates_and_persists(demo_project):
    session = core.open_session(demo_project)
    core.reject_item(session, "FR-0002", reason="not needed")
    fresh = core.open_session(demo_project)
    item = fresh.project.get("FR-0002")
    assert item.status == "rejected"
    assert item.attrs.get("invalidated_reason") == "not needed"


def test_remove_informational_link_persists(demo_project):
    session = core.open_session(demo_project)
    # FR-0002: [0] mitigates RISK-0001 (grounding), [1] relates FR-0001 (informational)
    view = core.remove_link(session, "FR-0002", 1)
    assert (view.type, view.ref) == ("relates", "FR-0001")
    fresh = core.open_session(demo_project)
    item = fresh.project.get("FR-0002")
    assert [ln.type for ln in item.links] == ["mitigates"]  # only the grounding link remains


def test_remove_link_refuses_orphaning(demo_project):
    session = core.open_session(demo_project)
    # FR-0001's sole link is its grounding edge; removing it would reach no root
    with pytest.raises(core.RatifierError, match="root"):
        core.remove_link(session, "FR-0001", 0)
    # nothing was written
    fresh = core.open_session(demo_project)
    assert len(fresh.project.get("FR-0001").links) == 1


def test_remove_link_still_grounded_after_dropping_grounding_link(demo_project):
    # FR-0002 keeps grounding via mitigates even though we drop the informational
    # link; and its grounding link itself is refused since it is the only root path.
    session = core.open_session(demo_project)
    with pytest.raises(core.RatifierError, match="root"):
        core.remove_link(session, "FR-0002", 0)  # the sole grounding link


def test_remove_link_rejects_bad_index(demo_project):
    session = core.open_session(demo_project)
    with pytest.raises(core.RatifierError, match="position"):
        core.remove_link(session, "FR-0002", 9)


def test_default_ratifier_is_nonempty(demo_project):
    assert core.default_ratifier()


def test_open_session_without_status_roles_errors_cleanly(tmp_path):
    # A format_version 3 project that never declared [status.roles] must fail with
    # a guiding RatifierError, not an uncaught SchemaError traceback.
    root = tmp_path / "roleless"
    root.mkdir()
    (root / "throughline.toml").write_text(
        "[project]\n"
        'name = "Roleless"\n'
        "format_version = 3\n\n"
        "[status]\n"
        'values = ["proposed", "ratified"]\n',
        encoding="utf-8",
    )
    with pytest.raises(core.RatifierError, match=r"\[status.roles\]"):
        core.open_session(root)
