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
moves are legal. Each move is also judged against where the item stood at the last
commit, as ``tl check`` judges it, so moves that are each permitted never add up to
one the project forbids (SR-0097).

Ratification itself is throughline's :func:`throughline.grounding.ratify`, called
rather than copied (SR-0022). We hand it our union index and it writes the whole
accountability record — who accepted the item *and* a fingerprint of what they
accepted. A copy of that operation lived here once, and when throughline began
binding signatures to content the copy silently fell behind, leaving every item
ratified through this cockpit signed but unbound. One implementation, not two.
"""
from __future__ import annotations

import copy
import json
import os
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
    Cascade,
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
    attribute_owner,
    build_union,
    change_since_ratification,
    delete_item,
    depths_from_roots,
    entry_for,
    invalidate,
    is_namespace_qualified,
    load_project,
    load_project_at_ref,
    parse_sources,
    read_project,
    reaches_root,
    render_for_ratification,
    resolve_sources,
    retired,
    set_status,
    transition_refusal,
    write_item,
)
from throughline import distribution_version
from throughline import default_identifier as throughline_default_identifier
from throughline import default_ratifier as throughline_default_ratifier
from throughline import normalise_identifier as throughline_normalise_identifier
from throughline import ratification_progress as throughline_ratification_progress
from throughline import ratify as core_ratify
from throughline import signatures as throughline_signatures


class RatifierError(RuntimeError):
    """A user-facing failure the TUI should surface without a traceback."""


class GraphLostError(RatifierError):
    """The graph an open cockpit holds is gone: its configuration file no longer
    exists (SR-0067). The message is the one line the reviewer is shown, naming
    the graph's path. ``undone`` is what the reviewer had asked for when the
    loss was found (``"signed"``, ``"rejected"``), or ``None`` when they had
    asked for nothing; ``said`` is the message without the path, for a screen
    that names the graph in its own way."""

    def __init__(self, root: Path, undone: str | None = None) -> None:
        self.root, self.undone = root, undone
        self.said = "the graph no longer exists" + (
            f"; nothing was {undone}" if undone else "")
        super().__init__(f"{root}: {self.said}")


class GraphUnreadableError(RatifierError):
    """The graph an open cockpit holds is still there and cannot be read
    (SR-0071). The message is the reason, without the graph's path: the cockpit
    showing it already names the graph."""


class ReadOnlySessionError(RatifierError):
    """A write asked of a session opened read-only (SR-0081). Nothing was written.
    Where the graph is at an older on-disk format than the Tool's, the message
    names ``tl migrate``, the one way such a graph becomes writable."""


# The ratification record is the Tool's `ratifications` list on the item, one
# signature per person (throughline SR-0254, from 4.0.0). Who signed, whether a
# signature still covers the wording, and whether the signatures meet what the
# item's kind requires are all read through the Tool's own `signatures` module,
# never from an attribute this cockpit names itself (SR-0057).


# --------------------------------------------------------------------------- #
# Semantic concerns — what colour/icon a row earns, and how it sorts.
# --------------------------------------------------------------------------- #


# The concerns a row can be in are throughline's vocabulary (SR-0058); what this
# cockpit decides is only how each is drawn. A concern the Tool adds is caught at
# import rather than drawn as a blank.
CONCERN_ICONS: dict[str, str] = {
    "proposed": "\u25cf",
    "ready": "\u25c9",
    # Signed by some of the people the item's kind requires, not yet by all
    # (throughline SR-0260): half a disc, for a signature half gathered.
    "awaiting": "\u25d0",
    "stale": "\u21ba",
    "ungrounded": "\u26a0",
    "ambiguous": "\u2691",
    # A draft is agreed or deleted, never signed (throughline SR-0307): a dotted
    # circle, a proposal not yet drawn in.
    "draft": "\u25cc",
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
    # The attributes the item carries, in the order its file holds them, bar the
    # ratification record (SR-0076). That record is the Tool's own bookkeeping
    # of a signature, and the pane already says whether there is one and whose;
    # everything else is the author's and is shown as written.
    attrs: dict = field(default_factory=dict)
    # The attribute names the signature covers — those the project's schema marks
    # normative for the item's type, which is what the fingerprint reads (SR-0076).
    # A change to one of these breaks the signature; the pane marks them so the
    # signer knows which of the values they are reading they are also signing.
    signed_attrs: tuple[str, ...] = ()
    # The item's own normative and derived flags, both read by the fingerprint, so
    # both shown to the signer (SR-0076). The defaults are the common case and are
    # not drawn; only a departure from them is.
    normative: bool = True
    derived: bool = False
    # For a draft: the status p agrees it to, as throughline names it (throughline
    # SR-0307; SR-0085). None for any other item, and for a draft its transitions
    # offer nowhere to agree to, which can only be deleted.
    agree_to: str | None = None
    # Why a dead (rejected) item was invalidated, if it recorded a reason. Empty
    # for live items and for tombstones with no reason.
    reason: str = ""
    # A sign-off that still stands but no longer covers the item's content — the
    # state throughline's check reports as ``ratified-stale`` (SR-0030). Ratifying
    # again is what clears it, so such an item is actionable, not settled.
    stale: bool = False
    # Who took accountability, when the item carries a sign-off: every signer,
    # as prose. Named on a stale row so the reviewer can see whose signature
    # they are about to replace.
    ratified_by: str = ""
    # Each signature the item carries, in words (name, identifier, role), oldest
    # first, and where the item stands against what its kind requires
    # (throughline SR-0260, SR-0261): shown so a second signer sees who went
    # before them and what is still asked for.
    signatures: tuple[str, ...] = ()
    standing: str = ""
    # Why the item cannot be signed as the graph stands, in the words throughline's
    # own ratify would use to refuse it (SR-0058); None when it can.
    obstacle: str | None = None
    # A proposed deletion (throughline SR-0267): the item is a tombstone whose
    # deletion no human has yet ratified, so it is still live scope and what a
    # signature on it accepts is the deletion record, not the wording (SR-0084).
    # False for a tombstone that stands, which is dead and drawn as such.
    deletion: bool = False
    # For a proposed deletion: the live items grounded on it along the withdrawing
    # link types — the ones ratifying it marks suspect (throughline SR-0270). The
    # confirmation names them, so the consequence is read before it is accepted.
    dependents: tuple[str, ...] = ()
    # For a proposed deletion: the record the signature is taken over, in the
    # lines throughline puts in front of a signer at `tl ratify` (SR-0083) — the
    # reason, the day, the status the item held, the content retired, whose
    # acceptance the deletion undoes and what it marks suspect.
    record: tuple[str, ...] = ()

    @property
    def icon(self) -> str:
        return CONCERN_ICONS.get(self.concern, "\u25cb")

    @property
    def draft(self) -> bool:
        """A draft: agreed with p or deleted with D, never signed (SR-0086)."""
        return self.concern == "draft"


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
    # What the graph's files looked like when this session last read or wrote them
    # (SR-0061). Compared with the disk before anything is written, so a screen left
    # open across somebody else's edit cannot sign wording it never showed.
    seen: tuple = ()
    # The format the graph's configuration declares when it is older than the
    # Tool's: such a graph was read by the Tool's tolerant reader and is never
    # written through (SR-0081). None for a graph at the Tool's own format.
    older_format: int | None = None

    @property
    def schema(self):
        return self.project.schema

    @property
    def read_only(self) -> bool:
        return self.older_format is not None

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
    watched: tuple[Path, ...] | None = None  # its register folders, once read
    seen: tuple = ()              # its files as they stood when it was read (SR-0069)

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

    def __init__(self, base: Path, candidates: list[Candidate],
                 several: bool = False) -> None:
        where = "the paths given" if several else str(base)
        super().__init__(
            f"{len(candidates)} throughline projects found beneath {where} — "
            "which one to ratify against is yours to choose")
        # Where several paths were given, base is the directory they share and
        # each candidate's label is relative to it (SR-0088).
        self.base = base
        self.candidates = candidates
        self.several = several


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
        # NUL-separated both ways (-z). A newline-separated list is rewritten
        # to CRLF by text mode on Windows, so every path reached git with a
        # trailing carriage return and nothing was ever ignored; NUL survives
        # the translation, and -z also frees the answer from git's quoting of
        # unusual characters.
        proc = subprocess.run(
            ["git", "-C", str(base), "check-ignore", "--stdin", "-z"],
            input="".join(f"{d}\0" for d in dirs),
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    return {Path(entry).resolve() for entry in proc.stdout.split("\0") if entry.strip()}


def _is_excluded(d: Path) -> bool:
    """A directory the search never enters — one that cannot hold a graph the
    reviewer owns (SR-0046). Dot-directories cover ``.git`` and ``.venv``;
    ``pyvenv.cfg`` catches a virtualenv that is not named like one."""
    return (
        d.name.startswith(".")
        or d.is_symlink()
        or (d / "pyvenv.cfg").exists()
    )


# Called as the search goes, with the directory being searched beneath, how many
# directories have been looked in and how many graphs found so far (SR-0094).
SearchProgress = Callable[[Path, int, int], None]


def discover_projects(path: str | Path, *more: str | Path,
                      on_search: SearchProgress | None = None) -> list[Candidate]:
    """Every graph at or beneath ``path`` — and beneath each of ``more``, where
    several paths were given (SR-0088) — in the order they should be offered.

    Breadth-first to ``_MAX_SEARCH_DEPTH``, pruning what SR-0046 excludes as the
    walk descends rather than filtering at the end, so an ignored directory costs
    nothing to skip. A graph an enclosing candidate declares as a source is
    dropped: composition gives a wider view, never a wider authority, so offering
    one as a peer would present a graph on which every decision is then refused.
    Over several paths that holds across the whole list, and a graph two of them
    reach is offered once.
    """
    bases = [base_of(p) for p in (path, *more)]
    roots: list[Path] = []
    search = _Search(on_search)
    for base in bases:
        roots.extend(r for r in _graphs_beneath(base, search.path(roots))
                     if r not in roots)
    return _candidates(_drop_borrowed(roots), shared_directory(bases))


def base_of(path: str | Path) -> Path:
    """The directory a given path stands for: itself, or the one holding it.
    Taken once, when the path is given: a directory that has since gone stands
    for nothing, never for its parent (SR-0068)."""
    base = Path(path).resolve()
    return base if base.is_dir() else base.parent


class _Search:
    """One running total over every path searched (SR-0094): each path's walk
    counts from zero, and this carries the counts of the paths before it."""

    def __init__(self, on_search: SearchProgress | None) -> None:
        self.on_search = on_search
        self.before = 0     # directories looked in beneath the earlier paths
        self.last = 0       # directories looked in beneath the present one

    def path(self, found_before: list[Path]) -> SearchProgress | None:
        """The progress callback for the next path's walk."""
        self.before, self.last = self.before + self.last, 0
        if self.on_search is None:
            return None

        def _report(base: Path, directories: int, graphs: int) -> None:
            self.last = directories
            self.on_search(base, self.before + directories, len(found_before) + graphs)
        return _report


