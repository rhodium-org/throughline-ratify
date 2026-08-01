# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""The account a sitting leaves behind (UR-0005, SR-0021).

A ratification sitting scatters its evidence one field at a time across dozens of
item files, so the only way to answer "what did I just accept, and why did that
one get rejected" is to read a diff. This module keeps a running record of every
decision as it is taken and renders it, once the sitting ends, as a plain-text
report that can be pasted into the commit that carries the work.

Two deliberate properties:

* **It describes, it does not govern.** Nothing here writes to the graph or
  decides anything; the items themselves remain the only source of truth. The
  log is appended to *after* a decision has already been persisted, so a report
  can never claim something the graph does not.
* **It never names a ratifier of its own choosing.** The name on the report is
  the one the sitting already recorded on sign-off, handed in by the caller —
  this module has no fallback and will not invent one.

Rendering happens after curses has closed (see :func:`throughline_ratify.cli.main`),
which is what makes the output redirectable and pasteable. The output is
deliberately ASCII-only so it survives redirection into a file, a commit message
or a pipe under any locale.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from textwrap import wrap

# What kind of decision an entry records. These strings are the words the report
# prints, so they read as the ratifier's own account of what they did.
RATIFIED = "ratified"
RERATIFIED = "re-ratified"
# Distinct from RERATIFIED on purpose (SR-0030). "re-ratified" is the account of a
# sign-off that was never taken and has now been recorded; this is the account of one
# that was taken, over wording that has since changed, and has now been given again.
# Reporting the second as the first would say of an item that nobody had accepted it,
# when somebody had — a false statement about the very record the report exists for.
RESIGNED = "re-signed"
REJECTED = "rejected"
LINK_REMOVED = "link removed"

# The destination meaning "stdout" — what ``--summary`` with no path resolves to.
STDOUT = "-"

# The trailer token the estate's commit convention expects, so the last line of a
# report can be pasted straight into the commit that carries the decisions.
TRAILER_TOKEN = "Items"

_WIDTH = 76  # wrap width: fits a git commit body without reflowing


@dataclass(frozen=True)
class Decision:
    """One decision, captured the moment after it was persisted."""

    kind: str
    uid: str
    title: str
    # re-ratification and re-signing only: the status itinerary the assistant walked
    # to reach ratified and come back. Named in the report so the ratifier can see
    # what was moved on their behalf. Empty when the item could be signed where it
    # stood and nothing had to be walked.
    route: tuple[str, ...] = ()
    # re-signing only: who had signed the wording that has since been replaced.
    superseded: str = ""
    # rejection only: the reason given, and the dependents suspicion cascaded to.
    reason: str = ""
    suspected: tuple[str, ...] = ()
    # link removal only.
    link_type: str = ""
    link_ref: str = ""
    grounding: bool = False


@dataclass
class DecisionLog:
    """Every decision of one sitting, in the order taken.

    ``ratifier`` is the name the sitting signs off under; it is supplied by the
    caller and simply carried through to the report."""

    ratifier: str
    decisions: list[Decision] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.decisions)

    def __bool__(self) -> bool:
        return bool(self.decisions)

    # -- recording ---------------------------------------------------------- #

    def ratified(self, uid: str, title: str) -> None:
        self.decisions.append(Decision(RATIFIED, uid, title))

    def reratified(self, uid: str, title: str, route: list[str]) -> None:
        self.decisions.append(Decision(RERATIFIED, uid, title, route=tuple(route)))

    def resigned(self, uid: str, title: str, superseded: str = "",
                 route: list[str] | None = None) -> None:
        self.decisions.append(
            Decision(RESIGNED, uid, title, route=tuple(route or ()),
                     superseded=superseded)
        )

    def rejected(self, uid: str, title: str, reason: str, suspected: list[str]) -> None:
        self.decisions.append(
            Decision(REJECTED, uid, title, reason=reason, suspected=tuple(suspected))
        )

    def link_removed(
        self, uid: str, title: str, link_type: str, ref: str, *, grounding: bool = False
    ) -> None:
        self.decisions.append(
            Decision(
                LINK_REMOVED, uid, title,
                link_type=link_type, link_ref=ref, grounding=grounding,
            )
        )

    # -- derived views ------------------------------------------------------ #

    @property
    def decided_uids(self) -> list[str]:
        """Every item touched, de-duplicated, in the order first decided — the
        list the commit trailer cites."""
        seen: list[str] = []
        for d in self.decisions:
            if d.uid not in seen:
                seen.append(d.uid)
        return seen

    def tally(self) -> list[tuple[str, int]]:
        """``(kind, count)`` in a fixed order, omitting kinds that did not occur."""
        counts = {k: 0 for k in (RATIFIED, RERATIFIED, RESIGNED, REJECTED, LINK_REMOVED)}
        for d in self.decisions:
            counts[d.kind] = counts.get(d.kind, 0) + 1
        return [(k, n) for k, n in counts.items() if n]


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

