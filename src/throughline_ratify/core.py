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

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

try:  # pragma: no cover - 3.11+ has it in the stdlib; the floor is 3.11
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

from throughline.fingerprint import fingerprint
from throughline.graph import Index
# Who is offered, and what a stable identifier may look like, are throughline's
# answers rather than ours (SR-0027, SR-0028). We import them; we do not restate
# them, so the cockpit cannot drift from the command line.
from throughline.identity import IdentityError
from throughline.identity import default_ratifier as throughline_default_ratifier
from throughline.identity import normalise_identifier as throughline_normalise_identifier
from throughline.grounding import (
    GroundingError,
    Refusal,
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

# The companion attribute holding a fingerprint of the content that was accepted.
# Comparing it with the content's fingerprint now is what tells a signature that
# still covers its item from one the wording has moved out from under (SR-0030).
RATIFIED_FINGERPRINT_ATTR = "ratified_fingerprint"


# --------------------------------------------------------------------------- #
# Semantic concerns — what colour/icon a row earns, and how it sorts.
# --------------------------------------------------------------------------- #

# concern key -> (icon, sort rank). Lower rank sorts first (most actionable up
# top, then the things a human must fix before they *can* sign off).
CONCERNS: dict[str, tuple[str, int]] = {
    "proposed": ("\u25cf", 0),   # ● AI-proposed, awaiting a human — the core case
    "ready": ("\u25c9", 1),      # ◉ already human-approved, one move from ratified
    "stale": ("\u21ba", 2),      # ↺ signed off, but the wording has moved since
    "blocked": ("\u25cb", 3),    # ○ pending but not directly ratifiable yet
    "ungrounded": ("\u26a0", 4),  # ⚠ reaches no root — must be linked before sign-off
    "ambiguous": ("\u2691", 5),  # ⚑ flagged ambiguous — must be clarified first
    "ratified": ("\u2713", 6),   # ✓ already signed off — done (only shown under --all)
    # Dead items — kept for the record, shown only under --all and never actionable.
    "rejected": ("\u2717", 7),   # ✗ invalidated (rejected) — retained, not signed off
    "deleted": ("\u2620", 8),    # ☠ tombstoned (soft-deleted) — retained for history
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
    # A sign-off that still stands but no longer covers the item's content — the
    # state throughline's check reports as ``ratified-stale`` (SR-0030). Ratifying
    # again is what clears it, so such an item is actionable, not settled.
    stale: bool = False
    # Who took accountability, when the item carries a sign-off. Named on a stale
    # row so the reviewer can see whose signature they are about to replace.
    ratified_by: str = ""

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
    def suspect_status(self) -> str | None:
        """The status this project binds to the ``suspect`` role, or ``None`` when it
        binds none. Unlike the ratified and proposed roles (SR-0009) suspicion is
        optional vocabulary, so its absence degrades inertly rather than refusing to
        open the project — the same treatment ``dead_statuses`` gives its own roles."""
        try:
            return self.schema.status_role("suspect")
        except SchemaError:
            return None

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


# How far beneath the given path the search for graphs reaches. A constant rather
# than a setting: SR-0026 forbids the assistant carrying configuration of its own,
# and this is deep enough for the layouts the requirement is about (``idd/`` at a
# repository root, ``packages/<name>/idd`` in a monorepo).
_MAX_SEARCH_DEPTH = 5


@dataclass(frozen=True)
class Candidate:
    """A graph found beneath the path the reviewer gave (SR-0045).

    Carries only what the choice needs — enough to name the graph and to open it.
    Nothing here loads the project's items or resolves its sources; SR-0048 keeps
    that work for the one graph the reviewer picks.
    """

    root: Path
    name: str
    rel: str    # display path, relative to the path searched


class AmbiguousProjectError(RatifierError):
    """More than one graph lies beneath the given path, so which to open is the
    reviewer's to say (SR-0045). Carries the candidates so the caller can offer
    them — interactively (SR-0048) or by refusing with them named (SR-0047)."""

    def __init__(self, base: Path, candidates: list[Candidate]) -> None:
        super().__init__(
            f"{len(candidates)} throughline projects found beneath {base} — "
            "which one to ratify against is yours to choose")
        self.base = base
        self.candidates = candidates


def _project_name_of(root: Path) -> str:
    """The project's declared name, read from its config alone.

    Deliberately not via ``load_project``: naming a candidate must not read the
    items of a graph the reviewer has not chosen (SR-0048). A config that cannot
    be read falls back to the directory name — discovery lists graphs, and it is
    opening one that judges whether it is sound (SR-0009).
    """
    try:
        config = tomllib.loads((root / CONFIG_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return root.name
    return config.get("project", {}).get("name") or root.name


def _declared_path_sources(root: Path) -> set[Path]:
    """Local directories this graph declares as sources.

    Read through compose's own ``parse_sources`` rather than by picking the array
    apart here, so the two can never hold different accounts of what a source
    declaration means (SR-0026). It only needs the config, so a stand-in carrying
    one avoids loading the graph.
    """
    try:
        config = tomllib.loads((root / CONFIG_NAME).read_text(encoding="utf-8"))
        declared = parse_sources(SimpleNamespace(config=config))
    except (OSError, ValueError, SourceError):
        return set()
    return {
        (root / src.path).resolve()
        for src in declared
        if not src.is_remote and src.path
    }


def _vcs_ignored(base: Path, dirs: list[Path]) -> set[Path]:
    """Which of ``dirs`` the repository ignores, asked of git rather than answered
    from a list of directory names kept here (SR-0046).

    A tree that is not a repository, or a machine with no git, yields nothing
    ignored — the walk then relies on its other exclusions rather than refusing.
    """
    if not dirs:
        return set()
    try:
        proc = subprocess.run(
            ["git", "-C", str(base), "check-ignore", "--stdin"],
            input="\n".join(str(d) for d in dirs),
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    return {Path(line).resolve() for line in proc.stdout.splitlines() if line.strip()}


def _is_excluded(d: Path) -> bool:
    """A directory the search never enters — one that cannot hold a graph the
    reviewer owns (SR-0046). Dot-directories cover ``.git`` and ``.venv``;
    ``pyvenv.cfg`` catches a virtualenv that is not named like one."""
    return (
        d.name.startswith(".")
        or d.is_symlink()
        or (d / "pyvenv.cfg").exists()
    )


def discover_projects(path: str | Path) -> list[Candidate]:
    """Every graph at or beneath ``path``, in the order they should be offered.

    Breadth-first to ``_MAX_SEARCH_DEPTH``, pruning what SR-0046 excludes as the
    walk descends rather than filtering at the end, so an ignored directory costs
    nothing to skip. A graph an enclosing candidate declares as a source is
    dropped: composition gives a wider view, never a wider authority, so offering
    one as a peer would present a graph on which every decision is then refused.
    """
    base = Path(path).resolve()
    if not base.is_dir():
        base = base.parent

    roots: list[Path] = []
    if (base / CONFIG_NAME).exists():
        roots.append(base)

    level = [base]
    for _ in range(_MAX_SEARCH_DEPTH):
        children: list[Path] = []
        for parent in level:
            try:
                children.extend(
                    c for c in sorted(parent.iterdir())
                    if c.is_dir() and not _is_excluded(c)
                )
            except OSError:
                continue
        if not children:
            break
        ignored = _vcs_ignored(base, children)
        children = [c for c in children if c not in ignored]
        roots.extend(c for c in children if (c / CONFIG_NAME).exists())
        level = children

    borrowed: set[Path] = set()
    for root in roots:
        borrowed |= {
            src for src in _declared_path_sources(root)
            if src != root and root in src.parents
        }

    return [
        Candidate(root=r, name=_project_name_of(r), rel=_relative_label(r, base))
        for r in roots if r not in borrowed
    ]


def _relative_label(root: Path, base: Path) -> str:
    """How a candidate's location is written for the reviewer — relative to what
    they typed, so it reads as the answer to the path they gave."""
    if root == base:
        return "."
    try:
        return str(root.relative_to(base))
    except ValueError:  # pragma: no cover - roots always sit under base
        return str(root)


def resolve_root(path: str | Path) -> Path:
    """Which graph ``path`` means (SR-0045).

    Pointing straight at a graph settles it, so a chosen candidate reopens
    without being asked again and a project holding a nested graph is not turned
    into a question by it. Otherwise the search runs beneath the path, and only
    an empty result falls back to the upward walk that lets the tool run from
    anywhere inside a project.
    """
    start = Path(path).resolve()
    base = start if start.is_dir() else start.parent
    if (base / CONFIG_NAME).exists():
        return base

    candidates = discover_projects(base)
    if len(candidates) == 1:
        return candidates[0].root
    if len(candidates) > 1:
        raise AmbiguousProjectError(base, candidates)

    root = _find_root(base)
    if root is None:
        raise RatifierError(
            f"no throughline.toml at, beneath or above {start} — "
            "not inside a throughline project")
    return root


def open_session(path: str | Path) -> Session:
    """Open the throughline project ``path`` names, composing its sources when it
    declares any. Raises :class:`AmbiguousProjectError` when the path encloses
    more than one graph and the choice is the reviewer's to make."""
    return open_root(resolve_root(path))


def open_root(root: Path) -> Session:
    """Open the graph rooted at ``root``, which is already decided."""
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
    """The ratification worklist: by default every local item that is neither settled
    nor dead, ranked most-actionable first. Settled means signed off *and* still
    covering its own content — an item whose wording has changed since it was accepted
    stays in the backlog, because clearing that is a job only its ratifier can do
    (SR-0030). ``show_all`` widens the view to
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
        stale = is_ratified and not is_dead and _signature_stale(session, item)
        # The default queue is the actionable backlog: hide the settled outcomes
        # (signed off, and the signature still covers the content) and the dead.
        # show_all keeps everything for review.
        if not show_all and (is_dead or (is_ratified and not stale)):
            continue

        rows.append(
            _evaluate(session, item, is_ratified, is_dead, stale, depths.get(item.uid)))

    _sort_rows(rows, sort)
    return rows


def _is_ratified(session: Session, item: Item) -> bool:
    """Whether ``item`` counts as signed off *now*. True if it currently holds the
    ratified status, or carries the ratification stamp — the latter catching an item
    that was ratified and has since advanced to ``implemented``/``verified``, so it is
    not wrongly re-offered for a ratification its status can no longer accept.

    A past stamp settles the item only while its status still stands on it (SR-0024).
    Once the item is suspect that sign-off no longer holds — something it rested on
    was withdrawn — so it is awaiting a human again and belongs back in the worklist,
    not filtered out of it by the very stamp the cascade called into question."""
    if session.suspect_status is not None and item.status == session.suspect_status:
        return False
    # Where ratification does not advance the item (throughline SR-0172), the status
    # carries no claim about sign-off — the ratified role is typically bound to an
    # ordinary workflow state there, and reading it as a signature would mark every
    # item passing through that state as signed by nobody. The stamp is the only
    # witness, which is exactly what that setting makes it.
    if not getattr(session.schema, "ratify_moves_status", True):
        return bool(item.attrs.get(RATIFIED_BY_ATTR))
    return (
        item.status == session.ratified_status
        or bool(item.attrs.get(RATIFIED_BY_ATTR))
    )


def _signature_stale(session: Session, item: Item) -> bool:
    """Whether the ratification recorded on ``item`` still covers what it signed —
    the drift throughline's ``check`` reports as ``ratified-stale`` (tl:SR-0148).

    The fingerprint is asked of throughline rather than computed here, for the reason
    ratification itself is (SR-0022): a second answer to what counts as a content
    change would drift from the validator's, and the cockpit would then disagree with
    ``check`` about which items still need a human — the exact failure this closes.
    A record written before the stamp existed carries none and cannot be judged, so
    it is not stale; that silence is throughline's own and is kept here."""
    stamp = item.attrs.get(RATIFIED_FINGERPRINT_ATTR)
    if not stamp:
        return False
    return fingerprint(item, session.schema) != stamp


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
    queue, so ratifying a row makes the number move even when it then leaves view.

    An item whose content has moved since it was accepted is counted as outstanding,
    not as ratified (SR-0030). Its signature no longer covers it, so counting it would
    report full marks over work the validator is calling an error — and a reviewer
    reading full marks stops looking."""
    schema = session.schema
    dead = schema.dead_statuses()
    ratified = gradable = 0
    for item in session.project.items():
        if item.status in dead:
            continue
        gradable += 1
        if _is_ratified(session, item) and not _signature_stale(session, item):
            ratified += 1
    return ratified, gradable


def _evaluate(
    session: Session, item: Item, is_ratified: bool, is_dead: bool, stale: bool,
    depth: int | None
) -> QueueItem:
    schema = session.schema
    union_item = session.union.get(item.uid) or item
    grounded = schema.is_root(union_item) or reaches_root(session.index, schema, item.uid)
    ambiguous = bool(item.attrs.get("ambiguous"))
    # Whether a sign-off can be taken from where the item already stands. Where
    # ratification advances the item, that is a transition question. Where the
    # project has declared it does not (throughline SR-0172), no transition is
    # involved — every status can take one directly, and the round trip below is
    # never offered, because walking a route there would fabricate exactly the
    # history that setting exists to avoid. Deciding it any other way would also
    # re-take, here, the judgement SR-0022 leaves to throughline.
    directly = (
        schema.allows_transition(item.status, session.ratified_status)
        if getattr(schema, "ratify_moves_status", True)
        else True
    )
    # Signed off, and the signature still covers the content. Only that settles an
    # item; a stale one is offered again, which throughline's own ratify permits
    # precisely because the content moved (SR-0030).
    settled = is_ratified and not stale
    # A dead item is never actionable, whatever stamp it may still carry.
    ratifiable_now = (
        directly and grounded and not ambiguous and not settled and not is_dead
    )

    if is_dead:
        # Invalidated/tombstoned — surfaced only under show_all, for the record. This
        # takes precedence over any lingering ratified stamp: it is now dead.
        concern = _dead_concern(schema, item.status)
    elif stale:
        # Signed off, then rewritten. Its own concern, ranked above the states that
        # must be fixed before anything can be signed off and never folded into
        # "ratified" — that is the claim the drift contradicts.
        concern = "stale"
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

    # Two states need a sign-off the item's current status cannot take directly: one
    # that advanced past ratified without ever being signed off, and one that was
    # signed off, has since been rewritten, and has also moved on. Both are carried
    # by the same round trip through ratified, offered only where this project's own
    # transitions permit one — what differs is what the reviewer is told they are
    # doing (SR-0019 records a sign-off that never happened; SR-0030 replaces one
    # that did).
    reratify_path = (
        _reratify_route(session, item)
        if not ratifiable_now and concern in ("blocked", "stale")
        else None
    )

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
        stale=stale,
        ratified_by=str(item.attrs.get(RATIFIED_BY_ATTR) or ""),
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
    """For a grounded, unambiguous item whose current status can no longer move
    straight to ratified, the full status itinerary that revisits ratified and returns
    to where it is now, computed purely from the project's ``[transitions]``. ``None``
    when the config offers no such round-trip, in which case no re-ratify affordance
    is shown.

    Two different situations need this same round trip — an item that advanced past
    ratified without ever being signed off (SR-0019), and one that was signed off and
    whose wording has since moved out from under the signature (SR-0030). The route
    is the same either way because it is a fact about the project's transitions, not
    about why the sign-off is owed; which of the two it is belongs to the wording the
    reviewer is shown, not here.

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

def default_ratifier(path: str | Path | None = None) -> str:
    """The ratifier to offer when none was named — throughline's answer, not ours
    (SR-0027).

    This function used to read the operating-system account name. throughline did
    the same until it stopped, and now offers the identity the repository already
    signs its commits with (throughline SR-0156); the moment it moved, the same
    person on the same machine was offered one name at the command line and another
    here. Nothing about who is offered is decided in this module any more — not the
    source of the identity, not the fallback where none is configured — so the two
    cannot part again. It is only ever an offer: the reviewer sees it in the
    confirmation for every sign-off, and an explicit ``--by`` overrides it outright."""
    return throughline_default_ratifier(path)


def normalise_identifier(raw: str | None) -> str | None:
    """Settle the optional stable identifier for the ratifying human (SR-0028).

    Whether ``github:octocat`` is well formed is throughline's judgement, not
    ours — this asks it and translates its refusal into this tool's error type so
    the caller can report it in the usual way. Nothing is invented, derived or
    defaulted: an absent identifier stays absent, because a guessed identity is
    worse than none at all. Called before the full-screen view opens so a refusal
    reaches the terminal rather than a curses window."""
    try:
        return throughline_normalise_identifier(raw)
    except IdentityError as exc:
        raise RatifierError(str(exc)) from exc


def ratify_item(session: Session, uid: str, by: str, by_id: str | None = None) -> None:
    """Take human accountability for ``uid``, grounding over the composed union.

    The sign-off itself is throughline's own :func:`throughline.grounding.ratify`
    (SR-0022) — we hand it the union's grounding index so a chain that reaches a
    root only through a source counts, and it writes the whole accountability
    record onto the consumer's own item. Nothing about who may be ratified, or
    what gets stamped, is decided here; a refusal it raises is surfaced as it
    stands. Only the consumer's register is written; a composed source stays
    read-only.

    ``by_id`` is the optional scheme-qualified identifier for that human (SR-0028).
    It is carried, never invented — absent stays absent — and whether a supplied
    one is well formed is throughline's judgement, surfaced as it stands."""
    if session.project.get(uid) is None:
        raise RatifierError(f"{uid} does not exist")
    try:
        item = core_ratify(session.project, uid, by, by_id=by_id, index=session.index)
    except (GroundingError, IdentityError) as exc:
        raise RatifierError(str(exc)) from exc
    write_item(item, session.project.register_of(uid))


def reratify_item(session: Session, uid: str, by: str,
                  by_id: str | None = None) -> list[str]:
    """Take a sign-off an item's own status cannot reach directly, then restore that
    status — for a grounded, unambiguous item that has moved past ratified. It covers
    both reasons a sign-off can be owed there: one never taken because the item
    overshot ratification (SR-0019), and one taken but since outgrown by the wording
    beneath it (SR-0030). The mechanics are identical; only what the caller tells the
    reviewer differs, and telling them a signature was missing when it was merely
    superseded would misdescribe the very record this tool exists to protect.

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
        core_ratify(session.project, uid, by, by_id=by_id, index=session.index)
        for to in route[pivot + 1:]:
            set_status(schema, item, to)
    except (GroundingError, IdentityError) as exc:
        # A refusal part-way along must not leave the in-memory item stranded at an
        # intermediate status the ratifier never chose. Nothing was written, so
        # restoring where it started makes the failure a true no-op.
        item.status = was
        raise RatifierError(str(exc)) from exc
    write_item(item, session.project.register_of(uid))
    return route


def preview_reject(session: Session, uid: str) -> list[str]:
    """The items that rejecting ``uid`` would actually make suspect, worked out
    without changing anything (SR-0025).

    A confirmation must state the consequence the cockpit has established, not the
    one an action of this kind can have in general, so the blast radius has to be
    known *before* the question is asked rather than read off the return value
    afterwards. Every fact used here is asked of throughline — the impact set from
    its index, the suspect status and the dead set from the project's own
    ``[status.roles]``, the legality of the move from its ``[transitions]`` — so the
    prediction is made the same way the cascade is, and the assistant carries no
    account of its own (SR-0026).

    The traversal is narrowed by the project's own ``withdrawing_link_types`` — the
    same set throughline's :func:`invalidate` walks — because suspicion follows the
    links that carry justification, not every link that happens to point at the
    item. The wider, unfiltered reachable set is a different question, and answering
    it here would over-state the consequence the reviewer is being asked to accept."""
    project = session.project
    if project.get(uid) is None:
        raise RatifierError(f"{uid} does not exist")
    suspect = session.suspect_status
    if suspect is None:
        return []
    schema = session.schema
    dead = schema.dead_statuses()
    return [
        aid
        for aid in sorted(Index.build(project).impact(
            uid, schema.withdrawing_link_types()))
        if (dep := project.get(aid)) is not None
        and dep.status not in dead
        and schema.allows_transition(dep.status, suspect)
    ]


class Rejection(list):
    """What a rejection did: the UIDs it made suspect, and the ones it could not.

    It *is* the list of newly-suspect UIDs, so a caller that reads the return as that
    list is unaffected (SR-0025). ``refused`` carries the dependents whose configured
    lifecycle declared no route to the suspect status, each with the move that was
    refused, so a reviewer can be told about footing that was withdrawn without
    anything being flagged (SR-0037)."""

    def __init__(self, marked: list[str], refused: list[Refusal]):
        super().__init__(marked)
        self.refused = refused


def reject_item(session: Session, uid: str, reason: str = "") -> Rejection:
    """Reject (invalidate) ``uid`` and cascade suspicion to its dependents, then
    persist every touched local item.

    Returns the UIDs that were *actually* made suspect — throughline reports them
    itself (tl:SR-0173), separately from the impact set, which is everything reachable
    and includes dependents left untouched because they were already dead or could not
    legally become suspect. What is reported afterwards, and what the session summary
    records, is then a fact about what happened rather than a claim about what might
    have (SR-0025). The refusals ride along on the result rather than being dropped,
    because a dependent left unflagged is the drift the cockpit exists to show
    (SR-0037)."""
    project = session.project
    if project.get(uid) is None:
        raise RatifierError(f"{uid} does not exist")
    try:
        outcome = invalidate(project, uid, reason)
    except GroundingError as exc:
        raise RatifierError(str(exc)) from exc

    write_item(project.get(uid), project.register_of(uid))
    for aid in outcome.marked:
        write_item(project.get(aid), project.register_of(aid))
    return Rejection(outcome.marked, outcome.refused)


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
