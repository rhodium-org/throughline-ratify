# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0100 — the worklist can be ordered by when each item was last signed,
newest first, so a reviewer can read back what they have just signed.

The fixture's signed items carry the older ``ratified_by`` record, which names a
signer and no time; each test here writes the signatures it needs, with explicit
times, so the order never rests on how fast two ratifications ran.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from throughline_ratify import cli, core


def _sign(root: Path, uid: str, *stamps) -> None:
    """Give ``uid`` one signature per stamp, oldest first, in place of whatever
    record it carried. A stamp is written as given: a string is quoted, a
    datetime is left for YAML to write unquoted."""
    path = next(root.glob(f"*/{uid}.yml"))
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    attrs = doc.get("attrs") or {}
    attrs.pop("ratified_by", None)
    attrs.pop("ratified_fingerprint", None)
    if attrs:
        doc["attrs"] = attrs
    else:
        doc.pop("attrs", None)
    doc["ratifications"] = [{"by": f"signer{n}", "at": at} for n, at in enumerate(stamps)]
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def _order(root: Path, sort: str = "signed") -> list[str]:
    return [r.uid for r in core.build_queue(core.open_session(root),
                                            show_all=True, sort=sort)]


def test_signed_sort_puts_the_newest_signature_first(demo_project):
    _sign(demo_project, "INT-0001", "2026-11-28T10:00:00Z")
    _sign(demo_project, "FR-0005", "2026-11-28T12:00:00Z")
    _sign(demo_project, "FR-0006", "2026-11-28T11:00:00Z")
    assert _order(demo_project)[:3] == ["FR-0005", "FR-0006", "INT-0001"]


def test_signed_sort_reads_the_newest_of_several_signatures(demo_project):
    _sign(demo_project, "INT-0001", "2026-11-28T10:00:00Z")
    _sign(demo_project, "FR-0005", "2026-11-01T09:00:00Z", "2026-11-28T12:00:00Z")
    assert _order(demo_project)[:2] == ["FR-0005", "INT-0001"]


def test_signed_sort_puts_the_never_signed_last(demo_project):
    _sign(demo_project, "INT-0001", "2026-11-28T10:00:00Z")
    rows = core.build_queue(core.open_session(demo_project), show_all=True, sort="signed")
    signed = [n for n, r in enumerate(rows) if r.ratified_by]
    unsigned = [n for n, r in enumerate(rows) if not r.ratified_by]
    assert unsigned and max(signed) < min(unsigned)


def test_signed_sort_puts_undated_signatures_after_dated_ones(demo_project):
    # RISK-0001 keeps its older record: signed by alice, with no time.
    _sign(demo_project, "INT-0001", "2026-11-28T10:00:00Z")
    order = _order(demo_project)
    assert order[0] == "INT-0001"
    assert order.index("RISK-0001") < order.index("FR-0001")  # signed before unsigned


def test_signed_sort_keeps_the_default_order_for_a_tie(demo_project):
    # Signed in the same second: the root INT-0001 comes before FR-0005, grounded
    # on it, in the default order (an order by UID would put FR-0005 first), and
    # so it does here.
    _sign(demo_project, "FR-0005", "2026-11-28T10:00:00Z")
    _sign(demo_project, "INT-0001", "2026-11-28T10:00:00Z")
    default = _order(demo_project, sort="concern")
    assert default.index("INT-0001") < default.index("FR-0005")
    assert _order(demo_project)[:2] == ["INT-0001", "FR-0005"]


def test_signed_sort_compares_quoted_and_unquoted_stamps(demo_project):
    import datetime as dt
    _sign(demo_project, "INT-0001", "2026-11-28T10:00:00Z")
    _sign(demo_project, "FR-0005",
          dt.datetime(2026, 11, 28, 11, 0, tzinfo=dt.timezone.utc))
    assert _order(demo_project)[:2] == ["FR-0005", "INT-0001"]


def test_list_sort_signed_says_when_each_item_was_signed(demo_project, capsys):
    _sign(demo_project, "INT-0001", "2026-11-28T10:00:00Z")
    cli.main(["-C", str(demo_project), "--list", "--all", "--sort", "signed"])
    out = capsys.readouterr().out
    assert "sort: signed" in out
    assert "2026-11-28 10:00:00Z" in out
    assert "undated" in out and "unsigned" in out
    assert out.index("INT-0001") < out.index("RISK-0001") < out.index("FR-0001")