def _graphs_beneath(base: Path, on_search: SearchProgress | None = None) -> list[Path]:
    """The roots of every graph at or beneath ``base``, before SR-0046's rule on
    borrowed graphs is applied. ``on_search`` hears how far the walk has got."""
    roots: list[Path] = []
    if (base / CONFIG_NAME).exists():
        roots.append(base)

    looked = 0
    level = [base]
    for _ in range(_MAX_SEARCH_DEPTH):
        children: list[Path] = []
        for parent in level:
            looked += 1
            if on_search is not None:
                on_search(base, looked, len(roots))
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
        # Both sides resolved: git echoes the path in its own spelling, and on
        # Windows that differs from the walk's (separators, drive case, short
        # names), so an unresolved child never matched and nothing was ignored.
        children = [c for c in children if c.resolve() not in ignored]
        roots.extend(c for c in children if (c / CONFIG_NAME).exists())
        level = children
    return roots


def _drop_borrowed(roots: list[Path]) -> list[Path]:
    """``roots`` less every graph another of them declares as a source and
    encloses (SR-0046)."""
    borrowed: set[Path] = set()
    for root in roots:
        borrowed |= {
            src for src in _declared_path_sources(root)
            if src != root and root in src.parents
        }
    return [r for r in roots if r not in borrowed]


