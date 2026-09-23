# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""The engine behind throughline-ratify.

This module owns everything that touches a throughline graph; the TUI
(:mod:`throughline_ratify.tui`) is a pure view over the values it
produces. It is deliberately compose-aware: when the project declares
``[[sources]]`` it grounds each item over the *composed union* — exactly as
``tl ratify`` does — so an item whose grounding chain reaches a root only
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
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

try:  # pragma: no cover - 3.11+ has it in the stdlib; the floor is 3.11
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

# Every name this module leans on is one throughline publishes (SR-0057): its
# `__all__`, listed in its document 10. Nothing is imported from a path inside the
# package and nothing that begins with an underscore, so a rename inside the Tool
# is the Tool's business and not a release here (UR-0016). What the cockpit asks
# of the Tool — who signs (SR-0027), what a signature records (SR-0022), what has
# moved since it (SR-0030), what awaits one and why (SR-0058), and the composed
# union it judges over (SR-0060) — is answered by these names and decided nowhere
# else.
from throughline import (
    CONCERNS,
    fingerprint,
    CONFIG_NAME,
    ComposeError,
    GroundingError,
    IdentityError,
    Index,
    Item,
    Project,
    ProjectError,
    RatificationChange,
    Refusal,
    SchemaError,
    SourceError,
    WorklistEntry,
    build_union,
    change_since_ratification,
    depths_from_roots,
    entry_for,
    invalidate,
    is_namespace_qualified,
    load_project,
    parse_sources,
    reaches_root,
    resolve_sources,
    set_status,
    write_item,
)
from throughline import default_ratifier as throughline_default_ratifier
from throughline import normalise_identifier as throughline_normalise_identifier
from throughline import ratification_progress as throughline_ratification_progress
from throughline import ratify as core_ratify


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


