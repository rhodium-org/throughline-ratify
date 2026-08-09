# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest

from throughline.graph import Index
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
    # FR-0007 is 'blocked' (overshot, never signed off) so it IS pending, and so are
    # FR-0010/FR-0011, whose signatures no longer cover their content (SR-0030).
    assert set(rows) == {"FR-0001", "FR-0002", "FR-0003", "FR-0004", "FR-0007",
                         "FR-0010", "FR-0011"}


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
    # non-dead items: 2 roots + FR-0001..0007 + FR-0010..0011 = 11; ratified: 2 roots
    # + FR-0005 + FR-0006 (ratified-then-implemented, counted via its stamp) = 4.
    # FR-0010/FR-0011 carry a stamp but a stale one, so they count as outstanding.
    assert core.ratification_progress(session) == (4, 11)


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


def _fingerprint_of(project, uid: str) -> str:
    from throughline.fingerprint import fingerprint
    return fingerprint(project.get(uid), project.schema)


# --------------------------------------------------------------------------- #
# A signature the content has outgrown (SR-0030).
# --------------------------------------------------------------------------- #

def test_a_stale_signature_returns_the_item_to_the_worklist(demo_project):
    """The reported gap: throughline's check calls a stale ratification an error, and
    the tool built for the only person who can clear it showed the item as '✓ ratified'
    and left it out of the backlog entirely."""
    session = core.open_session(demo_project)
    row = _by_uid(core.build_queue(session))["FR-0010"]   # default queue, not --all
    assert row.stale
    assert row.concern == "stale"                          # never conflated with ratified
    assert row.ratified_by == "alice"                      # whose signature is being replaced
    assert row.ratifiable_now                              # 'ratified' may always move to itself
    assert row.reratify_path is None                       # nothing to walk


def test_a_stale_item_counts_as_outstanding_not_as_ratified(demo_project):
    """A cockpit reporting full marks over an item the validator is erroring on is
    worse than one reporting nothing, because the reviewer stops looking."""
    session = core.open_session(demo_project)
    done, total = core.ratification_progress(session)
    core.ratify_item(session, "FR-0010", by="bob")         # accept the new wording
    assert core.ratification_progress(session) == (done + 1, total)


def test_a_stale_item_that_also_overshot_carries_the_reratify_route(demo_project):
    """FR-0011 was signed off, rewritten since, *and* advanced to 'implemented'. The
    round trip through ratified is the same one an overshoot uses — the difference is
    what the reviewer is told, not how it gets there."""
    session = core.open_session(demo_project)
    row = _by_uid(core.build_queue(session))["FR-0011"]
    assert row.concern == "stale" and row.stale
    assert not row.ratifiable_now
    assert row.reratify_path == ["implemented", "suspect", "ratified", "implemented"]


def test_re_signing_a_stale_item_rebinds_it_and_clears_the_concern(demo_project):
    session = core.open_session(demo_project)
    core.ratify_item(session, "FR-0010", by="bob")

    fresh = core.open_session(demo_project)
    item = fresh.project.get("FR-0010")
    assert item.attrs["ratified_by"] == "bob"              # alice's signature replaced
    assert item.attrs["ratified_fingerprint"] == _fingerprint_of(fresh.project, "FR-0010")
    assert "FR-0010" not in _by_uid(core.build_queue(fresh))
    assert _by_uid(core.build_queue(fresh, show_all=True))["FR-0010"].concern == "ratified"


def test_re_signing_a_stale_overshoot_restores_its_status(demo_project):
    session = core.open_session(demo_project)
    route = core.reratify_item(session, "FR-0011", by="bob")
    assert route == ["implemented", "suspect", "ratified", "implemented"]

    fresh = core.open_session(demo_project)
    item = fresh.project.get("FR-0011")
    assert item.status == "implemented"                    # exactly where it started
    assert item.attrs["ratified_fingerprint"] == _fingerprint_of(fresh.project, "FR-0011")
    assert "FR-0011" not in _by_uid(core.build_queue(fresh))


def test_staleness_is_judged_by_throughlines_own_fingerprint(demo_project):
    """Not by a rule of ours. A second answer to what counts as a content change would
    drift from the validator's, and the cockpit would then disagree with check about
    which items still need a human — so this drives a real edit, not a planted stamp."""
    session = core.open_session(demo_project)
    core.ratify_item(session, "FR-0001", by="alice")
    assert "FR-0001" not in _by_uid(core.build_queue(core.open_session(demo_project)))

    path = demo_project / "requirements" / "FR-0001.yml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "text: Body of FR-0001.", "text: Body of FR-0001, rewritten."),
        encoding="utf-8",
    )

    row = _by_uid(core.build_queue(core.open_session(demo_project)))["FR-0001"]
    assert row.concern == "stale" and row.ratified_by == "alice"