def _candidates(roots: list[Path], base: Path | None) -> list[Candidate]:
    return [Candidate(root=r, name=_project_name_of(r), rel=_relative_label(r, base))
            for r in roots]


def labelled_from(candidates: list[Candidate], base: Path | None) -> list[Candidate]:
    """``candidates`` with each label written relative to ``base``."""
    return [replace(c, rel=_relative_label(c.root, base)) for c in candidates]


def shared_directory(bases: list[Path]) -> Path | None:
    """The deepest directory every one of ``bases`` lies within, which candidates
    are labelled from (SR-0088). One path is its own. Paths with nothing in
    common — two drives on Windows — have none, and are labelled in full."""
    try:
        return Path(os.path.commonpath([str(b) for b in bases]))
    except ValueError:
        return None


def _relative_label(root: Path, base: Path | None) -> str:
    """How a candidate's location is written for the reviewer — relative to what
    they typed, so it reads as the answer to the path they gave."""
    if root == base:
        return "."
    if base is None:
        return str(root)
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
    kept: "Assessments | None" = None,
    reuse: bool = True,
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

    With ``kept``, a candidate whose own files stand as they did when its figure
    was kept takes that figure without being read, and only the rest are read
    and counted by ``on_progress`` (SR-0095); every figure read is kept. Without
    ``reuse`` every candidate is read, and still kept: that is R (SR-0068).
    """
    reused = {}
    if kept is not None and reuse:
        for candidate in candidates:
            known = kept.recall(candidate)
            if known is not None:
                reused[candidate.root] = known
    to_read = [c for c in candidates if c.root not in reused]
    read = {c.root: c for c in _read_candidates(to_read, on_progress)}
    if kept is not None and read:
        kept.keep(read.values())
    return [reused.get(c.root) or read[c.root] for c in candidates]


def _read_candidates(
    candidates: list[Candidate],
    on_progress: Callable[[int, int, Candidate], None] | None,
) -> list[Candidate]:
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
            unread = replace(candidate, error=reason, watched=None)
            described.append(replace(unread, seen=_candidate_state(unread)))
            continue
        ratified, gradable = ratification_progress(session)
        read = replace(
            candidate, ratified=ratified, gradable=gradable, error=None,
            modified=_latest_change(session.project),
            watched=tuple(sorted({r.path for r in session.project.registers.values()
                                  if r.path is not None})))
        described.append(replace(read, seen=_candidate_state(read)))
    return described


def _candidate_state(candidate: Candidate) -> tuple:
    """The candidate's own files as they stand now: its configuration, and every
    item file and manifest in its register folders (SR-0069).

    A graph that could not be read has no known registers, because reading it is
    what failed, so every YAML file beneath it is watched instead. Nothing is
    parsed here: the screen asks this of every candidate at each interval, and
    loading forty graphs to learn that none has moved would be most of the cost
    of the reload it is deciding whether to do."""
    files = [candidate.root / CONFIG_NAME]
    if candidate.watched is None:
        try:
            files.extend(sorted(candidate.root.rglob("*.yml")))
        except OSError:
            pass
    else:
        for folder in candidate.watched:
            files.extend(sorted(folder.glob("*.yml")))
            files.append(folder / ".register.yml")
    return _files_state(files)


def assessments_path() -> Path:
    """Where the candidates' figures are kept (SR-0095): beside the favourites,
    in the reviewer's own state directory."""
    return favourites_path().with_name("assessments")


# Names what wrote a kept figure. A figure is throughline's to compute (SR-0050),
# so one kept by another release of either package is read again, not trusted.
def _reader() -> str:
    return f"{distribution_version('throughline-ratify')}/{distribution_version('throughline')}"