def _wrapped(text: str, indent: str) -> list[str]:
    lines = wrap(text, width=_WIDTH, initial_indent=indent, subsequent_indent=indent)
    return lines or [indent.rstrip()]


def _entry(n: int, d: Decision) -> list[str]:
    """One decision, as the block of lines the report prints for it."""
    head = f"  {n}. {d.kind:<12} {d.uid}"
    out = [head, *_wrapped(d.title, "     ")]
    if d.kind in (RERATIFIED, RESIGNED) and d.route:
        out += _wrapped("route walked: " + " -> ".join(d.route), "     ")
    if d.kind == RESIGNED:
        out += _wrapped(
            f"content changed since {d.superseded or 'a human'} ratified it", "     ")
    if d.kind == REJECTED:
        out += _wrapped(f"reason: {d.reason or '(none given)'}", "     ")
        if d.suspected:
            out += _wrapped(
                "dependents made suspect: " + ", ".join(d.suspected), "     "
            )
    if d.kind == LINK_REMOVED:
        kind = "grounding link" if d.grounding else "link"
        out += _wrapped(f"removed {kind}: {d.link_type} -> {d.link_ref}", "     ")
    return out


def render(
    log: DecisionLog, *, project_name: str, composed: bool, when: datetime | None = None
) -> str:
    """The full plain-text account of a sitting. Assumes at least one decision was
    taken; callers use :func:`emit`, which declines to render an empty sitting."""
    ended = (when or datetime.now().astimezone()).strftime("%Y-%m-%d %H:%M:%S %Z").strip()
    scope = "composed union" if composed else "local graph"

    lines = [
        "tl-ratify session summary",
        "=" * 25,
        "",
        f"Project  : {project_name}",
        f"Scope    : {scope}",
        f"Ratifier : {log.ratifier}",
        f"Ended    : {ended}",
        "",
        f"Decisions taken ({len(log)}), in the order taken:",
        "",
    ]
    for n, d in enumerate(log.decisions, start=1):
        lines += _entry(n, d)
        lines.append("")

    lines.append("Tally: " + ", ".join(f"{n} {kind}" for kind, n in log.tally()))
    lines.append("")
    lines.append(f"{TRAILER_TOKEN}: " + ", ".join(log.decided_uids))
    return "\n".join(lines) + "\n"


def emit(
    log: DecisionLog,
    destination: str | None,
    *,
    project_name: str,
    composed: bool,
    stream=None,
) -> Path | None:
    """Render the sitting to ``destination`` — a path, or :data:`STDOUT` for the
    stream. Returns the file written, or ``None`` when nothing was written.

    A sitting in which no decision was taken produces no report and, crucially,
    creates no file: a browsing session must not leave a misleading empty artefact
    behind (SR-0021)."""
    if destination is None or not log:
        return None

    text = render(log, project_name=project_name, composed=composed)
    if destination == STDOUT:
        (stream or sys.stdout).write(text)
        return None

    path = Path(destination).expanduser()
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
