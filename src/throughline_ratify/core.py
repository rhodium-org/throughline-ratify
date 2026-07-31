# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""The engine behind throughline-ratify.

This module owns everything that touches a throughline graph; the TUI
(:mod:`throughline_ratify.tui`) is a pure view over the values it
produces. It is deliberately compose-aware: when the project declares
``[[sources]]`` it grounds each item over the *composed union* — exactly as
``tl-compose ratify`` does — so an item whose grounding chain reaches a root only
through a borrowed clause is seen as grounded, not orphaned. Writes only ever land
on the consumer's own registers; a composed source is a read-only view.

Every status change routes through throughline's own config-driven choke points
(:func:`throughline.grounding.set_status`, :func:`throughline.grounding.invalidate`),
so no status literal is hardcoded here — the project's ``[status.roles]`` and
``[transitions]`` govern what "ratified", "rejected" and "suspect" mean and which
moves are legal.

Ratification itself is throughline's :func:`throughline.grounding.ratify`, called
rather than copied (SR-0022). We hand it our union index and it writes the whole
accountability record — who accepted the item *and* a fingerprint of what they
accepted. A copy of that operation lived here once, and when throughline began
binding signatures to content the copy silently fell behind, leaving every item
ratified through this cockpit signed but unbound. One implementation, not two.
"""
from __future__ import annotations

import getpass
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from throughline.graph import Index
from throughline.grounding import (
    GroundingError,
    invalidate,
    reaches_root,
    set_status,
)
# The real ratification operation (SR-0022). We do not reimplement it: it decides
# what may be signed off and what gets recorded, and it accepts a prebuilt
# grounding index (throughline SR-0151) so we can hand it our composed-union view
# while it writes to the consumer's own item.
from throughline.grounding import ratify as core_ratify
from throughline.model import Item, Project
from throughline.schema import SchemaError
from throughline.storage import (
    CONFIG_NAME,
    ProjectError,
    load_project,
    write_item,
)

# Compose is a hard dependency (it re-exports the throughline core), so these are
# always importable. parse_sources/build_union are the public composition API.
from throughline_compose.sources import SourceError, parse_sources
from throughline_compose.union import ComposeError, build_union

# is_namespace_qualified tells a source reference (``asvs:SR-0195``) from a local
# one (``UR-0004``). Guarded: if compose renames it we degrade to a colon heuristic
# rather than crashing.
try:
    from throughline_compose.union import is_namespace_qualified as _is_ns_qualified
except Exception:  # pragma: no cover
    def _is_ns_qualified(ref: str) -> bool:
        return ":" in ref

# _resolve_sources carries tl-compose's full resolution semantics (remote fetch,
# path sources, one-level re-export, two-edition conflict detection). It is the
# same code path tl-compose's own ratify uses, so reusing it keeps our grounding
# view byte-identical to the CLI's. Guarded so a future rename degrades to the
# public single-hop resolver rather than crashing.
try:  # pragma: no cover - exercised via the composed-project path
    from throughline_compose.cli import _resolve_sources as _compose_resolve_sources
except Exception:  # pragma: no cover
    _compose_resolve_sources = None


class RatifierError(RuntimeError):
    """A user-facing failure the TUI should surface without a traceback."""


# The attribute ``tl ratify`` stamps on an item to record who took accountability.
# It is the durable proof an item was ratified: unlike the ``ratified`` *status*,
# it survives the item advancing to ``implemented``/``verified``, so it — not the
# current status alone — tells us an item has already been signed off.
RATIFIED_BY_ATTR = "ratified_by"


# --------------------------------------------------------------------------- #
# Semantic concerns — what colour/icon a row earns, and how it sorts.
# --------------------------------------------------------------------------- #

# concern key -> (icon, sort rank). Lower rank sorts first (most actionable up
# top, then the things a human must fix before they *can* sign off).
CONCERNS: dict[str, tuple[str, int]] = {
    "proposed": ("\u25cf", 0),   # ● AI-proposed, awaiting a human — the core case
    "ready": ("\u25c9", 1),      # ◉ already human-approved, one move from ratified
    "blocked": ("\u25cb", 2),    # ○ pending but not directly ratifiable yet
    "ungrounded": ("\u26a0", 3),  # ⚠ reaches no root — must be linked before sign-off
    "ambiguous": ("\u2691", 4),  # ⚑ flagged ambiguous — must be clarified first
    "ratified": ("\u2713", 5),   # ✓ already signed off — done (only shown under --all)
    # Dead items — kept for the record, shown only under --all and never actionable.
    "rejected": ("\u2717", 6),   # ✗ invalidated (rejected) — retained, not signed off
    "deleted": ("\u2620", 7),    # ☠ tombstoned (soft-deleted) — retained for history
}

# The orderings the queue can be sorted by (SR-0011). "concern" is the default
# most-actionable-first ranking; "roots"/"leaves" walk grounding depth so a large
# graph can be worked top-down (roots first) or bottom-up (leaves first).
SORTS = ("concern", "roots", "leaves")


@dataclass
class LinkView:
    """One outgoing link of a queued item, resolved over the composed union. The
    reference is kept exactly as authored (``asvs:SR-0195`` for a source clause,
    ``UR-0004`` for a local one) while the title and body are looked up through the
    union, so a reviewer can read what an external reference actually says."""

    type: str
    ref: str                    # display reference, as authored
    title: str | None = None    # resolved title, or None if it resolves to nothing
    text: str = ""              # resolved body — lets the reviewer read the source clause
    target_type: str = ""       # resolved item type (for the expanded view)
    target_status: str = ""     # resolved item status (for the expanded view)
    external: bool = False      # borrowed from a composed source (namespace-qualified)
    namespace: str | None = None
    source_ref: str = ""        # target's authoritative clause reference (attrs.source_ref)

    @property
    def resolved(self) -> bool:
        return self.title is not None


@dataclass
class QueueItem:
    """One row in the ratification queue — a flattened, display-ready view of a
    local item plus everything the TUI needs to colour and act on it."""

    uid: str
    title: str
    type: str
    status: str
    concern: str
    grounded: bool
    ambiguous: bool
    ratifiable_now: bool
    text: str
    rationale: str
    links: list[LinkView]
    depth: int | None = None  # hops to the nearest root; None if ungrounded
    # For an item that overshot ratification (its status can no longer move straight
    # to ratified) yet was never signed off: the config-permitted status itinerary
    # that records the missed ratification and restores its status. None otherwise.
    reratify_path: list[str] | None = None
    # Why a dead (rejected) item was invalidated, if it recorded a reason. Empty
    # for live items and for tombstones with no reason.
    reason: str = ""

    @property
    def icon(self) -> str:
        return CONCERNS.get(self.concern, ("\u25cb", 9))[0]


@dataclass
class SourceInfo:
    namespace: str
    location: str


@dataclass
class Session:
    """A loaded project ready to ratify against. Holds both the writable consumer
    graph and the (possibly identical) union view used for grounding."""

    root: Path
    project: Project           # the local, writable consumer graph
    union: Project             # union view for grounding (== project if not composed)
    ratified_status: str
    proposed_status: str
    composed: bool
    sources: list[SourceInfo] = field(default_factory=list)
    _index: Index | None = None

    @property
    def schema(self):
        return self.project.schema

    @property
    def index(self) -> Index:
        # Grounding topology is link-based and independent of status, so one index
        # built over the union survives every ratify/reject in a session.
        if self._index is None:
            self._index = Index.build(self.union)
        return self._index

    @property
    def project_name(self) -> str:
        return self.project.config.get("project", {}).get("name") or self.root.name


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #

def _find_root(start: Path) -> Path | None:
    """The nearest directory at or above ``start`` that holds a throughline.toml,
    so ``tl-ratify`` works from anywhere inside a project like ``git`` does."""
    base = start if start.is_dir() else start.parent
    for d in (base, *base.parents):
        if (d / CONFIG_NAME).exists():
            return d
    return None


def open_session(path: str | Path) -> Session:
    """Open the throughline project enclosing ``path`` (walking upward like
    ``git``), composing its sources when it declares any."""
    start = Path(path).resolve()
    root = _find_root(start)
    if root is None:
        raise RatifierError(
            f"no throughline.toml at or above {start} — not inside a throughline project")

    try:
        consumer = load_project(root)
    except ProjectError as exc:
        raise RatifierError(str(exc)) from exc

    try:
        schema = consumer.schema
        ratified = schema.status_role("ratified")
        proposed = schema.status_role("proposed")
    except SchemaError as exc:
        raise RatifierError(
            f"{root / CONFIG_NAME}: {exc}. tl-ratify needs to know which statuses play the "
            "'proposed' and 'ratified' roles — declare them under [status.roles] "
            "(run `tl migrate` to backfill roles on an older project)."
        ) from exc

    union, sources = _compose_if_declared(consumer, root)
    return Session(
        root=root,
        project=consumer,
        union=union,
        ratified_status=ratified,
        proposed_status=proposed,
        composed=bool(sources),
        sources=sources,
    )


def _compose_if_declared(consumer: Project, root: Path) -> tuple[Project, list[SourceInfo]]:
    """Return the graph to ground against and a summary of composed sources. With
    no ``[[sources]]`` the consumer is its own union (pure ``tl`` behaviour)."""
    try:
        declared = parse_sources(consumer)
    except SourceError as exc:
        raise RatifierError(str(exc)) from exc
    if not declared:
        return consumer, []

    try:
        if _compose_resolve_sources is not None:
            res = _compose_resolve_sources(declared, root)
            union = build_union(consumer, res.projects(), res.ns_aliases)
            infos = [SourceInfo(ns, res.locations.get(ns, "")) for ns in sorted(res.resolved)]
        else:  # pragma: no cover - fallback for a future compose internals rename
            union, infos = _compose_public_fallback(consumer, declared, root)
    except (ComposeError, Exception) as exc:  # noqa: BLE001 - report any resolve failure cleanly
        if isinstance(exc, RatifierError):
            raise
        raise RatifierError(f"could not compose sources: {exc}") from exc
    return union.project, infos


def _compose_public_fallback(consumer, declared, root):  # pragma: no cover
    """Single-hop resolution via the public API only (no re-export handling)."""
    from throughline_compose.resolve import resolve_source
    from throughline.storage import read_project

    projects: dict[str, Project] = {}
    infos: list[SourceInfo] = []
    for src in declared:
        resolved_path = resolve_source(src, root)
        projects[src.namespace] = read_project(resolved_path)
        loc = f"{src.url}@{src.ref}" if src.is_remote else f"path {src.path}"
        infos.append(SourceInfo(src.namespace, loc))
    union = build_union(consumer, projects)
    return union, sorted(infos, key=lambda s: s.namespace)


# --------------------------------------------------------------------------- #
# The queue
# --------------------------------------------------------------------------- #

def build_queue(
    session: Session, *, show_all: bool = False, sort: str = "concern"
) -> list[QueueItem]:
    """The ratification worklist: by default every local item that is neither already
    ratified nor dead, ranked most-actionable first. ``show_all`` widens the view to
    the whole local graph — already-ratified items *and* dead (rejected/tombstoned)
    items become visible too, so a reviewer can see what they invalidated instead of
    it silently vanishing. ``sort`` chooses the ordering — ``"concern"`` (default),
    ``"roots"`` (shallowest grounding depth first) or ``"leaves"`` (deepest first);
    see :data:`SORTS`."""
    if sort not in SORTS:
        raise RatifierError(f"unknown sort {sort!r}; choose one of {', '.join(SORTS)}")
    schema = session.schema
    dead = schema.dead_statuses()
    depths = _grounding_depths(session)
    rows: list[QueueItem] = []

    for item in session.project.items():
        is_dead = item.status in dead
        is_ratified = _is_ratified(session, item)
        # The default queue is the actionable backlog: hide the settled outcomes
        # (already ratified) and the dead. show_all keeps everything for review.
        if not show_all and (is_dead or is_ratified):
            continue

        rows.append(_evaluate(session, item, is_ratified, is_dead, depths.get(item.uid)))

    _sort_rows(rows, sort)
    return rows


def _is_ratified(session: Session, item: Item) -> bool:
    """Whether ``item`` has already been signed off. True if it currently holds the
    ratified status *or* carries the ratification stamp — the latter catching an item
    that was ratified and has since advanced to ``implemented``/``verified``, so it is
    not wrongly re-offered for a ratification its status can no longer accept."""
    return (
        item.status == session.ratified_status
        or bool(item.attrs.get(RATIFIED_BY_ATTR))
    )


def _dead_concern(schema, status: str) -> str:
    """Which dead concern a status earns, decided from the project's own
    ``[status.roles]``: the ``tombstone`` role reads as ``"deleted"``, every other
    dead status (the ``invalidated`` role) as ``"rejected"``. No status name is
    assumed — an undeclared tombstone role simply means everything dead is rejected."""
    roles = schema.status_roles or {}
    if status == roles.get("tombstone"):
        return "deleted"
    return "rejected"


def _sort_rows(rows: list[QueueItem], sort: str) -> None:
    """Order the queue in place. Ungrounded items (no depth) always sort last so
    they never masquerade as roots or leaves."""
    if sort == "roots":
        rows.sort(key=lambda r: (r.depth is None, r.depth or 0, r.uid))
    elif sort == "leaves":
        rows.sort(key=lambda r: (r.depth is None, -(r.depth or 0), r.uid))
    else:  # concern
        rows.sort(key=lambda r: (CONCERNS.get(r.concern, ("", 9))[1], r.uid))


def _grounding_depths(session: Session) -> dict[str, int]:
    """Shortest number of grounding hops from each item down to a root, computed
    over the composed union so borrowed chains are measured the same as local ones.
    Roots are depth 0; items that never reach a root are absent (ungrounded)."""
    from collections import deque

    idx = session.index
    schema = session.schema
    ground = schema.ground_link_types
    depth: dict[str, int] = {}
    q: deque[str] = deque()
    for it in session.union.items():
        if schema.is_root(it):
            depth[it.uid] = 0
            q.append(it.uid)
    while q:
        cur = q.popleft()
        d = depth[cur] + 1
        for child, _k in idx.in_links(cur, ground):
            if depth.get(child, d + 1) > d:
                depth[child] = d
                q.append(child)
    return depth


def ratification_progress(session: Session) -> tuple[int, int]:
    """``(ratified, gradable)`` over the local, non-dead items — the figure a human
    watches climb as they sign off. Counts the whole project, not just the filtered
    queue, so ratifying a row makes the number move even when it then leaves view."""
    schema = session.schema
    dead = schema.dead_statuses()
    ratified = gradable = 0
    for item in session.project.items():
        if item.status in dead:
            continue
        gradable += 1
        if _is_ratified(session, item):
            ratified += 1
    return ratified, gradable


def _evaluate(
    session: Session, item: Item, is_ratified: bool, is_dead: bool, depth: int | None
) -> QueueItem:
    schema = session.schema
    union_item = session.union.get(item.uid) or item
    grounded = schema.is_root(union_item) or reaches_root(session.index, schema, item.uid)
    ambiguous = bool(item.attrs.get("ambiguous"))
    directly = schema.allows_transition(item.status, session.ratified_status)
    # A dead item is never actionable, whatever stamp it may still carry.
    ratifiable_now = (
        directly and grounded and not ambiguous and not is_ratified and not is_dead
    )

    if is_dead:
        # Invalidated/tombstoned — surfaced only under show_all, for the record. This
        # takes precedence over any lingering ratified stamp: it is now dead.
        concern = _dead_concern(schema, item.status)
    elif is_ratified:
        concern = "ratified"  # done — only appears under show_all
    elif ambiguous:
        concern = "ambiguous"
    elif not grounded:
        concern = "ungrounded"
    elif not directly:
        concern = "blocked"
    elif item.status == session.proposed_status:
        concern = "proposed"
    else:
        concern = "ready"  # approved, one move from ratified

    # A blocked item is grounded and unambiguous but cannot move straight to ratified
    # — usually because it advanced past it without ever being signed off. Offer a
    # re-ratify route only when this project's own transitions permit one.
    reratify_path = _reratify_route(session, item) if concern == "blocked" else None

    return QueueItem(
        uid=item.uid,
        title=item.title,
        type=item.type,
        status=item.status,
        concern=concern,
        grounded=grounded,
        ambiguous=ambiguous,
        ratifiable_now=ratifiable_now,
        text=item.text,
        rationale=item.rationale,
        links=_resolve_links(session, item),
        depth=depth,
        reratify_path=reratify_path,
        reason=str(item.attrs.get("invalidated_reason") or ""),
    )


def _resolve_links(session: Session, item: Item) -> list[LinkView]:
    """Resolve each link over the composed union while showing the reference as
    authored. The union's own copy of the item carries link targets already
    rewritten to their mangled union UIDs (``asvs:SR-0195`` -> ``ASVSSR-0195``), so
    we look content up through those, but display the consumer's original reference
    so a source clause still reads as ``asvs:SR-0195``."""
    union_item = session.union.get(item.uid)
    # union link order matches the consumer's (compose rewrites in place), so we can
    # pair the authored reference with its resolvable union target positionally.
    union_targets = [ln.target for ln in union_item.links] if union_item is not None else None

    out: list[LinkView] = []
    for i, link in enumerate(item.links):
        ref = link.target
        lookup = union_targets[i] if union_targets and i < len(union_targets) else ref
        target_item = session.union.get(lookup)
        external = _is_ns_qualified(ref)
        out.append(LinkView(
            type=link.type,
            ref=ref,
            title=target_item.title if target_item is not None else None,
            text=(target_item.text if target_item is not None else ""),
            target_type=(target_item.type if target_item is not None else ""),
            target_status=(target_item.status if target_item is not None else ""),
            external=external,
            namespace=ref.split(":", 1)[0] if external else None,
            source_ref=_source_ref_of(target_item),
        ))
    return out


def _source_ref_of(target_item) -> str:
    """The authoritative clause reference a composed item cites (``attrs.source_ref``),
    e.g. an ASVS clause id — far more useful to a reviewer than the namespace label."""
    if target_item is None:
        return ""
    attrs = getattr(target_item, "attrs", None) or {}
    ref = attrs.get("source_ref")
    return str(ref) if ref else ""


# --------------------------------------------------------------------------- #
# Re-ratification routing — entirely derived from the project's own transitions.
# --------------------------------------------------------------------------- #

def _transition_path(
    schema, src: str, dst: str, blocked: frozenset[str]
) -> list[str] | None:
    """The shortest legal status itinerary ``[src, …, dst]`` using only this
    project's declared ``[transitions]``, never routing through a ``blocked`` status
    (except as the destination itself). ``None`` when no such path exists.

    This reads the transition table the project itself declares — nothing about
    "suspect" or any other status is assumed here; whether a round-trip back to
    ``ratified`` is even possible is a property of the config, not of this code."""
    from collections import deque

    transitions = schema.transitions
    if transitions is None:
        # Unconstrained lifecycle: every move is legal, so a single hop suffices.
        return [src] if src == dst else [src, dst]
    if src == dst:
        return [src]

    prev: dict[str, str | None] = {src: None}
    q: deque[str] = deque([src])
    while q:
        cur = q.popleft()
        if cur == dst:
            break
        for nxt in transitions.get(cur, frozenset()):
            if nxt in prev:
                continue
            if nxt in blocked and nxt != dst:
                continue
            prev[nxt] = cur
            q.append(nxt)
    if dst not in prev:
        return None
    out: list[str] = []
    node: str | None = dst
    while node is not None:
        out.append(node)
        node = prev[node]
    out.reverse()
    return out


def _reratify_route(session: Session, item: Item) -> list[str] | None:
    """For an item that overshot ratification — grounded and unambiguous, but whose
    current status can no longer move straight to ratified — the full status
    itinerary that revisits ratified and returns to where it is now, computed purely
    from the project's ``[transitions]``. ``None`` when the config offers no such
    round-trip, in which case no re-ratify affordance is shown.

    The itinerary is ``current → … → ratified → … → current``; persisting only its
    end state leaves the item exactly where it was but now carrying the ratification
    stamp, honouring the missed sign-off without a fabricated status change."""
    schema = session.schema
    start = item.status
    ratified = session.ratified_status
    if start == ratified:
        return None
    blocked = schema.dead_statuses()
    out_leg = _transition_path(schema, start, ratified, blocked)
    if out_leg is None:
        return None
    back_leg = _transition_path(schema, ratified, start, blocked)
    if back_leg is None:
        return None
    # Splice the legs, dropping the shared ``ratified`` pivot from the return leg.
    return out_leg + back_leg[1:]


# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #

def default_ratifier() -> str:
    try:
        return getpass.getuser()
    except Exception:  # pragma: no cover - unusual environments
        return "unknown"


def ratify_item(session: Session, uid: str, by: str) -> None:
    """Take human accountability for ``uid``, grounding over the composed union.

    The sign-off itself is throughline's own :func:`throughline.grounding.ratify`
    (SR-0022) — we hand it the union's grounding index so a chain that reaches a
    root only through a source counts, and it writes the whole accountability
    record onto the consumer's own item. Nothing about who may be ratified, or
    what gets stamped, is decided here; a refusal it raises is surfaced as it
    stands. Only the consumer's register is written; a composed source stays
    read-only."""
    if session.project.get(uid) is None:
        raise RatifierError(f"{uid} does not exist")
    try:
        item = core_ratify(session.project, uid, by, index=session.index)
    except GroundingError as exc:
        raise RatifierError(str(exc)) from exc
    write_item(item, session.project.register_of(uid))


def reratify_item(session: Session, uid: str, by: str) -> list[str]:
    """Retrospectively record the ratification an item overshot, then restore its
    current status — for a grounded, unambiguous item whose status advanced past
    ratified without ever being signed off.

    Every hop is walked through throughline's own :func:`set_status` choke point, so
    each step is validated against the project's ``[transitions]`` exactly as the CLI
    would — except the hop that lands on ratified, which is handed to throughline's
    own ratify (SR-0022). That keeps the sign-off, and the whole record it stamps,
    the tool's rather than ours: we only get the item *to* the point of ratification,
    never perform it. Only the end state is written, and it equals the item's original
    status — the item ends up precisely where it started, now carrying the full
    ratification stamp. Walking on afterwards does not stale the signature: the
    content fingerprint deliberately excludes status. Returns the status itinerary
    that was walked, for the caller to report."""
    item = session.project.get(uid)
    if item is None:
        raise RatifierError(f"{uid} does not exist")

    route = _reratify_route(session, item)
    if route is None:
        raise RatifierError(
            f"{uid} is at '{item.status}', from which this project's transitions offer "
            "no route back through ratified"
        )

    schema = session.schema
    pivot = route.index(session.ratified_status)
    was = item.status
    try:
        # Up to, but not including, the hop onto ratified — that one is not ours.
        for to in route[1:pivot]:
            set_status(schema, item, to)
        # throughline moves it the last step and records who accepted what. Its
        # gates (ambiguous, ungrounded, unchanged-already-ratified) bite here.
        core_ratify(session.project, uid, by, index=session.index)
        for to in route[pivot + 1:]:
            set_status(schema, item, to)
    except GroundingError as exc:
        # A refusal part-way along must not leave the in-memory item stranded at an
        # intermediate status the ratifier never chose. Nothing was written, so
        # restoring where it started makes the failure a true no-op.
        item.status = was
        raise RatifierError(str(exc)) from exc
    write_item(item, session.project.register_of(uid))
    return route


def reject_item(session: Session, uid: str, reason: str = "") -> list[str]:
    """Reject (invalidate) ``uid`` and cascade suspicion to its dependents, then
    persist every touched local item. Returns the affected UIDs."""
    if session.project.get(uid) is None:
        raise RatifierError(f"{uid} does not exist")
    try:
        affected = invalidate(session.project, uid, reason)
    except GroundingError as exc:
        raise RatifierError(str(exc)) from exc

    write_item(session.project.get(uid), session.project.register_of(uid))
    for aid in affected:
        dep = session.project.get(aid)
        if dep is not None:
            write_item(dep, session.project.register_of(aid))
    return affected


def remove_link(session: Session, uid: str, index: int) -> LinkView:
    """Remove the ``index``-th link from a *local* item and persist through
    throughline's own writer — never a hand-edit.

    throughline has no ``unlink`` op, so this is the ratify/reject pattern applied
    to a link: mutate the model, then :func:`throughline.storage.write_item` to the
    consumer's own register (a composed source stays read-only). Removing a
    *grounding* link is refused when it would leave the item reaching no root, so
    the graph can't be silently orphaned; informational links are always removable."""
    item = session.project.get(uid)
    if item is None:
        raise RatifierError(f"{uid} does not exist")
    if not 0 <= index < len(item.links):
        raise RatifierError(f"{uid} has no link at position {index}")

    link = item.links[index]
    view = _resolve_links(session, item)[index]
    schema = session.schema
    if link.type in schema.ground_link_types:
        union_item = session.union.get(uid) or item
        if not schema.is_root(union_item) and not _union_reaches_root_excluding(
            session, uid, index
        ):
            raise RatifierError(
                f"removing {link.type} \u2192 {link.target} would leave {uid} "
                "grounded to no root; link it elsewhere first"
            )

    del item.links[index]
    write_item(item, session.project.register_of(uid))
    # Keep the in-memory union view in step so the pane updates without a reload.
    # When the project isn't composed, union *is* project (same object) — the delete
    # above already applied, so only touch a distinct union copy.
    if session.composed:
        union_item = session.union.get(uid)
        if union_item is not None and index < len(union_item.links):
            del union_item.links[index]
    session._index = None  # topology changed; force a rebuild on next access
    return view


def _union_reaches_root_excluding(session: Session, uid: str, exclude: int) -> bool:
    """True if ``uid`` still reaches a root over the grounding links *other than*
    its ``exclude``-th one, evaluated over the composed union. Only the start item's
    edge set changes, so every deeper hop reuses the prebuilt index."""
    idx = session.index
    schema = session.schema
    ground = schema.ground_link_types
    start = session.union.get(uid)
    if start is None:
        return False
    stack = [
        ln.target
        for j, ln in enumerate(start.links)
        if j != exclude and ln.type in ground
    ]
    seen: set[str] = set()
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        it = session.union.get(cur)
        if it is None:
            continue
        if schema.is_root(it):
            return True
        stack.extend(t for t, _k in idx.out_links(cur, ground))
    return False