class Assessments:
    """Each candidate's figure, kept with the state of its own files it was read
    from (SR-0095). The reviewer's own and derived from the graphs, so it is no
    account of a project that tl does not share; nothing here is ever read in
    place of a graph whose files have moved.
    """

    _SHAPE = 1

    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path is not None else assessments_path()
        self._entries: dict[str, dict] | None = None

    def _load(self) -> dict[str, dict]:
        if self._entries is None:
            self._entries = {}
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if data.get("shape") == self._SHAPE and data.get("reader") == _reader():
                    self._entries = dict(data["graphs"])
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                pass   # absent, unreadable or another shape: keeps nothing
        return self._entries

    def recall(self, candidate: Candidate) -> Candidate | None:
        """``candidate`` with its kept figure, where its own files stand as they
        did when that figure was kept; ``None`` where it must be read."""
        entry = self._load().get(str(candidate.root))
        if entry is None:
            return None
        try:
            watched = None if entry["watched"] is None else \
                tuple(Path(w) for w in entry["watched"])
            known = replace(candidate, ratified=entry["ratified"],
                            gradable=entry["gradable"], modified=entry["modified"],
                            error=entry["error"], watched=watched)
            seen = tuple(tuple(f) for f in entry["seen"])
        except (KeyError, TypeError):
            return None
        state = _candidate_state(known)
        return replace(known, seen=state) if state == seen else None

    def keep(self, described) -> None:
        """Keep each of ``described``'s figures, and write the file. A file that
        cannot be written leaves the figures unkept and the screen working."""
        entries = self._load()
        for c in described:
            entries[str(c.root)] = {
                "ratified": c.ratified, "gradable": c.gradable,
                "modified": c.modified, "error": c.error,
                "watched": None if c.watched is None else [str(w) for w in c.watched],
                "seen": [list(f) for f in c.seen],
            }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            spare = self.path.with_name(self.path.name + ".new")
            spare.write_text(json.dumps({"shape": self._SHAPE, "reader": _reader(),
                                         "graphs": entries}), encoding="utf-8")
            os.replace(spare, self.path)
        except OSError:
            pass


def candidate_changed(candidate: Candidate) -> bool:
    """True when the candidate's own files differ from what its row was read from
    (SR-0069). A candidate not yet read has nothing to differ from."""
    return candidate.described and _candidate_state(candidate) != candidate.seen


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


# The views the selection screen offers, in the order the view key cycles them
# (SR-0090). Fixed in code, as the orders are (SR-0052).
PICKER_VIEWS = ("all", "favourites", "others")
VIEW_NAMES = {"all": "all", "favourites": "favourites", "others": "not yet favourites"}


def in_view(candidates: list[Candidate], view: str,
            favourites: set[Path]) -> list[Candidate]:
    """Those of ``candidates`` the view ``view`` lists, in the order given."""
    if view == "favourites":
        return [c for c in candidates if c.root in favourites]
    if view == "others":
        return [c for c in candidates if c.root not in favourites]
    return list(candidates)


def matching(candidates: list[Candidate], text: str) -> list[Candidate]:
    """Those of ``candidates`` whose name or path holds ``text``, ignoring case
    (SR-0093). No text matches every one."""
    needle = text.strip().casefold()
    if not needle:
        return list(candidates)
    return [c for c in candidates
            if needle in c.name.casefold() or needle in c.rel.casefold()]


def favourites_path() -> Path:
    """Where the reviewer's favourites are kept (SR-0089): their own state
    directory, outside every project. The XDG convention elsewhere, which also
    says to ignore a relative value; the local application data folder on
    Windows."""
    if os.name == "nt":
        home = os.environ.get("LOCALAPPDATA") or ""
        state = Path(home) if home else Path.home() / "AppData" / "Local"
    else:
        home = os.environ.get("XDG_STATE_HOME") or ""
        state = Path(home) if os.path.isabs(home) else Path.home() / ".local" / "state"
    return state / "tl-ratify" / "favourites"


class FavouritesError(RatifierError):
    """The favourites file could not be read or written (SR-0089)."""


