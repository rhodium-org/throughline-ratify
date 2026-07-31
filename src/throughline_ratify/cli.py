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
from importlib.metadata import PackageNotFoundError, version as _pkg_version

from . import core, report


def _v(name: str) -> str:
    try:
        return _pkg_version(name)
    except PackageNotFoundError:  # pragma: no cover - source tree
        return "0.0.0+unknown"


def _version_string() -> str:
    return (
        f"tl-ratify {_v('throughline-ratify')} "
        f"(throughline-compose {_v('throughline-compose')}, throughline {_v('throughline')})"
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tl-ratify",
        description="A full-screen assistant for ratifying throughline items (compose-aware).",
    )
    p.add_argument("--version", action="version", version=_version_string())
    p.add_argument("-C", "--path", default=".", help="project root or a path within it (default: .)")
    p.add_argument("--by", default=None,
                   help="the ratifier recorded on sign-off (default: the current user)")
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
        mark = "ratify-ready" if r.ratifiable_now else r.concern
        print(f"  {r.icon} {r.uid:<14} [{r.status:<10}] {mark:<12} {r.title}")
    return 0


def main(argv: list[str] | None = None) -> int:
    from throughline.cli import force_utf8_io
    force_utf8_io()
    args = build_parser().parse_args(argv)

    # --list takes no decisions, so it could only ever produce an empty report the
    # user would reasonably read as "I changed nothing". Fail fast instead (SR-0021).
    if args.list and args.summary is not None:
        print("tl-ratify: --summary cannot be used with --list; --list takes no "
              "decisions, so there is nothing to summarise", file=sys.stderr)
        return 2

    try:
        session = core.open_session(args.path)
    except core.RatifierError as exc:
        print(f"tl-ratify: {exc}", file=sys.stderr)
        return 2

    if args.list:
        return _print_list(session, args.all, args.sort)

    if not sys.stdout.isatty():
        print("tl-ratify: not a terminal; use --list for non-interactive output",
              file=sys.stderr)
        return 2

    from . import tui  # deferred: only import curses when we actually open the UI

    ratifier = args.by or core.default_ratifier()
    # The log carries exactly the name the sitting signs off under — the report
    # never names a ratifier of its own choosing.
    log = report.DecisionLog(ratifier) if args.summary is not None else None
    tui.run(session, ratifier, log)

    # Rendered only now, with curses closed, so the output is redirectable and
    # pasteable rather than merely readable inside the full-screen view.
    if log is not None:
        written = report.emit(log, args.summary, project_name=session.project_name,
                              composed=session.composed)
        if written is not None:
            print(f"tl-ratify: session summary written to {written}", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
