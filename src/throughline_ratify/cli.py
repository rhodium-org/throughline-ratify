# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""``tl-ratify`` — the entry point.

Launches the full-screen ratification cockpit over the throughline project
enclosing ``--path`` (default: the current directory). ``--list`` prints the same
worklist to stdout without curses, for pipelines, CI logs and quick glances.
``--summary`` leaves the sitting with a written account of every decision taken,
rendered once curses has closed so it can be redirected or pasted into the commit
that carries the work (see :mod:`throughline_ratify.report`).
"""
from __future__ import annotations

import argparse
import sys

from throughline import distribution_version as _v

from . import core, report


def _version_string() -> str:
    # Both read through throughline's own helper, so a working tree is named as
    # one rather than reporting the release it derives from (SR-0031). This cockpit
    # shows a verdict rather than computing one, so the build behind each layer is
    # part of what a reviewer needs in order to trust what is on the screen. The
    # Tool composes since throughline 3.11, so there is no third package to name.
    return f"tl-ratify {_v('throughline-ratify')} (throughline {_v('throughline')})"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tl-ratify",
        description="A full-screen assistant for ratifying throughline items (compose-aware).",
    )
    p.add_argument("--version", action="version", version=_version_string())
    p.add_argument("-C", "--path", default=".", help="project root or a path within it (default: .)")
    # The described default is throughline's, not a sentence maintained here (SR-0027).
    # This help string is the third place the one concept is written down, after this
    # tool's code and throughline's; naming the offer rather than restating its source
    # is what stops the flag advertising a default the assistant no longer has.
    p.add_argument("--by", default=None,
                   help="the ratifier recorded on sign-off (default: the identity "
                        "throughline offers — the one this repository signs with)")
    p.add_argument("--by-id", default=None, metavar="SCHEME:VALUE",
                   help="optional stable identifier for that human, e.g. "
                        "github:octocat or email:ada@example.com (SR-0028)")
    p.add_argument("--list", action="store_true",
                   help="print the ratification worklist and exit (no TUI)")
    p.add_argument("--all", action="store_true",
                   help="with --list, include already-ratified and dead "
                        "(rejected/tombstoned) items, not just the pending backlog")
    p.add_argument("--sort", choices=core.SORTS, default="concern",
                   help="worklist ordering: concern (default), roots (shallowest "
                        "grounding depth first) or leaves (deepest first)")
    # nargs="?" makes the path optional: bare --summary reports to stdout once the
    # full-screen view has closed, which is what makes it redirectable (SR-0021).
    p.add_argument("--summary", nargs="?", const=report.STDOUT, default=None,
                   metavar="PATH",
                   help="on exit, write an account of every decision taken during "
                        "the sitting to PATH (or stdout if PATH is omitted), ending "
                        "with a commit-ready trailer of the decided item UIDs")
    return p


def _print_list(session: core.Session, show_all: bool, sort: str) -> int:
    rows = core.build_queue(session, show_all=show_all, sort=sort)
    scope = "composed union" if session.composed else "local graph"
    done, total = core.ratification_progress(session)
    print(f"{session.project_name} \u2014 {scope}  \u2502  {done}/{total} ratified")
    if session.composed:
        for s in session.sources:
            print(f"  source {s.namespace}: {s.location}")
    if not rows:
        print("nothing to ratify \u2014 all clear")
        return 0
    header = "item(s) shown" if show_all else "item(s) pending ratification"
    print(f"{len(rows)} {header} (sort: {sort}):\n")
    for r in rows:
        # A stale row is ratifiable, but printing it as ratify-ready would hide the
        # one thing that distinguishes it — a signature already given, over wording
        # that has since changed (SR-0030). The concern is the more informative word.
        if r.stale:
            mark = "stale"
        else:
            mark = "ratify-ready" if r.ratifiable_now else r.concern
        print(f"  {r.icon} {r.uid:<14} [{r.status:<10}] {mark:<12} {r.title}")
    return 0


def _refuse_ambiguous(exc: core.AmbiguousProjectError) -> None:
    """Name every candidate and the command that selects it (SR-0047).

    The remedy is printed rather than described, because the reader of this
    message is the one who has to act on it and a message that only says a
    remedy exists has left them where it found them.
    """
    print(f"tl-ratify: {exc}", file=sys.stderr)
    width = max(len(c.name) for c in exc.candidates)
    for c in exc.candidates:
        print(f"  {c.name:<{width}}  {c.rel:<20}  tl-ratify -C {c.rel}", file=sys.stderr)


def _force_utf8_io() -> None:
    """Emit UTF-8 regardless of the console's default codec.

    This cockpit's own (SR-0059): what an interface does to its terminal is the
    interface's business, and the helper the Tool keeps for its own command line
    is not a name it publishes. A Windows console commonly defaults to cp1252,
    which raises the instant a glyph outside Latin-1 is printed.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:  # pragma: no cover - stream is not a TextIOWrapper
            continue
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):  # pragma: no cover - stream not reconfigurable
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_io()
    args = build_parser().parse_args(argv)

    # --list takes no decisions, so it could only ever produce an empty report the
    # user would reasonably read as "I changed nothing". Fail fast instead (SR-0021).
    if args.list and args.summary is not None:
        print("tl-ratify: --summary cannot be used with --list; --list takes no "
              "decisions, so there is nothing to summarise", file=sys.stderr)
        return 2

    interactive = not args.list and sys.stdout.isatty()
    candidates = None
    try:
        session = core.open_session(args.path)
    except core.AmbiguousProjectError as exc:
        # Which graph to open is the reviewer's to say (SR-0045). Where they cannot
        # be asked, refusing is the only honest answer — every rule for picking one
        # silently is wrong somewhere, and under --list the worklist for the wrong
        # project reads exactly like the right one (SR-0047).
        if not interactive:
            _refuse_ambiguous(exc)
            return 2
        session, candidates = None, exc.candidates
    except core.RatifierError as exc:
        print(f"tl-ratify: {exc}", file=sys.stderr)
        return 2

    if args.list:
        return _print_list(session, args.all, args.sort)

    if not sys.stdout.isatty():
        print("tl-ratify: not a terminal; use --list for non-interactive output",
              file=sys.stderr)
        return 2

    # A malformed identifier is throughline's to judge, and refusing now means the
    # refusal is legible instead of arriving behind a full-screen view (SR-0028).
    try:
        ratifier_id = core.normalise_identifier(args.by_id)
    except core.RatifierError as exc:
        print(f"tl-ratify: {exc}", file=sys.stderr)
        return 2

    from . import tui  # deferred: only import curses when we actually open the UI

    sitting = _Sitting(args.by, ratifier_id, args.summary)
    if candidates is None:
        sitting.open(tui, session)
        rc = 0
    else:
        rc = _work_through(tui, candidates, sitting)

    # Rendered only now, with curses closed, so the output is redirectable and
    # pasteable rather than merely readable inside the full-screen view.
    sitting.report()
    return rc