class Favourites:
    """The graphs the reviewer has marked as favourites (SR-0089).

    The reviewer's own, not the assistant's and not any project's: SR-0026
    admits them because nothing read from here changes how a graph is read,
    shown or signed — only which graphs a view lists. One absolute graph root
    per line, so the file can be read and edited with anything.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path is not None else favourites_path()
        self.roots: set[Path] = set()

    def load(self) -> None:
        """Read the file as it now stands. An absent file is no favourites; one
        that cannot be read raises :class:`FavouritesError` and keeps what was
        held."""
        self.roots = set(map(Path, self._lines()))

    def toggle(self, root: Path) -> bool:
        """Mark ``root`` a favourite, or unmark it where it is one, returning
        whether it now is. The file is read again first and only that one line
        changes, so a sitting never undoes another's marks; it is replaced whole,
        so it is never left half-written. Raises :class:`FavouritesError`, with
        nothing changed, where the file cannot be read or written."""
        lines = self._lines()
        entry = str(root)
        marked = entry not in lines
        lines = [*lines, entry] if marked else [line for line in lines if line != entry]
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            spare = self.path.with_name(self.path.name + ".new")
            spare.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
            os.replace(spare, self.path)
        except OSError as exc:
            raise FavouritesError(
                f"could not save favourites to {self.path}: {exc.strerror or exc}") from exc
        self.roots = set(map(Path, lines))
        return marked

    def _lines(self) -> list[str]:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        except (OSError, UnicodeDecodeError) as exc:
            raise FavouritesError(
                f"could not read favourites from {self.path}: "
                f"{getattr(exc, 'strerror', None) or exc}") from exc
        return [line.strip() for line in text.splitlines() if line.strip()]


def resolve_root(path: str | Path, *more: str | Path,
                 on_search: SearchProgress | None = None) -> Path:
    """Which graph ``path`` means (SR-0045) — or, where several paths were given,
    which graph they mean between them (SR-0088).

    Pointing straight at a graph settles it, so a chosen candidate reopens
    without being asked again and a project holding a nested graph is not turned
    into a question by it. Otherwise the search runs beneath the path, and only
    an empty result falls back to the upward walk that lets the tool run from
    anywhere inside a project. Each of several paths is resolved by that same
    rule, and the graphs they reach are asked about together.
    """
    paths = (path, *more)
    bases = [base_of(_start_of(p)) for p in paths]
    roots: list[Path] = []
    search = _Search(on_search)
    for given, base in zip(paths, bases):
        roots.extend(r for r in _graphs_reached(given, base, search.path(roots))
                     if r not in roots)
    if len(paths) > 1:
        # A graph in one tree may be a source declared by a graph in another.
        roots = _drop_borrowed(roots)
    if len(roots) == 1:
        return roots[0]
    shared = shared_directory(bases)
    raise AmbiguousProjectError(shared if shared is not None else bases[0],
                                _candidates(roots, shared), several=len(paths) > 1)


def _start_of(path: str | Path) -> Path:
    try:
        return Path(path).resolve()
    except OSError as exc:
        # A relative path is resolved against the directory the program was
        # started in. Where that directory has since been removed there is
        # nothing to resolve against, and the reviewer needs to be told so in
        # words they can act on, not shown a traceback (SR-0074).
        raise RatifierError(
            f"cannot resolve the path {str(path)!r}: the directory tl-ratify was "
            "started in no longer exists. Change to a directory that exists, "
            "or give an absolute path with -C") from exc


def _graphs_reached(given: str | Path, base: Path,
                    on_search: SearchProgress | None = None) -> list[Path]:
    """The graphs one given path contributes (SR-0045): itself where it is a
    graph, those beneath it otherwise, and the nearest enclosing one where none
    lies beneath. A path that reaches none is refused by its name (SR-0088)."""
    if (base / CONFIG_NAME).exists():
        return [base]
    beneath = _drop_borrowed(_graphs_beneath(base, on_search))
    if beneath:
        return beneath
    root = _find_root(base)
    if root is None:
        raise RatifierError(
            f"no throughline.toml at, beneath or above {_start_of(given)} — "
            "not inside a throughline project")
    return [root]


def disk_state(session: Session) -> tuple:
    """What the session's graph looks like on disk now: every item file, register
    manifest and the configuration, each with its size and modification time.

    Read from the filesystem and nothing else, for the reason :func:`_latest_change`
    gives. The composed sources are included, because an item's grounding can change
    under the reviewer without one of the consumer's own files moving; a register
    that has no folder of its own, as a fetched source's may not, has no files to
    watch and is passed over. A file that vanishes between the listing and the stat
    simply drops out, and its absence is itself a difference from what was seen."""
    files = [session.root / CONFIG_NAME]
    seen_dirs: set[Path] = set()
    for project in (session.project, session.union):
        for register in project.registers.values():
            if register.path is None or register.path in seen_dirs:
                continue
            seen_dirs.add(register.path)
            files.extend(sorted(register.path.glob("*.yml")))
            files.append(register.path / ".register.yml")
    return _files_state(files)


def _files_state(files: list[Path]) -> tuple:
    """Each of ``files`` that can be stat'd, with its size and modification time."""
    state = []
    for f in files:
        try:
            st = f.stat()
        except OSError:
            continue
        state.append((str(f), st.st_mtime_ns, st.st_size))
    return tuple(state)


def mark_seen(session: Session) -> None:
    """Record the disk as this session now knows it: after a read, or after a write
    the session itself has just made, which is not somebody else's change."""
    session.seen = disk_state(session)


def changed_on_disk(session: Session) -> bool:
    """True when the graph's files differ from what this session last read or wrote."""
    return disk_state(session) != session.seen


def open_session(path: str | Path, *more: str | Path,
                 read_older: bool = False,
                 on_search: SearchProgress | None = None) -> Session:
    """Open the throughline project ``path`` names, composing its sources when it
    declares any. Raises :class:`AmbiguousProjectError` when the path encloses
    more than one graph and the choice is the reviewer's to make.

    A graph at an older on-disk format is refused unless ``read_older``, which
    reads it with the Tool's tolerant reader into a session every write through
    is refused (SR-0081). A graph at the Tool's own format opens as always."""
    return open_root(resolve_root(path, *more, on_search=on_search), read_older=read_older)


def open_root(root: Path, *, read_older: bool = False) -> Session:
    """Open the graph rooted at ``root``, which is already decided."""
    return _open(root, compose=True, read_older=read_older)


