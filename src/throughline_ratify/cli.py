# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""``tl-ratify`` — the entry point.

Launches the full-screen ratification cockpit over the throughline project
enclosing ``--path`` (default: the current directory). ``--list`` prints the same
worklist to stdout without curses, for pipelines, CI logs and quick glances.
"""
from __future__ import annotations

import argparse
import sys
from importlib.metadata import PackageNotFoundError, version as _pkg_version

from . import core


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
    args = build_parser().parse_args(argv)
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
    tui.run(session, ratifier)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