def _work_through(tui, candidates: list[core.Candidate], sitting: "_Sitting") -> int:
    """Ask which graph to open, open it, and ask again when it is closed, until
    the reviewer leaves the list without choosing or interrupts (SR-0063)."""
    chooser = tui.ProjectChooser(candidates)
    while True:
        chosen = chooser.choose()
        if chosen is None:
            return 0
        try:
            session = core.open_root(chosen.root)
        except core.RatifierError as err:
            print(f"tl-ratify: {err}", file=sys.stderr)
            return 2
        if not sitting.open(tui, session, quit_leads_to="projects"):
            return 0


class _Sitting:
    """One run of the cockpit, over however many graphs the reviewer opens in it.

    It keeps an account for each graph, not one for the run (SR-0065): a decision
    is recorded against the project it landed in, and item identifiers are unique
    only within a graph, so one trailer over several could name two different
    items by one UID.
    """

    def __init__(self, by: str | None, ratifier_id: str | None,
                 summary: str | None) -> None:
        self.by = by
        self.ratifier_id = ratifier_id
        self.summary = summary
        # graph root -> (its account, the session it was last opened as), in the
        # order the graphs were first opened.
        self.accounts: dict = {}

    def open(self, tui, session: core.Session, quit_leads_to: str = "quit") -> bool:
        """Open the cockpit on ``session``; True when the reviewer left it with
        the quit key, False when they interrupted it."""
        # The name offered is throughline's, obtained by asking it about this
        # project rather than by deciding it here (SR-0027). Asked of the graph
        # that was opened rather than the path that was typed, so a picked
        # candidate is the project whose identity is offered (SR-0045).
        ratifier = self.by or core.default_ratifier(session.root)
        log = None
        if self.summary is not None:
            # The log carries exactly the name the sitting signs off under — the
            # report never names a ratifier of its own choosing. A graph opened a
            # second time goes on with the account it already has.
            log = self.accounts[session.root][0] if session.root in self.accounts \
                else report.DecisionLog(ratifier)
            self.accounts[session.root] = (log, session)
        return tui.run(session, ratifier, log, ratifier_id=self.ratifier_id,
                       quit_leads_to=quit_leads_to)

    def report(self) -> None:
        written, rendered = None, 0
        for log, session in self.accounts.values():
            if not log:
                continue
            written = report.emit(log, self.summary, project_name=session.project_name,
                                  composed=session.composed, append=rendered > 0)
            rendered += 1
        if written is not None:
            print(f"tl-ratify: session summary written to {written}", file=sys.stderr)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