def reopen(session: Session) -> Session:
    """Read again the graph ``session`` was opened on (SR-0067).

    At the root it was opened from, and nowhere else. Resolving the path afresh
    searches beneath it and then above it (SR-0045), and from the parent of a
    directory that has gone, so a removed graph that sat beside or inside
    another would be replaced on screen by one the reviewer never chose.

    A graph whose configuration file has gone raises :class:`GraphLostError`
    (SR-0067). One that is still there and will not open raises
    :class:`GraphUnreadableError` (SR-0071): a file caught half-written or a
    source that cannot be reached for a moment is not a graph that has gone."""
    root = session.root
    try:
        return open_root(root, read_older=session.read_only)
    except RatifierError as exc:
        if not (root / CONFIG_NAME).exists():
            raise GraphLostError(root) from exc
        raise GraphUnreadableError(
            _first_line(str(exc)).removeprefix(f"{root}: ")) from exc


def _open(root: Path, compose: bool, read_older: bool = False) -> Session:
    """Load ``root``, composing its declared sources only when ``compose``.

    An uncomposed session is the graph's own account of itself: its ``union`` is
    the consumer, so anything grounding-related read from it would be wrong for a
    project that declares sources. It exists for :func:`describe_candidates`,
    which asks only what needs no union, and it never leaves this module.
    """
    older_format = None
    try:
        try:
            consumer = load_project(root)
        except ProjectError:
            if not read_older or (older_format := _declared_format(root)) is None:
                raise
            # The strict loader refuses a graph at an older format; the tolerant
            # reader reads it in memory and never writes (SR-0081).
            consumer = read_project(root)
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
    session = Session(
        root=root,
        project=consumer,
        union=union,
        ratified_status=ratified,
        proposed_status=proposed,
        composed=bool(sources),
        sources=sources,
        older_format=older_format,
    )
    mark_seen(session)
    return session


def _declared_format(root: Path) -> int | None:
    """The format version the graph's configuration declares, or None where it
    names none that can be read."""
    try:
        declared = tomllib.loads((root / CONFIG_NAME).read_text(encoding="utf-8"))
        return int(declared["project"]["format_version"])
    except (OSError, KeyError, TypeError, ValueError, tomllib.TOMLDecodeError):
        return None


def _refuse_if_read_only(session: Session) -> None:
    """Refuse any write through a read-only session, before anything changes (SR-0081)."""
    if session.read_only:
        raise ReadOnlySessionError(
            f"{session.root / CONFIG_NAME} is at format version {session.older_format}, "
            "which this tool reads but does not write; run `tl migrate` there to sign or "
            "change it — nothing was written")


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
        # Only what needs a signature or a decision (SR-0096): the signature is
        # what counts, so a signed item is settled whatever its status.
        entries = [e for e in entries
                   if e.concern not in ("ratified", "rejected", "deleted")]
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
    """One worklist entry as the TUI draws it: the Tool's judgement, plus the body
    and the resolved links this cockpit adds."""
    item = session.project.get(entry.uid)
    # A tombstone the Tool does not count as dead is a proposed deletion
    # (throughline SR-0267): the worklist offers it like any other proposal, and
    # the row says what kind of proposal it is (SR-0084).
    deletion = item.is_deleted and not entry.dead
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
        attrs=_authored_attrs(item),
        signed_attrs=tuple(session.schema.normative_attrs(item.type)),
        normative=item.normative,
        derived=item.derived,
        agree_to=entry.agree_to,
        reason=str(item.attrs.get("invalidated_reason") or ""),
        # A dead row is drawn as dead; the staleness of the record it still carries
        # is a fact the Tool reports, not an action this view offers (SR-0030).
        stale=entry.stale and not entry.dead,
        ratified_by=_names(item),
        signatures=tuple(_describe(e) for e in throughline_signatures(item)),
        standing=entry.standing,
        obstacle=entry.obstacle,
        deletion=deletion,
        dependents=tuple(_withdrawal_reaches(session, item.uid)) if deletion else (),
        record=_deletion_record(session, item) if deletion else (),
    )


def _deletion_record(session: Session, item: Item) -> tuple[str, ...]:
    """The deletion record as throughline renders it for a signer (SR-0083): the
    very lines `tl ratify` prints, so the cockpit and the command put one account
    in front of the person, and the fields are the Tool's to choose."""
    lines: list[str] = []
    render_for_ratification(session.project, item, emit=lines.append)
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return tuple(lines)


def _describe(entry: dict) -> str:
    """One signature in words — the name, and its identifier and role where the
    Tool recorded them (throughline SR-0254, SR-0259). The drawing is this
    cockpit's; what the signature holds is read as the Tool publishes it."""
    name = str(entry.get("by") or "a human")
    bits = [str(entry[k]) for k in ("id",) if entry.get(k)]
    if entry.get("role"):
        bits.append(f"as {entry['role']}")
    return name + (f" ({', '.join(bits)})" if bits else "")


def _names(item: Item) -> str:
    """The signers' names as prose: ``A``, ``A and B``, ``A, B and C``."""
    seen: list[str] = []
    for entry in throughline_signatures(item):
        name = str(entry.get("by") or "a human")
        if name not in seen:
            seen.append(name)
    if not seen:
        return ""
    return seen[0] if len(seen) == 1 else ", ".join(seen[:-1]) + " and " + seen[-1]