# The concerns a row can be in are throughline's vocabulary (SR-0058); what this
# cockpit decides is only how each is drawn. A concern the Tool adds is caught at
# import rather than drawn as a blank.
CONCERN_ICONS: dict[str, str] = {
    "proposed": "\u25cf",
    "ready": "\u25c9",
    "stale": "\u21ba",
    "blocked": "\u25cb",
    "ungrounded": "\u26a0",
    "ambiguous": "\u2691",
    "ratified": "\u2713",
    "rejected": "\u2717",
    "deleted": "\u2620",
}
assert set(CONCERN_ICONS) >= set(CONCERNS), sorted(set(CONCERNS) - set(CONCERN_ICONS))

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
    # Why the item cannot be signed as the graph stands, in the words throughline's
    # own ratify would use to refuse it (SR-0058); None when it can.
    obstacle: str | None = None

    @property
    def icon(self) -> str:
        return CONCERN_ICONS.get(self.concern, "\u25cb")


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
    # Resolved differences, keyed by (uid, stamp). Keyed on the stamp and not the
    # uid alone so that re-signing an item — which writes a new stamp — misses the
    # entry left by its old one instead of showing a difference against content
    # that has just been accepted.
    _changes: dict[tuple[str, str], RatificationChange] = field(default_factory=dict)

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

    Discovery fills the first three fields, which name the graph and locate it.
    The rest are filled by :func:`describe_candidates` from the graph's own
    registers, so a row can say how far it has been signed off (SR-0050).
    Nothing here resolves a candidate's declared sources: SR-0048 keeps that for
    the one graph the reviewer picks.
    """

    root: Path
    name: str
    rel: str    # display path, relative to the path searched
    ratified: int | None = None   # signed off, of the gradable local items
    gradable: int | None = None   # local items that can be signed off
    modified: float = 0.0         # newest mtime among its own item files
    error: str | None = None      # why it could not be read, if it could not

    @property
    def described(self) -> bool:
        return self.gradable is not None or self.error is not None

    @property
    def outstanding(self) -> int:
        """Items still awaiting a signature. A graph that could not be read sorts
        as though nothing were outstanding rather than as though everything were,
        so a broken graph does not crowd out the work (SR-0051)."""
        if self.gradable is None or self.ratified is None:
            return 0
        return self.gradable - self.ratified


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


# The orders the selection screen offers, in the order the sort key cycles them.
# Fixed in code rather than configurable, for the reason _MAX_SEARCH_DEPTH is
# (SR-0026): a project able to name its own would decide which of a reviewer's
# graphs they saw first, and the assistant would then hold an account of the
# project that tl does not share.
PICKER_SORTS = ("path", "outstanding", "recent")


def _latest_change(project: Project) -> float:
    """The newest modification time among the graph's own item files.

    Read from the filesystem rather than from version control: asking git would
    start a process per candidate, and SR-0039 keeps this module free of those.
    A file that cannot be stat'd simply has no timestamp to offer, and is passed
    over: recency is a convenience, and one dangling symlink must not cost a graph
    the timestamps of every other file in the same register.
    """
    newest = 0.0
    for register in project.registers.values():
        for item_file in register.path.glob("*.yml"):
            try:
                newest = max(newest, item_file.stat().st_mtime)
            except OSError:
                continue
    return newest


def describe_candidates(
    candidates: list[Candidate],
    on_progress: Callable[[int, int, Candidate], None] | None = None,
) -> list[Candidate]:
    """Read each candidate's own registers so its row can say how far it has been
    signed off (SR-0050).

    Each graph is read on its own and a failure is kept on its own row (SR-0051):
    this screen exists because the reviewer does not yet know which graph they
    want, so one unreadable project must not withhold the rest. ``on_progress`` is
    called before each candidate is read with ``(index, total, candidate)``, which
    is how the caller shows the work happening without this module knowing what a
    terminal is (SR-0039).

    The figure is the one :func:`ratification_progress` computes for the cockpit's
    own header, from the same items, so the screen and the cockpit cannot give two
    accounts of one number. Sources are never resolved here — SR-0048 keeps that
    for the graph the reviewer picks.
    """
    described: list[Candidate] = []
    total = len(candidates)
    for i, candidate in enumerate(candidates):
        if on_progress is not None:
            on_progress(i, total, candidate)
        try:
            session = _open(candidate.root, compose=False)
        except RatifierError as exc:
            # The row already names the path, so the root _open prefixes for the
            # benefit of a caller that has nothing else to locate the graph by is
            # only noise here.
            reason = _first_line(str(exc)).removeprefix(f"{candidate.root}: ")
            described.append(replace(candidate, error=reason))
            continue
        ratified, gradable = ratification_progress(session)
        described.append(replace(
            candidate, ratified=ratified, gradable=gradable,
            modified=_latest_change(session.project)))
    return described


def _first_line(message: str) -> str:
    """The opening line of a failure, for a row that has one line to say it in."""
    return message.strip().splitlines()[0] if message.strip() else "could not be read"


def sort_candidates(candidates: list[Candidate], sort: str) -> list[Candidate]:
    """``candidates`` in the order ``sort`` names (SR-0052), leaving the argument
    alone. Every order falls back to the path, so the list is fully determined and
    does not shuffle between two graphs that tie."""
    by_path = sorted(candidates, key=lambda c: c.rel)
    if sort == "outstanding":
        return sorted(by_path, key=lambda c: -c.outstanding)
    if sort == "recent":
        return sorted(by_path, key=lambda c: -c.modified)
    return by_path


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
    return _open(root, compose=True)


def _open(root: Path, compose: bool) -> Session:
    """Load ``root``, composing its declared sources only when ``compose``.

    An uncomposed session is the graph's own account of itself: its ``union`` is
    the consumer, so anything grounding-related read from it would be wrong for a
    project that declares sources. It exists for :func:`describe_candidates`,
    which asks only what needs no union, and it never leaves this module.
    """
    try:
        consumer = load_project(root)
    except ProjectError as exc:
        raise RatifierError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — see below
        # A project directory is arbitrary user data, so a malformed item file
        # surfaces as the YAML parser's own error rather than as a ProjectError.
        # Either way the reviewer needs the reason and not a traceback printed
        # over a terminal curses has just restored (SR-0016, SR-0051).
        raise RatifierError(f"{root}: {exc}") from exc

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

    union, sources = _compose_if_declared(consumer, root) if compose else (consumer, [])
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
    no ``[[sources]]`` the consumer is its own union (pure ``tl`` behaviour).

    Resolution is throughline's own, through the name it publishes (SR-0057): the
    same closure the Tool's own composed commands build — transitive sources, one
    fetch per edition, a namespace bound to two editions refused — so the union the
    cockpit judges over is the union `tl check` judges over. The private seam
    SR-0054 once read, and its fallback to a single-hop resolver, are gone with it.
    """
    try:
        declared = parse_sources(consumer)
    except SourceError as exc:
        raise RatifierError(str(exc)) from exc
    if not declared:
        return consumer, []
    try:
        res = resolve_sources(declared, root)
        union = build_union(consumer, res.projects(), res.labels)
    except (SourceError, ComposeError) as exc:
        raise RatifierError(f"could not compose sources: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - a resolver's failure, reported cleanly
        raise RatifierError(f"could not compose sources: {exc}") from exc
    infos = [SourceInfo(ns, res.locations.get(ns, "")) for ns in sorted(res.resolved)]
    return union.project, infos


def build_queue(
    session: Session, *, show_all: bool = False, sort: str = "concern"
) -> list[QueueItem]:
    """The ratification worklist, as throughline computes it (SR-0058).

    Which items are outstanding, the concern each is in, whether it can be signed
    now and the Tool's own reason when it cannot, the depth from a root and the
    order they are offered in all come from throughline; this function only draws
    them. By default the settled outcomes (signed off, and the signature still
    covering the content) and the dead are left out, as the Tool leaves them out;
    ``show_all`` asks for them. ``sort`` is a view choice: ``"concern"`` keeps the
    Tool's order, ``"roots"`` and ``"leaves"`` reorder by depth (see :data:`SORTS`).
    """
    if sort not in SORTS:
        raise RatifierError(f"unknown sort {sort!r}; choose one of {', '.join(SORTS)}")
    # Depth is measured over the composed union, so an item grounded only through
    # a borrowed root is as close to it as one grounded through a local one.
    depths = depths_from_roots(session.union, session.index)
    entries = [entry_for(session.project, item, index=session.index, depths=depths)
               for item in session.project.items()]
    if not show_all:
        entries = [e for e in entries if e.concern not in ("ratified", "rejected", "deleted")]
    order = {name: n for n, name in enumerate(CONCERNS)}
    entries.sort(key=lambda e: (order.get(e.concern, len(CONCERNS)),
                                e.depth if e.depth is not None else 1 << 30, e.uid))
    rows = [_row(session, e) for e in entries]
    if sort == "roots":
        rows.sort(key=lambda r: (r.depth is None, r.depth or 0, r.uid))
    elif sort == "leaves":
        rows.sort(key=lambda r: (r.depth is None, -(r.depth or 0), r.uid))
    return rows


def _row(session: Session, entry: WorklistEntry) -> QueueItem:
    """One worklist entry as the TUI draws it: the Tool's judgement, plus the body,
    the resolved links and the re-ratify itinerary this cockpit adds."""
    item = session.project.get(entry.uid)
    # The walk is for an item that overshot ratification without ever being signed
    # (SR-0019). A signed item whose wording has since moved is not one: the Tool
    # records the new signature where it stands (throughline SR-0237, from 3.11.3),
    # so the worklist already calls it ratifiable and no route is offered.
    reratify_path = (
        _reratify_route(session, item)
        if not entry.ratifiable and entry.concern == "blocked"
        else None
    )
    return QueueItem(
        uid=entry.uid,
        title=entry.title,
        type=entry.type,
        status=entry.status,
        concern=entry.concern,
        grounded=entry.grounded,
        ambiguous=entry.ambiguous,
        ratifiable_now=entry.ratifiable,
        text=item.text,
        rationale=item.rationale,
        links=_resolve_links(session, item),
        depth=entry.depth,
        reratify_path=reratify_path,
        reason=str(item.attrs.get("invalidated_reason") or ""),
        # A dead row is drawn as dead; the staleness of the record it still carries
        # is a fact the Tool reports, not an action this view offers (SR-0030).
        stale=entry.stale and not entry.dead,
        ratified_by=str(item.attrs.get(RATIFIED_BY_ATTR) or ""),
        obstacle=entry.obstacle,
    )


def fingerprint_of(session: Session, item: Item) -> str:
    """The fingerprint the Tool would stamp on ``item`` now, under this project's
    schema — asked of the Tool, never computed here (SR-0022)."""
    return fingerprint(item, session.schema)


def change_since_signature(session: Session, uid: str) -> RatificationChange | None:
    """What moved since ``uid``'s signature, or None when the item is not local.

    Resolved on demand for the one item the reviewer is looking at, never for every
    row: resolution walks back through an item's history, and a reviewer moving down
    a worklist would pay that walk on each row they land on. throughline caches the
    revision it resolves and re-verifies it against the stamp (tl:SR-0166), so the
    second look at an item costs a read rather than a walk, and the memo here keeps
    a redraw from asking twice.

    The consumer project is what is asked, so the schema deciding which attributes
    are normative is the one :func:`_signature_stale` judged staleness with. Handing
    over the union instead would let the cockpit call an item stale and then report
    nothing changed, which is the disagreement SR-0030 exists to prevent.
    """
    item = session.project.get(uid)
    if item is None:
        return None
    key = (uid, str(item.attrs.get(RATIFIED_FINGERPRINT_ATTR) or ""))
    if key not in session._changes:
        session._changes[key] = change_since_ratification(session.project, item)
    return session._changes[key]



def ratification_progress(session: Session) -> tuple[int, int]:
    """``(ratified, gradable)`` over the local, non-dead items — the figure a human
    watches climb — as throughline counts it (SR-0058). Counts the whole project,
    not just the filtered queue, so ratifying a row makes the number move even
    when it then leaves view."""
    return throughline_ratification_progress(session.project, index=session.index)


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
        external = is_namespace_qualified(ref)
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

    One situation needs this round trip: an item that advanced past ratified without
    ever being signed off (SR-0019). An item that was signed off and whose wording has
    since moved is re-signed where it stands by the Tool itself (throughline SR-0237)
    and never arrives here.

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
    status — for a grounded, unambiguous item that overshot ratification without
    ever being signed off (SR-0019). A signature that was taken and since outgrown by
    the wording beneath it is not this case: the Tool records the replacement where
    the item stands (throughline SR-0237), through :func:`ratify_item`.

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