def test_the_stale_rows_are_exactly_what_throughline_calls_ratified_stale(demo_project):
    """The agreement itself, asserted directly: the cockpit's stale rows and check's
    ratified-stale findings are the same set of items."""
    from throughline.validate import validate

    session = core.open_session(demo_project)
    flagged = {f.uid for f in validate(session.project, strict=True)
               if f.rule == "ratified-stale"}
    shown = {r.uid for r in core.build_queue(session, show_all=True) if r.stale}
    assert flagged == shown == {"FR-0010", "FR-0011"}


def test_a_signature_written_before_fingerprints_existed_is_not_stale(demo_project):
    """FR-0006 carries a ratifier but no stamp — the whole back catalogue does. It
    cannot be judged, so it is left settled rather than accused."""
    session = core.open_session(demo_project)
    row = _by_uid(core.build_queue(session, show_all=True))["FR-0006"]
    assert not row.stale
    assert row.concern == "ratified"


def test_a_dead_item_is_dead_whatever_its_stamp_says(demo_project):
    """Staleness must not resurrect an invalidated item into the actionable backlog."""
    session = core.open_session(demo_project)
    core.reject_item(session, "FR-0010", reason="superseded")

    fresh = core.open_session(demo_project)
    assert "FR-0010" not in _by_uid(core.build_queue(fresh))
    row = _by_uid(core.build_queue(fresh, show_all=True))["FR-0010"]
    assert row.concern == "rejected"
    assert not row.stale and not row.ratifiable_now


def test_stale_sorts_below_the_unsigned_backlog_but_above_what_must_be_fixed(
    demo_project,
):
    session = core.open_session(demo_project)
    order = [r.uid for r in core.build_queue(session)]
    assert order.index("FR-0002") < order.index("FR-0010")   # ready(1) < stale(2)
    assert order.index("FR-0010") < order.index("FR-0007")   # stale(2) < blocked(3)
    assert order.index("FR-0007") < order.index("FR-0003")   # blocked(3) < ungrounded(4)


def test_ratifying_binds_the_signature_to_the_content_signed(demo_project):
    """The cockpit calls throughline's own ratify, so the whole record it stamps is
    written here too — not just who signed, but what they signed (SR-0022). Writing
    the ratifier alone left a signature bound to nothing."""
    session = core.open_session(demo_project)
    core.ratify_item(session, "FR-0001", by="tester")

    fresh = core.open_session(demo_project)
    item = fresh.project.get("FR-0001")
    assert item.attrs.get("ratified_by") == "tester"
    assert item.attrs.get("ratified_fingerprint") == _fingerprint_of(fresh.project, "FR-0001")


def test_reratifying_binds_the_signature_too_and_the_walk_does_not_stale_it(
    demo_project,
):
    """The route walks on past ratified to restore the item's status. That must not
    invalidate the stamp — the content fingerprint deliberately excludes status."""
    session = core.open_session(demo_project)
    core.reratify_item(session, "FR-0007", by="tester")

    fresh = core.open_session(demo_project)
    item = fresh.project.get("FR-0007")
    assert item.status == "implemented"          # walked on, as before
    assert item.attrs.get("ratified_fingerprint") == _fingerprint_of(fresh.project, "FR-0007")


def test_a_ratified_item_whose_content_has_not_changed_is_refused(demo_project):
    """throughline refuses a second sign-off that accepts nothing rather than
    silently replacing the record of who accepted it (throughline SR-0148). The
    cockpit's own copy allowed it; calling the real operation does not."""
    session = core.open_session(demo_project)
    core.ratify_item(session, "FR-0001", by="alice")
    with pytest.raises(core.RatifierError, match="already ratified by alice"):
        core.ratify_item(session, "FR-0001", by="bob")
    assert session.project.get("FR-0001").attrs["ratified_by"] == "alice"


def test_an_unbound_signature_can_be_bound_without_changing_anything_else(
    demo_project,
):
    """The back catalogue: an item carrying a ratifier but no fingerprint — every
    item this cockpit ever ratified — can be re-ratified in place to bind the
    signature, and nothing but the stamp moves."""
    session = core.open_session(demo_project)
    item = session.project.get("FR-0006")  # ratified_by alice, no fingerprint
    assert item.attrs.get("ratified_by") and "ratified_fingerprint" not in item.attrs
    before_status, before_text = item.status, item.text

    core.reratify_item(session, "FR-0006", by="alice")

    fresh = core.open_session(demo_project).project.get("FR-0006")
    assert fresh.status == before_status and fresh.text == before_text
    assert fresh.attrs["ratified_by"] == "alice"
    assert fresh.attrs["ratified_fingerprint"].startswith("sha256:")