def _authored_attrs(item: Item) -> dict:
    """The attributes a reviewer is shown (SR-0076): every one the item carries
    except the ratification record, which the Tool owns and the pane already
    expresses as the readiness line. Which names make up that record is the
    Tool's to say (`attribute_owner`), not a prefix guessed here. The
    clarification record stays: the Tool puts it in front of a signer itself
    (tl:SR-0214), because a removed ambiguity flag is about the very words being
    signed."""
    return {name: value for name, value in item.attrs.items()
            if (attribute_owner(name) or ("",))[0] != "ratification record"}


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
    held = throughline_signatures(item)
    key = (uid, str((held[-1] if held else {}).get("fingerprint") or ""))
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

# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #

def default_identifier(path: str | Path | None = None) -> str | None:
    """The identifier offered where a graph declares roles (throughline SR-0259):
    the email the repository signs commits with, as throughline offers it, or None
    when there is none to offer. Asked of the Tool, never decided here (SR-0027)."""
    return throughline_default_identifier(path)


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


# Moves judged from the last commit (SR-0097). throughline's set_status judges a
# move from the status in memory; tl check judges it from the status at the last
# commit. Two permitted moves in one sitting can add up to one the project forbids
# (deferred -> proposed -> ratified, suspect -> rejected after verified -> suspect),
# which the gate then fails after the cockpit has written it. So before any action
# writes, it is run through throughline on a copy of the project, and every status
# that copy moved is judged from the last commit by throughline's own wording.
SIGN, AGREE, DELETE, REJECT = "sign", "agree", "delete", "reject"


@dataclass(frozen=True)
class Forbidden:
    """A move an action would write that the project's [transitions] forbid from
    where the item stood at the last commit: its UID, the status it held there, the
    status it would be given, and throughline's words for the refusal."""

    uid: str
    was: str
    to: str
    why: str


def forbidden_moves(session: Session, uid: str, action: str, *, by: str = "",
                    by_id: str | None = None, role: str | None = None) -> list[Forbidden]:
    """The moves ``action`` on ``uid`` would write that the last commit forbids
    (SR-0097), empty when there are none. ``action`` is one of :data:`SIGN`,
    :data:`AGREE`, :data:`DELETE` and :data:`REJECT`; ``by``, ``by_id`` and
    ``role`` are the signature's, since who signs decides whether a deletion
    retires and so what it marks. What the action moves is throughline's answer on
    a copy, never this module's prediction (SR-0026). An action throughline would
    refuse moves nothing here; the action itself then says why. Where no last
    commit can be read, nothing is judged, as tl check judges nothing then; outside
    a git work tree git is not asked (SR-0039)."""
    project = session.project
    if project.get(uid) is None:
        return []
    trial = copy.deepcopy(project)
    try:
        if action == SIGN:
            core_ratify(trial, uid, by, by_id=by_id, index=session.index, role=role,
                        cascade=Cascade())
        elif action == AGREE:
            to = entry_for(project, project.get(uid), index=session.index).agree_to
            if to is None:
                return []
            set_status(session.schema, trial.get(uid), to)
        elif action == DELETE:
            delete_item(trial, uid, reason="judged before it is written")
        elif action == REJECT:
            invalidate(trial, uid, "")
        else:
            raise ValueError(f"no such action: {action}")
    except (GroundingError, IdentityError):
        return []
    moved = {item.uid: item.status for item in trial.items()
             if item.status != project.get(item.uid).status}
    if not moved or not _in_work_tree(Path(project.path)):
        return []
    try:
        committed, _sha = load_project_at_ref(project.path, "HEAD")
    except ProjectError:
        return []
    schema = session.schema
    found = []
    for aid, to in sorted(moved.items()):
        then = committed.get(aid)
        # New since the commit, or held a status the project no longer declares:
        # not a move tl check judges (throughline SR-0083, SR-0314).
        if then is None or then.status == to or not schema.is_status(then.status):
            continue
        why = transition_refusal(schema, then, to)
        if why is not None:
            found.append(Forbidden(aid, then.status, to, why))
    return found


def _in_work_tree(path: Path) -> bool:
    """Whether ``path`` sits in a git work tree, looked for without starting a
    process: a graph outside one has no last commit, and the decisions stay usable
    where no process can be started (SR-0039). ``GIT_DIR`` names a repository kept
    elsewhere, so git is asked then too."""
    if os.environ.get("GIT_DIR"):
        return True
    here = path.resolve()
    return any((d / ".git").exists() for d in (here, *here.parents))


def refuse_forbidden_moves(session: Session, uid: str, action: str, *, by: str = "",
                           by_id: str | None = None, role: str | None = None) -> None:
    """Raise :class:`RatifierError` where ``action`` on ``uid`` would write a move
    the last commit forbids (SR-0097), naming the first such item, from and to
    which status, and that this sitting's work must be committed first. Called by
    every writer before it writes, and by the cockpit before it asks."""
    found = forbidden_moves(session, uid, action, by=by, by_id=by_id, role=role)
    if not found:
        return
    first = found[0]
    more = f" (and {len(found) - 1} more)" if len(found) > 1 else ""
    raise RatifierError(
        f"nothing written: {first.uid} was '{first.was}' at the last commit, and "
        f"'{first.was}' -> '{first.to}' is not a move this project's transitions "
        f"permit{more}; commit this sitting's work, then {action} {uid} again")


