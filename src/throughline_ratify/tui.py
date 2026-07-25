# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""The full-screen, htop-style ratification cockpit.

A pure curses view over :mod:`throughline_ratify.core`: a scrollable
worklist on the left, a detail pane on the right, a colour-coded summary header
and a keybinding footer. The whole terminal is used; colour and glyphs carry the
semantic weight (what needs a human, what is blocked, what cannot yet be signed
off) so the eye lands on the actionable rows first.
"""
from __future__ import annotations

import curses
import textwrap
from dataclasses import dataclass

from . import core
from .core import QueueItem, Session

# ------------------------------------------------------------------ colours

_PAIR = {}  # logical name -> curses pair id


def _init_colours() -> None:
    if not curses.has_colors():
        return
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except curses.error:  # pragma: no cover
        bg = curses.COLOR_BLACK

    spec = {
        "header": (curses.COLOR_WHITE, curses.COLOR_BLUE),
        "footer": (curses.COLOR_WHITE, curses.COLOR_BLUE),
        "sel": (curses.COLOR_BLACK, curses.COLOR_CYAN),
        "proposed": (curses.COLOR_YELLOW, bg),
        "ready": (curses.COLOR_GREEN, bg),
        "blocked": (curses.COLOR_CYAN, bg),
        "ungrounded": (curses.COLOR_RED, bg),
        "ambiguous": (curses.COLOR_RED, bg),
        "ratified": (curses.COLOR_GREEN, bg),
        "dim": (curses.COLOR_WHITE, bg),
        "ok": (curses.COLOR_GREEN, bg),
        "warn": (curses.COLOR_YELLOW, bg),
        "err": (curses.COLOR_RED, bg),
        "key": (curses.COLOR_CYAN, bg),
    }
    for i, (name, (fg, back)) in enumerate(spec.items(), start=1):
        try:
            curses.init_pair(i, fg, back)
            _PAIR[name] = i
        except curses.error:  # pragma: no cover
            _PAIR[name] = 0


def _attr(name: str, *, bold: bool = False) -> int:
    a = curses.color_pair(_PAIR.get(name, 0))
    if bold:
        a |= curses.A_BOLD
    return a


_CONCERN_LABEL = {
    "proposed": "proposed",
    "ready": "ready",
    "blocked": "blocked",
    "ungrounded": "ungrounded",
    "ambiguous": "ambiguous",
    "ratified": "ratified",
}


# ------------------------------------------------------------------ helpers

def _safe_addstr(win, y: int, x: int, text: str, attr: int = 0) -> None:
    """addstr that never raises on clipping at the screen edge."""
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x >= w:
        return
    if x < 0:
        text = text[-x:]
        x = 0
    text = text[: max(0, w - x)]
    try:
        win.addstr(y, x, text, attr)
    except curses.error:  # bottom-right cell always raises; harmless
        pass


def _hline(win, y: int, x: int, width: int, attr: int) -> None:
    _safe_addstr(win, y, x, " " * width, attr)


# ------------------------------------------------------------------ app

@dataclass
class _Flash:
    text: str = ""
    kind: str = "dim"  # ok | warn | err | dim


class App:
    def __init__(self, stdscr, session: Session, ratifier: str):
        self.scr = stdscr
        self.session = session
        self.ratifier = ratifier
        self.show_all = False
        self.sort = "concern"
        self.filter = ""
        self.rows: list[QueueItem] = []
        self.sel = 0
        self.top = 0  # first visible list row
        self.focus = "list"            # "list" | "detail"
        self.link_sel = 0              # cursor within the focused item's links
        self.expanded: set[int] = set()  # link indices showing full content
        self._detail_uid: str | None = None
        self._detail_scroll = 0        # first visible detail line
        self._link_lines: dict[int, int] = {}  # link index -> line in _detail_lines
        self.flash = _Flash()
        self.refresh_queue()

    # -- data ---------------------------------------------------------------
    def refresh_queue(self) -> None:
        all_rows = core.build_queue(self.session, show_all=self.show_all, sort=self.sort)
        if self.filter:
            f = self.filter.lower()
            all_rows = [r for r in all_rows if f in r.uid.lower() or f in r.title.lower()]
        self.rows = all_rows
        self.sel = max(0, min(self.sel, len(self.rows) - 1))

    @property
    def current(self) -> QueueItem | None:
        if 0 <= self.sel < len(self.rows):
            return self.rows[self.sel]
        return None

    def reload_from_disk(self) -> None:
        self.session = core.open_session(self.session.root)
        self.refresh_queue()
        self.flash = _Flash("reloaded from disk", "ok")

    # -- main loop ----------------------------------------------------------
    def run(self) -> None:
        curses.curs_set(0)
        self.scr.keypad(True)
        while True:
            self.draw()
            try:
                ch = self.scr.getch()
            except KeyboardInterrupt:  # Ctrl-C — quit cleanly, like 'q'
                return
            if ch in (ord("q"), ord("Q")):
                return
            self.handle(ch)

    def handle(self, ch: int) -> None:
        self.flash = _Flash()
        if ch in (9, curses.KEY_BTAB):  # Tab — switch pane focus
            self._toggle_focus()
            return
        if self.focus == "detail":
            self._handle_detail(ch)
            return
        if ch in (curses.KEY_DOWN, ord("j")):
            self.move(1)
        elif ch in (curses.KEY_UP, ord("k")):
            self.move(-1)
        elif ch == curses.KEY_NPAGE:
            self.move(self._page())
        elif ch == curses.KEY_PPAGE:
            self.move(-self._page())
        elif ch in (curses.KEY_HOME, ord("g")):
            self.sel = 0
        elif ch in (curses.KEY_END, ord("G")):
            self.sel = max(0, len(self.rows) - 1)
        elif ch in (ord("r"), ord("\n"), curses.KEY_ENTER):
            self.do_ratify()
        elif ch in (ord("x"), ord("X")):
            self.do_reject()
        elif ch in (ord("a"), ord("A")):
            self.show_all = not self.show_all
            self.refresh_queue()
            self.flash = _Flash("showing all items" if self.show_all else "showing pending items", "dim")
        elif ch in (ord("s"), ord("S")):
            nxt = core.SORTS[(core.SORTS.index(self.sort) + 1) % len(core.SORTS)]
            self.sort = nxt
            self.refresh_queue()
            self.flash = _Flash(f"sort: {self._sort_label(nxt)}", "dim")
        elif ch == ord("/"):
            self.do_filter()
        elif ch in (ord("R"),):
            self.reload_from_disk()
        elif ch == ord("?"):
            self.show_help()
        elif ch == curses.KEY_RESIZE:
            pass

    def _page(self) -> int:
        return max(1, self._list_height() - 1)

    def move(self, delta: int) -> None:
        if not self.rows:
            return
        self.sel = max(0, min(self.sel + delta, len(self.rows) - 1))

    # -- detail-pane focus --------------------------------------------------
    def _toggle_focus(self) -> None:
        if self.focus == "list":
            item = self.current
            if item is not None and item.links:
                self.focus = "detail"
                self.link_sel = 0
            else:
                self.flash = _Flash("no links to inspect", "dim")
        else:
            self.focus = "list"

    def _handle_detail(self, ch: int) -> None:
        item = self.current
        if item is None or not item.links:
            self.focus = "list"
            return
        n = len(item.links)
        if ch in (curses.KEY_DOWN, ord("j")):
            self.link_sel = min(self.link_sel + 1, n - 1)
        elif ch in (curses.KEY_UP, ord("k")):
            self.link_sel = max(self.link_sel - 1, 0)
        elif ch in (ord("\n"), curses.KEY_ENTER, ord("e"), ord("E")):
            self.expanded ^= {self.link_sel}  # toggle
        elif ch in (ord("x"), ord("X"), ord("d"), ord("D")):
            self.do_remove_link()
        elif ch == 27:  # ESC — back to the list
            self.focus = "list"

    def do_remove_link(self) -> None:
        item = self.current
        if item is None or not item.links:
            return
        lv = item.links[self.link_sel]
        if not self._confirm(f"Remove link {lv.type} \u2192 {lv.ref} from {item.uid}?"):
            self.flash = _Flash("removal cancelled", "dim")
            return
        try:
            core.remove_link(self.session, item.uid, self.link_sel)
        except core.RatifierError as exc:
            self.flash = _Flash(str(exc), "err")
            return
        self.refresh_queue()
        self.expanded = set()
        cur = self.current
        if cur is None or not cur.links:
            self.focus = "list"
        else:
            self.link_sel = min(self.link_sel, len(cur.links) - 1)
        self.flash = _Flash(f"\u2717 removed {lv.type} \u2192 {lv.ref}", "warn")

    # -- actions ------------------------------------------------------------
    def do_ratify(self) -> None:
        item = self.current
        if item is None:
            return
        if not item.ratifiable_now:
            # An item that overshot ratification without ever being signed off can be
            # put right via a route the project's own transitions permit — offer that
            # instead of a dead-end "cannot move to ratified" message.
            if item.reratify_path:
                self._do_reratify(item)
            else:
                self.flash = _Flash(self._why_blocked(item), "warn")
            return
        if not self._confirm(f"Ratify {item.uid} as {self.ratifier}?"):
            self.flash = _Flash("ratify cancelled", "dim")
            return
        try:
            core.ratify_item(self.session, item.uid, self.ratifier)
            self.refresh_queue()
            self.flash = _Flash(f"\u2713 {item.uid} ratified by {self.ratifier}", "ok")
        except core.RatifierError as exc:
            self.flash = _Flash(str(exc), "err")

    def _do_reratify(self, item: QueueItem) -> None:
        """Record a missed ratification on an overshot item. The route is the one
        core computed from this project's ``[transitions]`` — we only present it and
        confirm; nothing about which statuses are traversed is decided here."""
        route = " \u2192 ".join(item.reratify_path or [])
        if not self._confirm(
            f"{item.uid} is at '{item.status}' and was never ratified. "
            f"Record sign-off via {route}?"
        ):
            self.flash = _Flash("re-ratify cancelled", "dim")
            return
        try:
            walked = core.reratify_item(self.session, item.uid, self.ratifier)
            self.refresh_queue()
            self.flash = _Flash(
                f"\u2713 {item.uid} ratified by {self.ratifier} "
                f"(via {' \u2192 '.join(walked)})",
                "ok",
            )
        except core.RatifierError as exc:
            self.flash = _Flash(str(exc), "err")

    def do_reject(self) -> None:
        item = self.current
        if item is None:
            return
        reason = self._prompt(f"Reject {item.uid} — reason: ")
        if reason is None:
            self.flash = _Flash("reject cancelled", "dim")
            return
        if not self._confirm(f"Reject {item.uid} and mark dependents suspect?"):
            self.flash = _Flash("reject cancelled", "dim")
            return
        try:
            affected = core.reject_item(self.session, item.uid, reason)
            self.refresh_queue()
            extra = f", {len(affected)} dependent(s) now suspect" if affected else ""
            self.flash = _Flash(f"\u2717 {item.uid} rejected{extra}", "warn")
        except core.RatifierError as exc:
            self.flash = _Flash(str(exc), "err")

    def do_filter(self) -> None:
        val = self._prompt("filter (uid/title): ", initial=self.filter)
        self.filter = "" if val is None else val.strip()
        self.refresh_queue()

    @staticmethod
    def _sort_label(sort: str) -> str:
        return {"concern": "concern", "roots": "roots\u2193", "leaves": "leaves\u2191"}.get(sort, sort)

    @staticmethod
    def _why_blocked(item: QueueItem) -> str:
        if item.ambiguous:
            return f"{item.uid} is flagged ambiguous — clarify it before ratifying"
        if not item.grounded:
            return f"{item.uid} reaches no root — link it upward before ratifying"
        return f"{item.uid} cannot move straight to ratified from '{item.status}'"

    # -- drawing ------------------------------------------------------------
    def _list_height(self) -> int:
        h, _ = self.scr.getmaxyx()
        return max(1, h - 4)  # header(1) + summary(1) + footer(1) + spacing

    def _list_width(self) -> int:
        _, w = self.scr.getmaxyx()
        return max(24, min(52, w // 2))

    def _sync_detail(self) -> None:
        """Reset link cursor/expansion when the selected item changes, and drop out
        of detail focus if the current item has no links."""
        cur = self.current
        uid = cur.uid if cur is not None else None
        if uid != self._detail_uid:
            self._detail_uid = uid
            self.link_sel = 0
            self.expanded = set()
            self._detail_scroll = 0
        if self.focus == "detail" and (cur is None or not cur.links):
            self.focus = "list"

    def draw(self) -> None:
        self._sync_detail()
        self.scr.erase()
        h, w = self.scr.getmaxyx()
        if h < 6 or w < 40:
            _safe_addstr(self.scr, 0, 0, "terminal too small", _attr("err"))
            self.scr.noutrefresh()
            curses.doupdate()
            return
        self._draw_header(w)
        self._draw_summary(w)
        list_w = self._list_width()
        self._draw_list(top=2, height=h - 4, width=list_w)
        self._draw_detail(top=2, height=h - 4, left=list_w + 1, width=w - list_w - 1)
        self._draw_footer(h - 1, w)
        self.scr.noutrefresh()
        curses.doupdate()

    def _draw_header(self, w: int) -> None:
        _hline(self.scr, 0, 0, w, _attr("header", bold=True))
        left = f" throughline-ratify \u2502 {self.session.project_name}"
        _safe_addstr(self.scr, 0, 0, left, _attr("header", bold=True))
        if self.session.composed:
            right = f"composed \u2502 {len(self.session.sources)} source(s) "
        else:
            right = "local project "
        _safe_addstr(self.scr, 0, max(0, w - len(right)), right, _attr("header", bold=True))

    def _draw_summary(self, w: int) -> None:
        counts: dict[str, int] = {}
        for r in self.rows:
            counts[r.concern] = counts.get(r.concern, 0) + 1
        x = 1
        _safe_addstr(self.scr, 1, x, "queue:", _attr("dim"))
        x += 7
        concerns = ["proposed", "ready", "blocked", "ungrounded", "ambiguous"]
        if self.show_all:
            concerns.append("ratified")
        for concern in concerns:
            icon = core.CONCERNS[concern][0]
            seg = f"{icon} {counts.get(concern, 0)} {_CONCERN_LABEL[concern]}  "
            _safe_addstr(self.scr, 1, x, seg, _attr(concern, bold=concern in ("proposed",)))
            x += len(seg)
        done, total = core.ratification_progress(self.session)
        tail = f"\u2713 {done}/{total} ratified \u2502 sort:{self._sort_label(self.sort)} \u2502 "
        if self.filter:
            tail += f"filter:{self.filter} "
        tail += f"({len(self.rows)} shown)"
        _safe_addstr(self.scr, 1, max(x, w - len(tail) - 1), tail, _attr("dim"))

    def _draw_list(self, top: int, height: int, width: int) -> None:
        # keep selection in view
        if self.sel < self.top:
            self.top = self.sel
        elif self.sel >= self.top + height:
            self.top = self.sel - height + 1

        if not self.rows:
            msg = "nothing to ratify \u2014 all clear" if not self.filter else "no matches"
            _safe_addstr(self.scr, top, 1, msg, _attr("ok", bold=True))
            return

        for i in range(height):
            idx = self.top + i
            if idx >= len(self.rows):
                break
            row = self.rows[idx]
            y = top + i
            selected = idx == self.sel
            base = _attr("sel") if selected else _attr(row.concern)
            if selected:
                _hline(self.scr, y, 0, width, _attr("sel"))
            cursor = "\u25b8 " if selected else "  "
            uid = row.uid[:14].ljust(14)
            title = row.title or "(untitled)"
            line = f"{cursor}{row.icon} {uid} {title}"
            _safe_addstr(self.scr, y, 0, line[:width], base | (curses.A_BOLD if selected else 0))

        # scroll indicators
        if self.top > 0:
            _safe_addstr(self.scr, top, width - 1, "\u25b2", _attr("dim"))
        if self.top + height < len(self.rows):
            _safe_addstr(self.scr, top + height - 1, width - 1, "\u25bc", _attr("dim"))

    def _draw_detail(self, top: int, height: int, left: int, width: int) -> None:
        for y in range(top, top + height):
            _safe_addstr(self.scr, y, left - 1, "\u2502", _attr("dim"))
        item = self.current
        if item is None:
            _safe_addstr(self.scr, top, left + 1, "no item selected", _attr("dim"))
            return

        lines = self._detail_lines(item, width - 2)
        scroll = self._detail_scroll_offset(lines, height)
        for i in range(height):
            src = scroll + i
            if src >= len(lines):
                break
            text, attr = lines[src]
            _safe_addstr(self.scr, top + i, left + 1, text, attr)
        # scroll indicators
        if scroll > 0:
            _safe_addstr(self.scr, top, left + width - 2, "\u25b2", _attr("dim"))
        if scroll + height < len(lines):
            _safe_addstr(self.scr, top + height - 1, left + width - 2, "\u25bc", _attr("dim"))

    def _detail_scroll_offset(self, lines: list, height: int) -> int:
        """Choose a first-visible line so the focused link stays on screen."""
        total = len(lines)
        if total <= height:
            self._detail_scroll = 0
            return 0
        # when navigating links, pin the focused link (and, if expanded, as much
        # of its body as fits) into view; otherwise keep the last offset in range.
        if self.focus == "detail" and self.link_sel in self._link_lines:
            start = self._link_lines[self.link_sel]
            # end of this link's block = start of the next link, or end of lines
            nxt = self._link_lines.get(self.link_sel + 1, total)
            scroll = self._detail_scroll
            if start < scroll:
                scroll = start
            elif nxt > scroll + height:
                # bring as much of the block into view as possible without
                # pushing the header off the top
                scroll = min(start, nxt - height)
            self._detail_scroll = max(0, min(scroll, total - height))
        else:
            self._detail_scroll = max(0, min(self._detail_scroll, total - height))
        return self._detail_scroll

    def _detail_lines(self, item: QueueItem, width: int) -> list[tuple[int | str, int]]:
        out: list[tuple[str, int]] = []
        self._link_lines = {}

        def add(text: str = "", attr: int = 0) -> None:
            out.append((text, attr))

        def wrap(text: str, attr: int, indent: str = "  ") -> None:
            for seg in textwrap.wrap(text, max(10, width - len(indent))) or [""]:
                add(indent + seg, attr)

        head = f"{item.icon} {item.uid}"
        add(head, _attr(item.concern, bold=True))
        add(f"  {item.type}  \u2502  status: {item.status}", _attr("dim"))
        add()
        if item.title:
            wrap(item.title, _attr("dim", bold=True), indent="")
            add()

        # readiness line
        if item.concern == "ratified":
            add("  \u2713 already ratified", _attr("ok"))
        elif item.ratifiable_now:
            add(f"  \u2713 ready to ratify  ({item.status} \u2192 {self.session.ratified_status})",
                _attr("ok"))
        elif item.reratify_path:
            # overshot ratification: a config-permitted route can still record it
            add(f"  \u2717 never ratified — advanced to '{item.status}'", _attr("warn"))
            route = " \u2192 ".join(item.reratify_path)
            add(f"  \u21ba press r to record sign-off via {route}", _attr("key"))
        else:
            add(f"  \u2717 {self._why_blocked(item)}", _attr("warn"))
        gicon = "\u2713" if item.grounded else "\u26a0"
        gattr = "ok" if item.grounded else "ungrounded"
        dtxt = "root" if item.depth == 0 else (str(item.depth) if item.depth is not None else "\u2014")
        add(f"  grounded: {gicon}   depth: {dtxt}   ambiguous: {'yes' if item.ambiguous else 'no'}",
            _attr(gattr))
        add()

        if item.text:
            add("text", _attr("key"))
            wrap(item.text, 0)
            add()
        if item.rationale:
            add("rationale", _attr("key"))
            wrap(item.rationale, 0)
            add()
        if item.links:
            hint = "  (Tab to navigate)" if self.focus != "detail" else "  (\u25b8 j/k \u00b7 e expand \u00b7 x remove)"
            add(f"links{hint}", _attr("key"))
            for i, lv in enumerate(item.links):
                self._link_lines[i] = len(out)
                focused = self.focus == "detail" and i == self.link_sel
                cur = "\u25b8 " if focused else "  "
                if lv.external:
                    # prefer the target's authoritative clause reference; fall back to
                    # the source namespace only when the item declares no source_ref.
                    tag = f"  ({lv.source_ref or lv.namespace})"
                else:
                    tag = ""
                head_attr = _attr("sel") if focused else _attr("dim", bold=True)
                if lv.resolved:
                    add(f"{cur}{lv.type} \u2192 {lv.ref}{tag}", head_attr)
                    if i in self.expanded:
                        meta = f"{lv.target_type} \u00b7 {lv.target_status}".strip(" \u00b7")
                        if meta:
                            add("      " + meta, _attr("dim"))
                        wrap(lv.title, _attr("dim", bold=True), indent="      ")
                        if lv.text:
                            wrap(lv.text, _attr("dim"), indent="      ")
                    else:
                        wrap(lv.title, _attr("dim"), indent="      ")
                else:
                    ua = _attr("sel") if focused else _attr("ungrounded")
                    add(f"{cur}{lv.type} \u2192 {lv.ref}  (unresolved)", ua)
        else:
            add("no links", _attr("dim"))
        return out

    def _draw_footer(self, y: int, w: int) -> None:
        _hline(self.scr, y, 0, w, _attr("footer"))
        if self.flash.text:
            _safe_addstr(self.scr, y, 0, " " + self.flash.text, _attr(self.flash.kind, bold=True)
                         | curses.A_REVERSE)
            return
        if self.focus == "detail":
            keys = [
                ("j/k", "link"), ("e/\u21b5", "expand"), ("x", "remove"),
                ("Tab", "list"), ("?", "help"), ("q", "quit"),
            ]
        else:
            keys = [
                ("j/k", "move"), ("r/\u21b5", "ratify"), ("x", "reject"),
                ("Tab", "detail"), ("a", "all"), ("s", "sort"), ("/", "filter"),
                ("R", "reload"), ("?", "help"), ("q", "quit"),
            ]
        x = 1
        for key, label in keys:
            _safe_addstr(self.scr, y, x, key, _attr("footer", bold=True) | curses.A_REVERSE)
            x += len(key)
            seg = f":{label}  "
            _safe_addstr(self.scr, y, x, seg, _attr("footer"))
            x += len(seg)

    # -- modal prompts ------------------------------------------------------
    def _confirm(self, question: str) -> bool:
        h, w = self.scr.getmaxyx()
        y = h - 1
        _hline(self.scr, y, 0, w, _attr("warn") | curses.A_REVERSE)
        _safe_addstr(self.scr, y, 1, f"{question} [y/N] ", _attr("warn", bold=True) | curses.A_REVERSE)
        self.scr.noutrefresh()
        curses.doupdate()
        ch = self.scr.getch()
        return ch in (ord("y"), ord("Y"))

    def _prompt(self, label: str, initial: str = "") -> str | None:
        h, w = self.scr.getmaxyx()
        y = h - 1
        buf = list(initial)
        curses.curs_set(1)
        try:
            while True:
                _hline(self.scr, y, 0, w, _attr("header") | curses.A_REVERSE)
                shown = (label + "".join(buf))[: w - 1]
                _safe_addstr(self.scr, y, 0, shown, _attr("header", bold=True) | curses.A_REVERSE)
                self.scr.move(y, min(len(label) + len(buf), w - 1))
                self.scr.noutrefresh()
                curses.doupdate()
                ch = self.scr.getch()
                if ch in (27,):  # ESC
                    return None
                if ch in (ord("\n"), curses.KEY_ENTER):
                    return "".join(buf)
                if ch in (curses.KEY_BACKSPACE, 127, 8):
                    if buf:
                        buf.pop()
                elif 32 <= ch < 127:
                    buf.append(chr(ch))
        finally:
            curses.curs_set(0)

    def show_help(self) -> None:
        lines = [
            "throughline-ratify",
            "",
            "  j / \u2193        move down",
            "  k / \u2191        move up",
            "  g / G        jump to top / bottom",
            "  PgUp/PgDn    page",
            "  r / Enter    ratify the selected item; on a blocked item that",
            "               overshot ratification, record the missed sign-off",
            "               via a route the project's transitions permit",
            "  x            reject (invalidate) the selected item",
            "  a            toggle showing already-ratified items",
            "  s            cycle sort: concern \u2192 roots\u2193 \u2192 leaves\u2191",
            "  /            filter by uid or title",
            "  R            reload the graph from disk",
            "  ?            this help",
            "  q            quit",
            "",
            "detail pane:",
            "  Tab          focus the detail pane's links (Tab again \u2192 list)",
            "  j / k        move between the focused item's links",
            "  e / Enter    expand a link to read the referenced item",
            "  x / d        remove a link (refused if it would un-ground)",
            "  Esc          return focus to the list",
            "",
            "concerns:",
            "  \u25cf proposed    awaiting a human's accountability",
            "  \u25c9 ready       approved, one move from ratified",
            "  \u25cb blocked     pending but not directly ratifiable",
            "  \u26a0 ungrounded  reaches no root \u2014 link it first",
            "  \u2691 ambiguous   flagged ambiguous \u2014 clarify first",
            "  \u2713 ratified    already signed off (shown under 'a')",
            "",
            "sort roots\u2193 orders shallowest-first (closest to intent);",
            "leaves\u2191 orders deepest-first. ungrounded items sort last.",
            "",
            "  press any key to return",
        ]
        self.scr.erase()
        for i, ln in enumerate(lines):
            attr = _attr("key", bold=True) if i == 0 else _attr("dim")
            _safe_addstr(self.scr, i + 1, 2, ln, attr)
        self.scr.noutrefresh()
        curses.doupdate()
        self.scr.getch()


def run(session: Session, ratifier: str) -> None:
    def _main(stdscr):
        _init_colours()
        App(stdscr, session, ratifier).run()

    try:
        # curses.wrapper restores the terminal in its finally before re-raising,
        # so a Ctrl-C anywhere in the loop exits cleanly with no traceback.
        curses.wrapper(_main)
    except KeyboardInterrupt:
        pass