def test_reratify_refuses_when_the_config_offers_no_route(demo_project):
    session = core.open_session(demo_project)
    # a directly-ratifiable item has no round-trip overshoot route
    with pytest.raises(core.RatifierError, match="no route"):
        core.reratify_item(session, "FR-0001", by="tester")
    # nor does an ungrounded one still sitting at proposed — routing is judged
    # first, and the cockpit never sends such an item down this path anyway
    with pytest.raises(core.RatifierError, match="no route"):
        core.reratify_item(session, "FR-0003", by="tester")


def test_reratify_surfaces_throughlines_own_refusal_and_leaves_the_item_alone(
    demo_project,
):
    """Where a route exists, the gates are throughline's to apply, not ours — its
    refusal is passed through as it stands, and a failure part-way along the route
    must leave the item exactly where it started (SR-0022)."""
    session = core.open_session(demo_project)
    session.project.get("FR-0007").attrs["ambiguous"] = True
    with pytest.raises(core.RatifierError, match="ambiguous"):
        core.reratify_item(session, "FR-0007", by="tester")
    assert session.project.get("FR-0007").status == "implemented"
    # nothing was written: the item on disk is untouched and still unratified
    fresh = core.open_session(demo_project).project.get("FR-0007")
    assert fresh.status == "implemented"
    assert core.RATIFIED_BY_ATTR not in fresh.attrs


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
    # proposed(0) < ready(1) < ungrounded(4) < ambiguous(5)
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


def test_the_offered_ratifier_is_throughlines_answer_not_ours(demo_project,
                                                              monkeypatch):
    """SR-0027: the identity offered where none was named is obtained by asking
    throughline, so the cockpit and the command line cannot offer different names
    to the same person on the same machine. Nothing about who is offered — not the
    source, not the fallback — is decided in this module."""
    import throughline.identity as identity
    seen = {}

    def _fake(path=None):
        seen["path"] = path
        return "Ada Lovelace"

    monkeypatch.setattr(identity, "default_ratifier", _fake)
    monkeypatch.setattr(core, "throughline_default_ratifier", _fake)
    assert core.default_ratifier(demo_project) == "Ada Lovelace"
    # The project is passed on, because the identity a repository signs with is a
    # property of that repository rather than of the machine.
    assert seen["path"] == demo_project


def test_a_stable_identifier_is_recorded_beside_the_name(demo_project):
    """SR-0028: a ratification taken in the cockpit carries the same record as the
    same ratification taken at the command line — the identifier in its own field,
    never conflated with the name."""
    session = core.open_session(demo_project)
    core.ratify_item(session, "FR-0001", by="Ada Lovelace", by_id="github:ada")

    fresh = core.open_session(demo_project)
    item = fresh.project.get("FR-0001")
    assert item.attrs.get("ratified_by") == "Ada Lovelace"
    assert item.attrs.get("ratified_id") == "github:ada"


def test_an_absent_identifier_stays_absent(demo_project):
    """Never invented, derived or defaulted — a guessed identity is worse than
    none, so the field simply is not written (SR-0028)."""
    session = core.open_session(demo_project)
    core.ratify_item(session, "FR-0001", by="Ada Lovelace")

    fresh = core.open_session(demo_project)
    assert "ratified_id" not in fresh.project.get("FR-0001").attrs


def test_a_malformed_identifier_is_refused_in_throughlines_words(demo_project):
    """Well-formedness is throughline's judgement, surfaced as it stands rather
    than re-argued here (SR-0028)."""
    assert core.normalise_identifier(None) is None
    assert core.normalise_identifier("email:ada@example.com") == "email:ada@example.com"
    with pytest.raises(core.RatifierError):
        core.normalise_identifier("ada@example.com")  # no scheme


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


# --------------------------------------------------------------------------- #
# SR-0024 — an item made suspect returns to the worklist
# --------------------------------------------------------------------------- #

def _uids(rows) -> set[str]:
    return {r.uid for r in rows}