@dataclass
class Signing:
    """What one signature did beyond the item it was written on (SR-0082).

    ``retired`` is whether the item was a tombstone that now stands — its deletion
    ratified to the standing its kind requires (throughline SR-0269). ``marked``
    are the dependents that signature made suspect and ``refused`` the ones whose
    configured lifecycle declared no route to suspect, each with the move refused
    (throughline SR-0270, SR-0173). Both empty for a signature over wording, which
    marks nothing. A refusal is carried, never dropped: a dependent whose footing
    is gone and carries no flag is the drift the cockpit exists to show (SR-0037)."""

    retired: bool = False
    marked: list[str] = field(default_factory=list)
    refused: list[Refusal] = field(default_factory=list)


def _write_cascade(session: Session, cascade: Cascade) -> None:
    """Persist every dependent the Tool's cascade marked (SR-0082). The marking is
    throughline's; this writes what it reports moved, as `tl ratify` does, and
    only to this project's own registers — a borrowed item is never reached."""
    project = session.project
    for aid in cascade.marked:
        write_item(project.get(aid), project.register_of(aid))


def ratify_item(session: Session, uid: str, by: str, by_id: str | None = None,
                role: str | None = None) -> Signing:
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
    one is well formed is throughline's judgement, surfaced as it stands. ``role``
    is the role the signature is given in where the graph declares roles
    (throughline SR-0259); whether it is needed, and whether this person holds it,
    is the Tool's to say.

    On a tombstone the signature is over the deletion record (throughline
    SR-0269), and the one that brings it to the standing its kind requires
    retires the item and marks everything grounded on it suspect (throughline
    SR-0270). The Tool refuses to sign such a deletion unless the caller receives
    that cascade, so it is received here and every dependent it marked is written
    beside the item (SR-0082). What it did, and what it could not, is returned for
    the reviewer to be told."""
    _refuse_if_read_only(session)
    if session.project.get(uid) is None:
        raise RatifierError(f"{uid} does not exist")
    refuse_forbidden_moves(session, uid, SIGN, by=by, by_id=by_id, role=role)
    cascade = Cascade()
    try:
        item = core_ratify(session.project, uid, by, by_id=by_id, index=session.index,
                           role=role, cascade=cascade)
    except (GroundingError, IdentityError) as exc:
        raise RatifierError(str(exc)) from exc
    write_item(item, session.project.register_of(uid))
    _write_cascade(session, cascade)
    return Signing(retired=retired(item, session.schema),
                   marked=list(cascade.marked), refused=list(cascade.refused))


def agree_item(session: Session, uid: str) -> str:
    """Agree a draft (SR-0085): move it to the status throughline names for it
    (throughline SR-0307), through throughline's own choke point, and take no
    signature — it is signed after, as any other item. Returns the status it now
    holds."""
    _refuse_if_read_only(session)
    item = session.project.get(uid)
    if item is None:
        raise RatifierError(f"{uid} does not exist")
    to = entry_for(session.project, item, index=session.index).agree_to
    if to is None:
        raise RatifierError(
            f"{uid} is at '{item.status}' and cannot be agreed: it is no draft, or "
            "this project's transitions offer it nowhere from which it can be "
            "signed — delete it instead")
    refuse_forbidden_moves(session, uid, AGREE)
    try:
        set_status(session.schema, item, to)
    except GroundingError as exc:
        raise RatifierError(str(exc)) from exc
    write_item(item, session.project.register_of(uid))
    return to


def delete_draft(session: Session, uid: str, reason: str) -> bool:
    """Delete a draft (SR-0086) with throughline's own :func:`delete_item`: the
    file stays as a tombstone and the UID is never reused. Only a draft is offered
    here; any other item is rejected with x or signed. Returns whether the item was
    retired outright (throughline SR-0272) rather than left a proposed deletion."""
    _refuse_if_read_only(session)
    item = session.project.get(uid)
    if item is None:
        raise RatifierError(f"{uid} does not exist")
    if entry_for(session.project, item, index=session.index).concern != "draft":
        raise RatifierError(f"{uid} is not a draft — reject it with x instead")
    refuse_forbidden_moves(session, uid, DELETE)
    try:
        delete_item(session.project, uid, reason=reason)
    except GroundingError as exc:
        raise RatifierError(str(exc)) from exc
    write_item(item, session.project.register_of(uid))
    return retired(item, session.schema)


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
    return [
        aid for aid in _withdrawal_reaches(session, uid)
        if schema.allows_transition(project.get(aid).status, suspect)
    ]


def _withdrawal_reaches(session: Session, uid: str) -> list[str]:
    """The live items whose footing withdrawing ``uid`` takes away: its transitive
    dependents along the project's own ``withdrawing_link_types``, the walk
    throughline's cascade makes (tl:SR-0159), less those already dead. Shared by
    the rejection preview (SR-0025) and the deletion row (SR-0084), so the
    consequence a confirmation states is the one the Tool then enacts."""
    project = session.project
    schema = session.schema
    dead = schema.dead_statuses()
    return [
        aid
        for aid in sorted(Index.build(project).impact(
            uid, schema.withdrawing_link_types()))
        if (dep := project.get(aid)) is not None and dep.status not in dead
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
    _refuse_if_read_only(session)
    project = session.project
    if project.get(uid) is None:
        raise RatifierError(f"{uid} does not exist")
    refuse_forbidden_moves(session, uid, REJECT)
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
    _refuse_if_read_only(session)
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
