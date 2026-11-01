# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0096 — r settles a signed item only where one permitted move reaches
ratified.

throughline judges a status change against the status last committed, so a
route of several moves written in one sitting is one move to `tl check`, and
in throughline's own graph that move (deferred -> ratified) was refused. Here
the fixture's draft status plays deferred's part: draft may reach ratified only
through approved.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from test_settled_by_status import SIGNED, _cockpit_on, _no_curses, _on_disk, _path, _rows  # noqa: F401
from throughline_ratify import cli, core


def _signed_at(root: Path, status: str) -> Path:
    """Sign the fixture's item, then move its status by hand to ``status``."""
    core.ratify_item(core.open_session(root), SIGNED, "Grace Hopper")
    path = _path(root)
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc["status"] = status
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
                    encoding="utf-8")
    return root


@pytest.fixture
def two_moves(demo_project: Path) -> Path:
    return _signed_at(demo_project, "draft")


def test_one_permitted_move_still_settles(demo_project, monkeypatch):
    root = _signed_at(demo_project, "proposed")
    app, asked = _cockpit_on(root, monkeypatch, answer=True)
    app.do_ratify()
    assert asked and _on_disk(root)["status"] == "ratified"


def test_two_moves_are_refused_and_nothing_is_written(two_moves, monkeypatch):
    before = _path(two_moves).read_text(encoding="utf-8")
    app, asked = _cockpit_on(two_moves, monkeypatch, answer=True)
    app.do_ratify()
    assert asked == [], "refused before asking"
    assert _path(two_moves).read_text(encoding="utf-8") == before
    assert app.log.decisions == []


def test_the_refusal_names_the_first_move_and_the_command(two_moves, monkeypatch):
    app, _ = _cockpit_on(two_moves, monkeypatch, answer=True)
    app.do_ratify()
    assert app.flash.kind == "warn"
    assert f"tl status {SIGNED} approved, commit, then r" in app.flash.text
    assert "'draft'" in app.flash.text and "last commit" in app.flash.text


def test_settle_item_refuses_a_route_of_several_moves(two_moves):
    with pytest.raises(core.RatifierError, match=f"tl status {SIGNED} approved"):
        core.settle_item(core.open_session(two_moves), SIGNED)
    assert _on_disk(two_moves)["status"] == "draft"


def test_the_row_still_says_signed_but_not_settled(two_moves, capsys):
    row = _rows(two_moves)[SIGNED]
    assert row.unsettled and row.settle_path == ["draft", "approved", "ratified"]
    assert cli.main(["-C", str(two_moves), "--list"]) == 0
    assert "unsettled" in capsys.readouterr().out