def test_a_suspect_item_is_back_in_the_default_worklist(demo_project):
    """A previously-ratified item that a cascade made suspect is awaiting a human
    again, so it belongs in the queue the reviewer is already working through — not
    hidden behind the wide view by the very stamp the cascade called into question."""
    session = core.open_session(demo_project)
    core.ratify_item(session, "FR-0001", "Ada Lovelace")

    session = core.open_session(demo_project)
    assert "FR-0001" not in _uids(core.build_queue(session)), "ratified: settled"

    # reject something FR-0001 stands on, so the sign-off no longer holds
    core.reject_item(session, "INT-0001", "superseded")
    session = core.open_session(demo_project)
    item = session.project.get("FR-0001")
    assert item.status == session.suspect_status
    assert item.attrs.get("ratified_by") == "Ada Lovelace", "the stamp survives"
    assert "FR-0001" in _uids(core.build_queue(session)), "suspect: awaiting a human"


def test_a_stamped_item_that_moved_on_stays_out_of_the_worklist(demo_project):
    """The stamp test still does its original job: an item ratified and since advanced
    is not re-offered for a ratification its status can no longer accept (SR-0019)."""
    session = core.open_session(demo_project)
    item = session.project.get("FR-0007")   # overshot to 'implemented'
    item.attrs["ratified_by"] = "Ada Lovelace"
    assert core._is_ratified(session, item)


# --------------------------------------------------------------------------- #
# SR-0025 — a confirmation states the consequence it has actually computed
# --------------------------------------------------------------------------- #

def test_preview_reject_predicts_exactly_what_reject_does(demo_project):
    """The set shown before the question and the set produced after the answer are
    the same set. If these can drift the confirmation is boilerplate again."""
    session = core.open_session(demo_project)
    predicted = core.preview_reject(session, "INT-0001")
    assert predicted, "this rejection really does have dependents"

    session = core.open_session(demo_project)
    actual = core.reject_item(session, "INT-0001", "superseded")
    assert sorted(actual) == sorted(predicted)


def test_preview_reject_excludes_dependents_that_cannot_become_suspect(demo_project):
    """Reachability is not consequence. FR-0001 is reachable from INT-0001 but sits at
    'proposed', which this project's [transitions] give no route to suspect, so the
    cascade leaves it alone and the confirmation must not claim it."""
    session = core.open_session(demo_project)
    idx = Index.build(session.project)
    assert "FR-0001" in idx.impact("INT-0001"), "reachable"
    assert "FR-0001" not in core.preview_reject(session, "INT-0001"), "but untouched"


# --------------------------------------------------------------------------- #
# SR-0037 — a rejection reports the dependents it could not flag
# --------------------------------------------------------------------------- #

def test_reject_names_the_dependents_it_could_not_flag(demo_project):
    """FR-0001 is reachable from INT-0001 but sits at 'proposed', which this project's
    [transitions] give no route to suspect. Its footing goes and nothing on it records
    that, which is precisely the drift the cockpit exists to surface — so the rejection
    names it and the move that was refused, rather than quietly returning a shorter
    list of successes."""
    session = core.open_session(demo_project)
    outcome = core.reject_item(session, "INT-0001", "superseded")

    assert "FR-0001" not in outcome, "it was not flagged, so it is not reported as flagged"
    refused = {r.uid: (r.frm, r.to) for r in outcome.refused}
    assert refused.get("FR-0001") == ("proposed", session.suspect_status)


def test_reject_does_not_report_an_already_dead_dependent_as_refused(demo_project):
    """Nothing was withheld from an item that has already gone, so it is neither
    flagged nor refused. Reporting it would send the reviewer after a non-problem."""
    session = core.open_session(demo_project)
    core.reject_item(session, "FR-0001", "not needed")

    session = core.open_session(demo_project)
    outcome = core.reject_item(session, "INT-0001", "superseded")
    assert "FR-0001" not in outcome
    assert "FR-0001" not in {r.uid for r in outcome.refused}


def test_preview_reject_is_read_only(demo_project):
    """It is called before the human has answered, so it must change nothing."""
    session = core.open_session(demo_project)
    before = {i.uid: i.status for i in session.project.items()}
    core.preview_reject(session, "INT-0001")
    assert {i.uid: i.status for i in session.project.items()} == before
    assert {i.uid: i.status for i in core.open_session(demo_project).project.items()} == before


def test_preview_reject_says_nothing_is_affected_when_nothing_is(demo_project):
    """The empty answer is as much of the requirement as the populated one — it is the
    answer that most changes how freely a person can act."""
    session = core.open_session(demo_project)
    assert core.preview_reject(session, "FR-0006") == []


def test_preview_reject_refuses_an_unknown_uid(demo_project):
    session = core.open_session(demo_project)
    with pytest.raises(core.RatifierError, match="does not exist"):
        core.preview_reject(session, "NOPE-9999")
